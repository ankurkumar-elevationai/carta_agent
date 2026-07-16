"""
services/providers/carta/api/direct_fetch.py
---------------------------------------------
Direct Fetch Service — The fast-path engine that fetches individual Carta
endpoints in <1 second using stored cookies + the API Route Registry.
No browser interaction required.
"""

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

import httpx

from .auth import CartaAuthContext
from .route_registry import RouteRegistry, EntityContext, ResolvedRoute
from .session_manager import SessionManager
from .replay_client import (
    ReplayFailureType,
    FailureClassifier,
    is_cloudflare,
    generate_shape_hash,
)

log = logging.getLogger(__name__)


@dataclass
class DirectFetchResult:
    """Result of a direct fetch operation."""
    endpoint_name: str
    status_code: int
    latency_ms: int
    payload: Any = None
    error: Optional[str] = None
    url: Optional[str] = None
    shape_hash: Optional[str] = None
    retried: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class DirectFetchService:
    """
    Fast-path data fetcher that bypasses Playwright entirely.
    
    Usage:
        service = DirectFetchService()
        result = await service.fetch("get_investments", firm_id=3288983)
        # Returns in <1 second
    
    For entity-level endpoints:
        result = await service.fetch("get_capital_calls", firm_id=3288983, entity_id=3272607)
    """

    def __init__(
        self,
        registry: Optional[RouteRegistry] = None,
        session_manager: Optional[SessionManager] = None,
        timeout: float = 10.0,
    ):
        self.registry = registry or RouteRegistry()
        self.session_manager = session_manager or SessionManager()
        self.timeout = timeout
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init a reusable httpx client for connection pooling."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._http_client

    async def close(self):
        """Cleanup HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def fetch(
        self,
        endpoint_name: str,
        firm_id: int,
        entity_id: Optional[int] = None,
        org_id: Optional[int] = None,
        org_uuid: Optional[str] = None,
        fund_uuid: Optional[str] = None,
        partner_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> DirectFetchResult:
        """
        Fetch a single endpoint's data via direct HTTP.
        
        Args:
            endpoint_name: Platform endpoint name (e.g. "get_investments")
            firm_id: Carta firm/individual ID
            entity_id: Corporation/entity ID (required for detail endpoints)
            org_id: Organization ID (optional, defaults to firm_id)
            org_uuid: Organization UUID for fund-admin APIs
            fund_uuid: Fund UUID for fund-admin APIs
            partner_id: Partner interest ID
            start_date: Start date for statements
            end_date: End date for statements
            extra_params: Additional query parameters
            
        Returns:
            DirectFetchResult with payload and metadata
        """
        start = time.monotonic()

        # 1. Check registry readiness
        if not self.registry.is_ready():
            return DirectFetchResult(
                endpoint_name=endpoint_name,
                status_code=503,
                latency_ms=0,
                error="API Route Registry is empty. Run a full sync first to discover Carta's API endpoints.",
            )

        # 2. Build entity context
        ctx = EntityContext(
            firm_id=firm_id,
            org_id=org_id or firm_id,
            entity_id=entity_id,
            org_uuid=org_uuid,
            fund_uuid=fund_uuid,
            partner_id=partner_id,
            start_date=start_date,
            end_date=end_date,
        )

        # 3. Resolve the URL
        try:
            route = self.registry.lookup(endpoint_name, ctx)
        except KeyError as e:
            return DirectFetchResult(
                endpoint_name=endpoint_name,
                status_code=404,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=str(e),
            )
        except ValueError as e:
            return DirectFetchResult(
                endpoint_name=endpoint_name,
                status_code=422,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=str(e),
            )

        # 4. Get auth context
        try:
            auth = await self.session_manager.get_auth_context()
        except RuntimeError as e:
            return DirectFetchResult(
                endpoint_name=endpoint_name,
                status_code=401,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=str(e),
                url=route.url,
            )

        # 5. Make the HTTP request
        result = await self._execute_request(route, auth, extra_params, start)
        result.endpoint_name = endpoint_name

        # 6. Handle auth failures with retry
        if result.status_code in (401, 403) and not result.retried:
            log.warning(f"[DirectFetch] Auth failure ({result.status_code}) on {endpoint_name}. Attempting session refresh...")
            self.session_manager.invalidate()
            try:
                auth = await self.session_manager.get_auth_context()
                retry_result = await self._execute_request(route, auth, extra_params, time.monotonic())
                retry_result.endpoint_name = endpoint_name
                retry_result.retried = True
                result = retry_result
            except RuntimeError:
                pass

        # 7. Handle transaction URL firm/fund swap retry
        if result.status_code in (401, 403, 404) and "/transactions/" in route.url:
            alternative_url = route.url
            if "/transactions/firm/" in route.url:
                alternative_url = route.url.replace("/transactions/firm/", "/transactions/fund/")
            elif "/transactions/fund/" in route.url:
                alternative_url = route.url.replace("/transactions/fund/", "/transactions/firm/")

            if alternative_url != route.url:
                log.info(f"[DirectFetch] Retrying with alternative transaction URL pattern: {alternative_url}")
                alt_route = ResolvedRoute(
                    url=alternative_url,
                    method=route.method,
                    params=route.params,
                    category=route.category,
                    requires_entity_id=route.requires_entity_id,
                    template_name=route.template_name
                )
                try:
                    retry_result = await self._execute_request(alt_route, auth, extra_params, time.monotonic())
                    retry_result.endpoint_name = endpoint_name
                    retry_result.retried = True
                    if retry_result.status_code == 200:
                        return retry_result
                except Exception as e:
                    log.warning(f"[DirectFetch] Failed transaction swap retry: {e}")

        # 8. Handle portfolio investments URL firm/individual list retry
        if result.status_code in (401, 403, 404) and ("list_firm_investments" in route.url or "list_individual_portfolio_investments" in route.url):
            alternative_url = route.url
            if "list_firm_investments" in route.url:
                alternative_url = route.url.replace("/list_firm_investments/", f"/list_individual_portfolio_investments/{ctx.firm_id}/list/")
            elif "list_individual_portfolio_investments" in route.url:
                import re
                alternative_url = re.sub(r"/list_individual_portfolio_investments/\d+/list/?", "/list_firm_investments/", route.url)
            
            if alternative_url != route.url:
                log.info(f"[DirectFetch] Retrying with alternative investments URL pattern: {alternative_url}")
                alt_route = ResolvedRoute(
                    url=alternative_url,
                    method=route.method,
                    params=route.params,
                    category=route.category,
                    requires_entity_id=route.requires_entity_id,
                    template_name=route.template_name
                )
                try:
                    retry_result = await self._execute_request(alt_route, auth, extra_params, time.monotonic())
                    retry_result.endpoint_name = endpoint_name
                    retry_result.retried = True
                    if retry_result.status_code == 200:
                        return retry_result
                except Exception as e:
                    log.warning(f"[DirectFetch] Failed investments swap retry: {e}")

        # 9. Handle valuation URL tabs vs. firm_entity_tabs retry
        if result.status_code in (401, 403, 404) and ("firm_entity_tabs" in route.url or "/tabs/" in route.url):
            alternative_url = route.url
            if "firm_entity_tabs" in route.url:
                alternative_url = route.url.replace(
                    f"/portfolio/firm/{ctx.org_id or ctx.firm_id}/company/{ctx.entity_id}/firm_entity_tabs",
                    f"/portfolio/fund/{ctx.firm_id}/entity/{ctx.entity_id}/tabs/"
                )
            elif "/tabs/" in route.url:
                alternative_url = route.url.replace(
                    f"/portfolio/fund/{ctx.firm_id}/entity/{ctx.entity_id}/tabs/",
                    f"/portfolio/firm/{ctx.org_id or ctx.firm_id}/company/{ctx.entity_id}/firm_entity_tabs"
                )
            
            if alternative_url != route.url:
                log.info(f"[DirectFetch] Retrying with alternative valuation URL pattern: {alternative_url}")
                alt_route = ResolvedRoute(
                    url=alternative_url,
                    method=route.method,
                    params=route.params,
                    category=route.category,
                    requires_entity_id=route.requires_entity_id,
                    template_name=route.template_name
                )
                try:
                    retry_result = await self._execute_request(alt_route, auth, extra_params, time.monotonic())
                    retry_result.endpoint_name = endpoint_name
                    retry_result.retried = True
                    if retry_result.status_code == 200:
                        return retry_result
                except Exception as e:
                    log.warning(f"[DirectFetch] Failed valuation swap retry: {e}")

        return result

    async def fetch_all(
        self,
        endpoint_names: List[str],
        firm_id: int,
        entity_id: Optional[int] = None,
        org_id: Optional[int] = None,
        concurrency: int = 3,
    ) -> Dict[str, DirectFetchResult]:
        """
        Fetch multiple endpoints concurrently.
        
        Args:
            endpoint_names: List of endpoint names to fetch
            firm_id: Carta firm ID
            entity_id: Entity ID (if needed)
            org_id: Org ID
            concurrency: Max concurrent requests (to avoid rate limiting)
            
        Returns:
            Dict mapping endpoint_name → DirectFetchResult
        """
        semaphore = asyncio.Semaphore(concurrency)
        results: Dict[str, DirectFetchResult] = {}

        async def _fetch_one(name: str):
            async with semaphore:
                result = await self.fetch(name, firm_id, entity_id, org_id)
                results[name] = result
                # Small delay between requests to be respectful
                await asyncio.sleep(0.3)

        tasks = [_fetch_one(name) for name in endpoint_names]
        await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def fetch_url(
        self,
        url: str,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> DirectFetchResult:
        """
        Fetch an arbitrary relative or absolute URL using the active cookie jar.
        """
        start = time.monotonic()

        # Resolve full URL if relative
        if url.startswith("/"):
            from services.providers.carta.utils.settings import settings
            base_url = settings.app_base_url.rstrip("/")
            full_url = f"{base_url}{url}"
        else:
            full_url = url

        route = ResolvedRoute(
            url=full_url,
            params={},
            method="GET",
            category="custom",
            requires_entity_id=False,
            template_name="custom_url",
        )

        # Get auth context
        try:
            auth = await self.session_manager.get_auth_context()
        except RuntimeError as e:
            return DirectFetchResult(
                endpoint_name="fetch_url",
                status_code=401,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=str(e),
                url=full_url,
            )

        result = await self._execute_request(route, auth, extra_params, start)
        result.endpoint_name = "fetch_url"

        # Handle auth failures with retry
        if result.status_code in (401, 403) and not result.retried:
            log.warning(f"[DirectFetch] Auth failure ({result.status_code}) on fetch_url. Attempting session refresh...")
            self.session_manager.invalidate()
            try:
                auth = await self.session_manager.get_auth_context()
                retry_result = await self._execute_request(route, auth, extra_params, time.monotonic())
                retry_result.endpoint_name = "fetch_url"
                retry_result.retried = True
                return retry_result
            except RuntimeError:
                pass  # Return original failure

        return result

    async def _execute_request(
        self,
        route: ResolvedRoute,
        auth: CartaAuthContext,
        extra_params: Optional[Dict[str, str]],
        start: float,
    ) -> DirectFetchResult:
        """Execute a single HTTP request."""
        url = route.url
        params = dict(route.params)
        if extra_params:
            params.update(extra_params)

        # Build headers — same as CartaReplayClient._execute_httpx
        headers = {
            "User-Agent": auth.user_agent,
            "Accept": "application/json, text/plain, */*",
            "X-CSRFToken": auth.csrf_token,
            "Referer": "https://app.carta.com",
        }

        # Strip CSRF for cross-subdomain requests (fund-admin)
        from urllib.parse import urlparse
        from services.providers.carta.utils.settings import settings
        base_netloc = urlparse(settings.app_base_url).netloc
        if urlparse(url).netloc != base_netloc:
            headers.pop("X-CSRFToken", None)
            headers.pop("Referer", None)

        try:
            client = await self._get_client()
            response = await client.get(
                url,
                headers=headers,
                cookies=auth.cookies,
                params=params if params else None,
            )
            latency = int((time.monotonic() - start) * 1000)
            content = response.text

            # Parse JSON
            payload = None
            if response.status_code == 200:
                try:
                    payload = response.json()
                except Exception:
                    payload = {"raw_text": content[:2000]}

            error = None
            if response.status_code != 200:
                resp_headers = dict(response.headers)
                if response.status_code != 400 and is_cloudflare(resp_headers, content):
                    error = "Cloudflare challenge detected. Use browser-based extraction for this endpoint."
                else:
                    classification = FailureClassifier.classify(response.status_code, content)
                    error = f"{classification.failure_type.value}: HTTP {response.status_code}"

            return DirectFetchResult(
                endpoint_name="",
                status_code=response.status_code,
                latency_ms=latency,
                payload=payload,
                error=error,
                url=url,
                shape_hash=generate_shape_hash(payload),
            )

        except httpx.TimeoutException:
            latency = int((time.monotonic() - start) * 1000)
            return DirectFetchResult(
                endpoint_name="",
                status_code=504,
                latency_ms=latency,
                error=f"Request timed out after {self.timeout}s",
                url=url,
            )
        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            return DirectFetchResult(
                endpoint_name="",
                status_code=500,
                latency_ms=latency,
                error=str(e),
                url=url,
            )

    async def download_file(self, url: str, output_path: str) -> bool:
        """Download a binary file from Carta and save it to output_path."""
        from services.providers.carta.utils.settings import settings
        import os
        from urllib.parse import urlparse
        
        # Ensure url is absolute
        if url.startswith("/"):
            url = f"{settings.app_base_url}{url}"
            
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        try:
            # 1. Get auth context
            auth = await self.session_manager.get_auth_context()
            
            # 2. Build headers
            headers = {
                "User-Agent": auth.user_agent,
                "Accept": "application/pdf,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Referer": "https://app.carta.com",
            }
            
            client = await self._get_client()
            
            log.info(f"[DirectFetch] Downloading PDF via HTTPX: {url}")
            response = await client.get(
                url,
                headers=headers,
                cookies=auth.cookies,
                follow_redirects=True
            )
            
            if response.status_code == 200 and "application/pdf" in response.headers.get("content-type", "").lower():
                with open(output_path, "wb") as f:
                    f.write(response.content)
                log.info(f"[DirectFetch] Successfully saved PDF via HTTPX ({len(response.content)} bytes) to {output_path}")
                return True
            else:
                log.warning(f"[DirectFetch] Failed to download PDF via HTTPX for {url}. Status: {response.status_code}, Content-Type: {response.headers.get('content-type')}")
                return False
        except Exception as e:
            log.error(f"[DirectFetch] HTTPX download error for {url}: {e}")
            return False

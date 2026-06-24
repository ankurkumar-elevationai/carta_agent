import os
import asyncio
import logging
import time
import hashlib
import json
import uuid
from enum import Enum
from datetime import datetime, timedelta
from typing import Dict, Optional, Union, Callable, Any, List
import httpx
from pydantic import BaseModel, Field

from .auth import CartaAuthContext
from .url_builder import URLBuilder

from dataclasses import dataclass
from typing import Set

@dataclass(slots=True)
class ReplayTarget:
    method: str
    url: str
    headers: Dict[str, str]
    body_hash: Optional[str]
    inferred_capabilities: Set[str]


log = logging.getLogger(__name__)

class CartaReplayStrategy(str, Enum):
    HTTPX = "httpx"
    API_REQUEST_CONTEXT = "api_request_context"
    BROWSER_FETCH = "browser_fetch"

class ReplayScenario(str, Enum):
    HTTPX_ONLY = "httpx_only"
    API_CONTEXT_ONLY = "api_context_only"
    BROWSER_FETCH_ONLY = "browser_fetch_only"
    AUTO_FALLBACK = "auto_fallback"
    SESSION_REFRESH = "session_refresh"

class BrowserHealth(str, Enum):
    ALIVE = "alive"
    DEGRADED = "degraded"
    DEAD = "dead"

class ReplayMode(str, Enum):
    DISCOVERY = "discovery"
    EXTRACTION = "extraction"
    DEBUG = "debug"

class ReplayFailureType(str, Enum):
    FORBIDDEN = "forbidden"
    CLOUDFLARE = "cloudflare"
    TIMEOUT = "timeout"
    SESSION_EXPIRED = "session_expired"
    PERMISSION_DENIED = "permission_denied"
    AUTH_FAILURE = "auth_failure"
    INVALID_REQUEST = "invalid_request"
    EXTERNAL_SERVICE = "external_service"
    CSRF_MISMATCH = "csrf_mismatch"
    NOT_FOUND = "not_found"
    UNPROCESSABLE = "unprocessable"
    UNKNOWN = "unknown"

class FailureClassification(BaseModel):
    failure_type: ReplayFailureType
    retryable: bool

class FailureClassifier:
    @staticmethod
    def classify(status_code: int, content: str = "") -> FailureClassification:
        if status_code == 401:
            return FailureClassification(failure_type=ReplayFailureType.AUTH_FAILURE, retryable=False)
        elif status_code == 403:
            return FailureClassification(failure_type=ReplayFailureType.FORBIDDEN, retryable=False)
        elif status_code == 404:
            return FailureClassification(failure_type=ReplayFailureType.NOT_FOUND, retryable=False)
        elif status_code == 422:
            return FailureClassification(failure_type=ReplayFailureType.UNPROCESSABLE, retryable=False)
        
        content_lower = content.lower()
        if "csrf" in content_lower and "mismatch" in content_lower:
            return FailureClassification(failure_type=ReplayFailureType.CSRF_MISMATCH, retryable=False)
        if "permission denied" in content_lower:
            return FailureClassification(failure_type=ReplayFailureType.PERMISSION_DENIED, retryable=False)
        if "invalid request" in content_lower:
            return FailureClassification(failure_type=ReplayFailureType.INVALID_REQUEST, retryable=False)
            
        if status_code in (429, 500, 502, 503, 504):
            return FailureClassification(failure_type=ReplayFailureType.EXTERNAL_SERVICE, retryable=True)
            
        return FailureClassification(failure_type=ReplayFailureType.UNKNOWN, retryable=True)

class ReplayDecision(BaseModel):
    selected_strategy: CartaReplayStrategy
    reason: str
    fallback_attempted: bool = False

class ReplayTierHealth(BaseModel):
    consecutive_failures: int = 0
    temporarily_disabled: bool = False
    disabled_until: Optional[datetime] = None

class ReplayResult(BaseModel):
    strategy_used: CartaReplayStrategy
    status_code: int
    latency_ms: int
    payload: Any = None
    trace_id: Optional[str] = None
    fallback_count: int = 0
    failure_type: Optional[ReplayFailureType] = None
    shape_hash: Optional[str] = None
    timeline: List[str] = Field(default_factory=list)
    x_carta_trace_id: Optional[str] = None

class ReplayException(Exception):
    """Custom exception raised when all replay tiers fail."""
    def __init__(self, message: str, final_url: Optional[str] = None, page_url: Optional[str] = None, strategy: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(message)
        self.final_url = final_url
        self.page_url = page_url
        self.strategy = strategy
        self.status_code = status_code

class ReplaySchemaDriftError(Exception):
    """Raised when the response shape has drifted from known intelligence."""
    pass

def is_cloudflare(headers: Dict[str, str], content: str) -> bool:
    headers_lower = {k.lower(): v.lower() for k, v in headers.items()}
    if "cf-ray" in headers_lower or ("server" in headers_lower and "cloudflare" in headers_lower["server"]):
        return True
    content_lower = content.lower()
    if "cf-browser-verification" in content_lower or "challenge-platform" in content_lower or "just a moment..." in content_lower:
        return True
    return False

def generate_shape_hash(payload: Any) -> Optional[str]:
    if not payload:
        return None
    try:
        if isinstance(payload, dict):
            keys = sorted(payload.keys())
        elif isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], dict):
            keys = sorted(payload[0].keys())
        else:
            return None
        keys_str = ",".join(keys)
        return hashlib.sha256(keys_str.encode("utf-8")).hexdigest()
    except Exception:
        return None

class ReplayPolicy(BaseModel):
    allow_internal: bool = False
    allow_admin_routes: bool = False
    require_same_origin: bool = True
    rate_limit_rps: int = 2

class CartaReplayClient:
    def __init__(
        self,
        page,
        auth_context: CartaAuthContext,
        mode: ReplayMode = ReplayMode.DISCOVERY,
        on_refresh_callback: Optional[Callable[[], Any]] = None,
        policy: Optional[ReplayPolicy] = None
    ):
        self.page = page
        self.auth_context = auth_context
        self.mode = mode
        self.on_refresh_callback = on_refresh_callback
        self.policy = policy or ReplayPolicy()
        
        # Endpoint-scoped circuit breakers
        self.circuit_breakers: Dict[str, ReplayTierHealth] = {}
        
        self.browser_health = BrowserHealth.ALIVE
        
        # Strategy success counters
        self.stats = {
            "httpx_attempts": 0,
            "httpx_successes": 0,
            "browser_fallback_count": 0
        }
        
        self._refresh_lock = asyncio.Lock()

    def _get_health(self, path: str) -> ReplayTierHealth:
        if path not in self.circuit_breakers:
            self.circuit_breakers[path] = ReplayTierHealth()
        return self.circuit_breakers[path]

    def _log_event(self, event_name: str, strategy: str, path: str, latency_ms: int, trace_id: str, extra: dict = None):
        event = {
            "event": event_name,
            "strategy": strategy,
            "endpoint": path,
            "latency_ms": latency_ms,
            "trace_id": trace_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        if extra:
            event.update(extra)
        log.info(f"[ReplayEvent] {json.dumps(event)}")

    async def get(
        self,
        target: ReplayTarget,
        params: Optional[dict] = None,
        tags: Optional[dict] = None,
        scenario: ReplayScenario = ReplayScenario.AUTO_FALLBACK
    ) -> ReplayResult:
        path = target.url

        
        # Enforce Replay Policy
        if not self.policy.allow_internal and ("/internal/" in path or "/_next/" in path):
            raise ReplayException(f"Policy Violation: Internal route access denied: {path}")
        if not self.policy.allow_admin_routes and ("/admin/" in path or "manage" in path):
            raise ReplayException(f"Policy Violation: Admin route access denied: {path}")
            
        trace_id = str(uuid.uuid4())
        tags = tags or {}
        
        # Clear expired circuit breaker logic
        health = self._get_health(path)
        if health.temporarily_disabled and health.disabled_until and datetime.utcnow() > health.disabled_until:
            health.temporarily_disabled = False
            health.consecutive_failures = 0
            health.disabled_until = None

        log.info(f"[ReplayClient][{trace_id}] Route GET {path} (scenario={scenario.value}) tags={tags}")

        if scenario == ReplayScenario.HTTPX_ONLY:
            return await self._execute_with_strategy(CartaReplayStrategy.HTTPX, path, params, trace_id, [])
        elif scenario == ReplayScenario.API_CONTEXT_ONLY:
            return await self._execute_with_strategy(CartaReplayStrategy.API_REQUEST_CONTEXT, path, params, trace_id, [])
        elif scenario == ReplayScenario.BROWSER_FETCH_ONLY:
            return await self._execute_with_strategy(CartaReplayStrategy.BROWSER_FETCH, path, params, trace_id, [])
        elif scenario == ReplayScenario.SESSION_REFRESH:
            await self._trigger_session_refresh(trace_id)
            return await self._execute_with_strategy(CartaReplayStrategy.HTTPX, path, params, trace_id, [])

        # AUTO_FALLBACK logic
        timeline = []
        decision = self._decide_strategy(target, path)

        try:
            return await self._execute_with_strategy(decision.selected_strategy, path, params, trace_id, timeline)
        except ReplayException as e:
            if decision.selected_strategy == CartaReplayStrategy.HTTPX:
                log.warning(f"[ReplayClient][{trace_id}] Tier-1 HTTPX failed: {e}. Dropping to Tier-2 API Context.")
                
                if self.browser_health == BrowserHealth.DEAD:
                    log.error(f"[ReplayClient][{trace_id}] Browser is DEAD. Skipping browser tiers.")
                    raise ReplayException(f"Failed to replay {path}: HTTPX failed and Browser is DEAD.")
                
                try:
                    res = await self._execute_with_strategy(CartaReplayStrategy.API_REQUEST_CONTEXT, path, params, trace_id, timeline)
                    res.fallback_count = 1
                    return res
                except ReplayException as e2:
                    log.warning(f"[ReplayClient][{trace_id}] Tier-2 API Context failed: {e2}. Dropping to Tier-3 Browser Fetch.")
                    if self.browser_health == BrowserHealth.DEAD:
                        log.error(f"[ReplayClient][{trace_id}] Browser is DEAD. Skipping Tier-3.")
                        raise ReplayException(f"Failed to replay {path} across all tiers.")
                        
                    try:
                        res = await self._execute_with_strategy(CartaReplayStrategy.BROWSER_FETCH, path, params, trace_id, timeline)
                        res.fallback_count = 2
                        return res
                    except ReplayException as e3:
                        log.error(f"[ReplayClient][{trace_id}] All replay tiers exhausted.")
                        raise ReplayException(f"Failed to replay {path} across all tiers.")
            elif decision.selected_strategy == CartaReplayStrategy.API_REQUEST_CONTEXT:
                self.stats["browser_fallback_count"] += 1
                log.warning(f"[ReplayClient][{trace_id}] Tier-2 API Context failed: {e}. Dropping to Tier-3 Browser Fetch.")
                
                if self.browser_health == BrowserHealth.DEAD:
                    log.error(f"[ReplayClient][{trace_id}] Browser is DEAD. Skipping Tier-3.")
                    raise ReplayException(f"Failed to replay {path} across all tiers.")
                    
                try:
                    res = await self._execute_with_strategy(CartaReplayStrategy.BROWSER_FETCH, path, params, trace_id, timeline)
                    res.fallback_count = 1
                    return res
                except ReplayException as e2:
                    log.error(f"[ReplayClient][{trace_id}] All replay tiers exhausted.")
                    raise ReplayException(f"Failed to replay {path} across all tiers.")
            raise

    def _decide_strategy(self, target: ReplayTarget, path: str) -> ReplayDecision:
        health = self._get_health(path)

        if "requires_browser" in target.inferred_capabilities:
            return ReplayDecision(
                selected_strategy=CartaReplayStrategy.API_REQUEST_CONTEXT,
                reason="Endpoint capability requires browser context, skipping HTTPX"
            )

        if health.temporarily_disabled:
            return ReplayDecision(
                selected_strategy=CartaReplayStrategy.API_REQUEST_CONTEXT,
                reason=f"HTTPX circuit breaker tripped until {health.disabled_until}",
                fallback_attempted=True
            )

        return ReplayDecision(
            selected_strategy=CartaReplayStrategy.HTTPX,
            reason="HTTPX healthy path"
        )

    async def _execute_with_strategy(
        self,
        strategy: CartaReplayStrategy,
        path: str,
        params: Optional[dict],
        trace_id: str,
        timeline: List[str]
    ) -> ReplayResult:
        start_time = time.monotonic()
        
        if strategy == CartaReplayStrategy.HTTPX:
            timeline.append("HTTPX_ATTEMPT")
            self.stats["httpx_attempts"] += 1
            res = await self._execute_httpx(path, params, trace_id, start_time)
            
            health = self._get_health(path)
            if res.status_code == 200:
                timeline.append("SUCCESS")
                health.consecutive_failures = 0
                self.stats["httpx_successes"] += 1
                res.timeline = timeline
                return res
            else:
                timeline.append("HTTPX_FAILED")
                health.consecutive_failures += 1
                if health.consecutive_failures >= 3:
                    health.temporarily_disabled = True
                    health.disabled_until = datetime.utcnow() + timedelta(minutes=5)
                
                if res.failure_type == ReplayFailureType.SESSION_EXPIRED:
                    refreshed = await self._trigger_session_refresh(trace_id)
                    if refreshed:
                        log.info(f"[ReplayClient][{trace_id}] Session refreshed. Retrying Tier-1...")
                        timeline.append("HTTPX_RETRY_AFTER_REFRESH")
                        retry_res = await self._execute_httpx(path, params, trace_id, time.monotonic())
                        retry_res.timeline = timeline
                        return retry_res
                
                # Classify failure and check if retryable
                classification = FailureClassifier.classify(res.status_code, str(res.payload) if res.payload else "")
                res.failure_type = classification.failure_type
                
                if not classification.retryable:
                    log.warning(f"[ReplayClient][{trace_id}] {classification.failure_type.value.upper()} on Tier-1. Terminal error, aborting fallback.")
                    res.timeline = timeline
                    return res
                    
                raise ReplayException(f"Tier-1 HTTPX returned retryable status: {res.status_code}", status_code=res.status_code)
                
        elif strategy == CartaReplayStrategy.API_REQUEST_CONTEXT:
            timeline.append("API_REQUEST_CONTEXT_ATTEMPT")
            try:
                res = await self._execute_api_request_context(path, params, trace_id, start_time)
                if res.status_code == 200:
                    timeline.append("SUCCESS")
                else:
                    timeline.append("API_REQUEST_CONTEXT_FAILED")
                    
                    classification = FailureClassifier.classify(res.status_code, str(res.payload) if res.payload else "")
                    res.failure_type = classification.failure_type
                    
                    if not classification.retryable:
                        log.warning(f"[ReplayClient][{trace_id}] {classification.failure_type.value.upper()} on Tier-2. Terminal error, aborting fallback.")
                        res.timeline = timeline
                        return res
                        
                    raise ReplayException(f"Tier-2 failed with retryable status: {res.status_code}", status_code=res.status_code)
                res.timeline = timeline
                return res
            except Exception as e:
                timeline.append("API_REQUEST_CONTEXT_FAILED")
                error_str = str(e)
                if "TargetClosedError" in error_str:
                    self.browser_health = BrowserHealth.DEGRADED
                elif "Browser closed" in error_str or "Connection closed" in error_str:
                    self.browser_health = BrowserHealth.DEAD
                raise
            
        elif strategy == CartaReplayStrategy.BROWSER_FETCH:
            timeline.append("BROWSER_FETCH_ATTEMPT")
            try:
                res = await self._execute_browser_fetch(path, params, trace_id, start_time)
                if res.status_code == 200:
                    timeline.append("SUCCESS")
                else:
                    timeline.append("BROWSER_FETCH_FAILED")
                    raise ReplayException(f"Tier-3 failed with status: {res.status_code}")
                res.timeline = timeline
                return res
            except Exception as e:
                timeline.append("BROWSER_FETCH_FAILED")
                error_str = str(e)
                if "TargetClosedError" in error_str:
                    self.browser_health = BrowserHealth.DEGRADED
                elif "Browser closed" in error_str or "Connection closed" in error_str:
                    self.browser_health = BrowserHealth.DEAD
                raise
            
        raise ReplayException(f"Unsupported strategy: {strategy}")

    async def _validate_browser_context(self):
        url = self.page.url
        if "about:blank" in url:
            raise ReplayException("Browser context invalid: page is about:blank", page_url=url)
        if "login" in url:
            raise ReplayException("Browser context invalid: page is on login domain", page_url=url)
        
        try:
            await self.page.wait_for_load_state("networkidle", timeout=1000)
        except Exception as e:
            log.warning(f"wait_for_load_state networkidle timed out or failed: {e}")

    async def _execute_httpx(self, path: str, params: Optional[dict], trace_id: str, start_time: float) -> ReplayResult:
        absolute_url = URLBuilder.build_api_url(path)
        log.info(f"[Replay] Final URL => {absolute_url}")
        
        base_url = self.page.url.split("/investors")[0] if "/investors" in self.page.url else URLBuilder.APP_BASE_URL
        
        headers = {
            "User-Agent": self.auth_context.user_agent,
            "Accept": "application/json, text/plain, */*",
            "X-CSRFToken": self.auth_context.csrf_token,
            "Referer": base_url,
        }
        
        from urllib.parse import urlparse
        if urlparse(absolute_url).netloc != urlparse(base_url).netloc:
            headers.pop("X-CSRFToken", None)
            headers.pop("Referer", None)
            headers.pop("Origin", None)
            log.info(f"[Replay] Stripping auth bounds for cross-subdomain API: {absolute_url}")
        
        async def _run():
            async with httpx.AsyncClient(timeout=10.0) as client:
                return await client.get(
                    absolute_url,
                    headers=headers,
                    cookies=self.auth_context.cookies,
                    params=params
                )
                
        try:
            # Explicit timeout guard
            response = await asyncio.wait_for(_run(), timeout=10.0)
            latency = int((time.monotonic() - start_time) * 1000)
            
            x_carta_trace_id = response.headers.get("x-carta-trace-id")
            
            content = response.text
            is_cf = is_cloudflare(dict(response.headers), content)
            
            failure = None
            if response.status_code != 200:
                if is_cf:
                    failure = ReplayFailureType.CLOUDFLARE
                elif response.status_code in (401, 403):
                    if "permission" in content.lower():
                        failure = ReplayFailureType.PERMISSION_DENIED
                    elif response.status_code == 401 or "auth" in content.lower():
                        failure = ReplayFailureType.AUTH_FAILURE
                    else:
                        failure = ReplayFailureType.SESSION_EXPIRED
                elif response.status_code == 400:
                    failure = ReplayFailureType.INVALID_REQUEST
                    log.warning(f"[ReplayClient] 400 Bad Request on {path}. Params: {params}")
                else:
                    failure = ReplayFailureType.FORBIDDEN
                    
            payload = None
            if response.status_code == 200:
                try:
                    payload = response.json()
                except Exception:
                    payload = {"raw_text": content[:1000]}

            self._log_event("replay_attempt", "httpx", path, latency, trace_id, {"status_code": response.status_code, "failure_type": failure})

            return ReplayResult(
                strategy_used=CartaReplayStrategy.HTTPX,
                status_code=response.status_code,
                latency_ms=latency,
                payload=payload,
                trace_id=trace_id,
                failure_type=failure,
                shape_hash=generate_shape_hash(payload),
                x_carta_trace_id=x_carta_trace_id
            )
            
        except Exception as e:
            latency = int((time.monotonic() - start_time) * 1000)
            self._log_event("replay_attempt", "httpx", path, latency, trace_id, {"error": str(e)})
            return ReplayResult(
                strategy_used=CartaReplayStrategy.HTTPX,
                status_code=500,
                latency_ms=latency,
                trace_id=trace_id,
                failure_type=ReplayFailureType.TIMEOUT,
            )

    async def _execute_api_request_context(self, path: str, params: Optional[dict], trace_id: str, start_time: float) -> ReplayResult:
        await self._validate_browser_context()
        absolute_url = URLBuilder.build_api_url(path)
        log.info(f"[Replay] Final URL => {absolute_url}")
        
        context = self.page.context
        query_str = ""
        
        req_headers = {
            "x-csrftoken": self.auth_context.csrf_token,
            "Accept": "application/json, text/plain, */*"
        }
        
        if params:
            from urllib.parse import urlencode, urlparse
            query_str = "?" + urlencode(params, doseq=True)
            
            base_url = self.page.url.split("/investors")[0] if "/investors" in self.page.url else URLBuilder.APP_BASE_URL
            if urlparse(absolute_url).netloc != urlparse(base_url).netloc:
                req_headers.pop("x-csrftoken", None)
                log.info(f"[Replay] Stripping x-csrftoken for cross-subdomain API context: {absolute_url}")
                
        full_url = f"{absolute_url}{query_str}"
        
        async def _run():
            return await context.request.get(
                full_url,
                headers=req_headers,
                timeout=20000
            )
            
        try:
            # Explicit timeout guard
            response = await asyncio.wait_for(_run(), timeout=20.0)
            latency = int((time.monotonic() - start_time) * 1000)
            status = response.status
            content = await response.text()
            
            x_carta_trace_id = response.headers.get("x-carta-trace-id")
            is_cf = is_cloudflare(response.headers, content)
            
            failure = None
            if status != 200:
                if is_cf:
                    failure = ReplayFailureType.CLOUDFLARE
                elif status in (401, 403):
                    failure = ReplayFailureType.SESSION_EXPIRED
                else:
                    failure = ReplayFailureType.FORBIDDEN
                    
            payload = None
            if status == 200:
                try:
                    payload = await response.json()
                except Exception:
                    payload = {"raw_text": content[:1000]}
                    
            self._log_event("replay_attempt", "api_request_context", path, latency, trace_id, {"status_code": status})

            return ReplayResult(
                strategy_used=CartaReplayStrategy.API_REQUEST_CONTEXT,
                status_code=status,
                latency_ms=latency,
                payload=payload,
                trace_id=trace_id,
                failure_type=failure,
                shape_hash=generate_shape_hash(payload),
                x_carta_trace_id=x_carta_trace_id
            )
            
        except Exception as e:
            latency = int((time.monotonic() - start_time) * 1000)
            self._log_event("replay_attempt", "api_request_context", path, latency, trace_id, {"error": str(e)})
            raise ReplayException(str(e), final_url=full_url, page_url=self.page.url, strategy="api_request_context")

    async def _execute_browser_fetch(self, path: str, params: Optional[dict], trace_id: str, start_time: float) -> ReplayResult:
        await self._validate_browser_context()
        absolute_url = URLBuilder.build_api_url(path)
        log.info(f"[Replay] Final URL => {absolute_url}")
        
        query_str = ""
        if params:
            from urllib.parse import urlencode
            query_str = "?" + urlencode(params, doseq=True)
            
        full_url = f"{absolute_url}{query_str}"
        csrf_token = self.auth_context.csrf_token
        
        fetch_js = """
            async ([url, csrf]) => {
                const headers = {
                    'Accept': 'application/json, text/plain, */*',
                    'x-csrftoken': csrf
                };
                try {
                    const response = await fetch(url, { headers });
                    const status = response.status;
                    const text = await response.text();
                    const xCartaTraceId = response.headers.get('x-carta-trace-id');
                    let json = null;
                    try { json = JSON.parse(text); } catch (e) {}
                    return { status, text, json, xCartaTraceId };
                } catch (err) {
                    return { status: 500, error: err.toString() };
                }
            }
        """
        
        try:
            # Explicit timeout guard
            res_dict = await asyncio.wait_for(self.page.evaluate(fetch_js, [full_url, csrf_token]), timeout=30.0)
            latency = int((time.monotonic() - start_time) * 1000)
            status = res_dict.get("status", 500)
            x_carta_trace_id = res_dict.get("xCartaTraceId")
            
            if status != 200:
                error_msg = res_dict.get("error") or res_dict.get("text", "")
                self._log_event("replay_attempt", "browser_fetch", path, latency, trace_id, {"status_code": status, "error": error_msg})
                raise ReplayException(f"Browser fetch failed (status {status}): {error_msg}", final_url=full_url, page_url=self.page.url, strategy="browser_fetch", status_code=status)
                
            payload = res_dict.get("json") or {"raw_text": res_dict.get("text", "")[:1000]}
            
            self._log_event("replay_attempt", "browser_fetch", path, latency, trace_id, {"status_code": status})

            return ReplayResult(
                strategy_used=CartaReplayStrategy.BROWSER_FETCH,
                status_code=status,
                latency_ms=latency,
                payload=payload,
                trace_id=trace_id,
                shape_hash=generate_shape_hash(payload),
                x_carta_trace_id=x_carta_trace_id
            )
            
        except Exception as e:
            latency = int((time.monotonic() - start_time) * 1000)
            self._log_event("replay_attempt", "browser_fetch", path, latency, trace_id, {"error": str(e)})
            raise ReplayException(str(e), final_url=full_url, page_url=self.page.url, strategy="browser_fetch")

    async def _trigger_session_refresh(self, trace_id: str) -> bool:
        if not self.on_refresh_callback:
            return False
            
        async with self._refresh_lock:
            log.info(f"[ReplayClient][{trace_id}] Session expired. Invoking re-authentication callback...")
            try:
                fresh_auth = await self.on_refresh_callback()
                if fresh_auth:
                    self.auth_context = fresh_auth
                    # Clear all breakers
                    self.circuit_breakers.clear()
                    log.info(f"[ReplayClient][{trace_id}] Session successfully updated to version {fresh_auth.version}!")
                    return True
            except Exception as e:
                log.error(f"[ReplayClient][{trace_id}] Reauthentication callback failed: {e}")
                
        return False

"""
services/providers/carta/api/route_registry.py
----------------------------------------------
API Route Registry — Maps platform endpoint names to concrete Carta backend
URL templates. Built automatically after a full discovery extraction and
persisted to disk for sub-second replay on subsequent requests.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

log = logging.getLogger(__name__)

# ── Defaults derived from the EAI Space I LLC extraction ─────────────
# These are the known URL patterns for Carta's internal APIs.
# They are used as seed templates and updated dynamically during discovery.

DEFAULT_ROUTE_TEMPLATES: Dict[str, dict] = {
    # ── Tier 1: Firm-level (no entity_id) ──
    "get_investments": {
        "url_template": "/api/investors/portfolio/firm/{org_id}/list_individual_portfolio_investments/{firm_id}/list/",
        "base": "app",
        "method": "GET",
        "requires_entity_id": False,
        "params": {},
        "category": "portfolio",
    },
    "get_investment_firm": {
        "url_template": "/api/investors/organization/{org_id}/address_api/",
        "base": "app",
        "method": "GET",
        "requires_entity_id": False,
        "params": {},
        "category": "investors",
    },
    # ── Tier 2: Entity-level (entity_id required) ──
    "get_investment_extra_info": {
        "url_template": "/api/corporations/{entity_id}/corporation_info/{entity_id}/",
        "base": "app",
        "method": "GET",
        "requires_entity_id": True,
        "params": {},
        "category": "cap_table",
    },
    "get_investment_valuations": {
        "url_template": "/api/investors/portfolio/fund/{firm_id}/entity/{entity_id}/tabs/",
        "base": "app",
        "method": "GET",
        "requires_entity_id": True,
        "params": {},
        "category": "valuations",
    },
    "get_capital_calls": {
        "url_template": "/api/investors/transactions/fund/{firm_id}/entity/{entity_id}/transactions/",
        "base": "app",
        "method": "GET",
        "requires_entity_id": True,
        "params": {},
        "category": "portfolio",
    },
    "get_investment_transactions": {
        "url_template": "/api/investors/transactions/fund/{firm_id}/entity/{entity_id}/transactions/",
        "base": "app",
        "method": "GET",
        "requires_entity_id": True,
        "params": {},
        "category": "portfolio",
    },
    "get_investment_certificates": {
        "url_template": "/partner-portfolios/{firm_id}/fund/{entity_id}/portfolio-entity-overview/",
        "base": "fund-admin",
        "method": "GET",
        "requires_entity_id": True,
        "params": {},
        "category": "portfolio",
    },
    # Documents
    "get_documents": {
        "url_template": "/api/investors/fund/{firm_id}/get_received_documents/sent_from/{entity_id}/",
        "base": "app",
        "method": "GET",
        "requires_entity_id": True,
        "params": {},
        "category": "portfolio",
    },
    # Fund-admin partner metrics (UUIDs)
    "get_partner_metrics": {
        "url_template": "/v2/partners/organization/{org_uuid}/fund/{fund_uuid}/metrics/",
        "base": "fund-admin",
        "method": "GET",
        "requires_entity_id": True,
        "params": {},
        "category": "portfolio",
    },
    "get_capital_account_summary": {
        "url_template": "/fund/{fund_uuid}/get-partner-capital-account-summary-v2-lp?fund_uuid={fund_uuid}&start_date={start_date}&end_date={end_date}&partner_id={partner_id}",
        "base": "fund-admin",
        "method": "GET",
        "requires_entity_id": True,
        "params": {},
        "category": "portfolio",
    },
    "get_investment_team": {
        "url_template": "/v2/partners/list-primary-partner-contacts/org/{org_uuid}/fund/{fund_uuid}",
        "base": "fund-admin",
        "method": "GET",
        "requires_entity_id": True,
        "params": {},
        "category": "portfolio",
    },
}

# Aliases: many platform endpoint names map to the same underlying route
_ENDPOINT_ALIASES = {
    "inv_investment": "get_investments",
    "inv_asset_extra_info": "get_investment_extra_info",
    "inv_asset_team": "get_investment_team",
    "inv_asset_valuation": "get_investment_valuations",
    "inv_cap_call": "get_capital_calls",
    "investment_log": "get_capital_calls",
    "inv_investment_transaction": "get_investment_transactions",
    "inv_investment_firm": "get_investment_firm",
    "inv_investment_focus": "get_investments",
    "inv_investment_sector": "get_investments",
    "inv_investment_certificate": "get_investment_certificates",
    "inv_investment_distribution_history": "get_capital_calls",
    "inv_liquidity_distribution": "get_capital_calls",
    "get_investment_log": "get_capital_calls",
    "get_investment_focus": "get_investments",
    "get_investment_sectors": "get_investments",
    "get_distribution_history": "get_capital_calls",
    "get_liquidity_distributions": "get_capital_calls",
}

BASE_URLS = {
    "app": "https://app.carta.com",
    "fund-admin": "https://fund-admin.app.carta.com",
}


@dataclass
class ResolvedRoute:
    """A fully resolved route ready for HTTP fetch."""
    url: str
    method: str
    params: Dict[str, str]
    category: str
    requires_entity_id: bool
    template_name: str


@dataclass
class EntityContext:
    """Stores the ID mappings needed to resolve URL templates."""
    firm_id: int
    org_id: Optional[int] = None
    entity_id: Optional[int] = None
    org_uuid: Optional[str] = None
    fund_uuid: Optional[str] = None
    commitment_uuid: Optional[str] = None
    partner_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class RouteRegistry:
    """
    Persistent registry mapping platform endpoint names → Carta API URL templates.
    
    Lifecycle:
    1. On first run, seeds with DEFAULT_ROUTE_TEMPLATES
    2. After a full extraction, updated with discovered URL patterns
    3. Persisted to disk as JSON for sub-second lookups
    """

    def __init__(self, registry_path: str = None):
        from ..utils.settings import settings
        project_root = Path(__file__).resolve().parents[4]  # openclaw_carta/
        self.registry_path = Path(registry_path) if registry_path else project_root / "output" / "api_route_registry.json"
        self.entity_cache_path = self.registry_path.parent / "entity_cache.json"
        self.routes: Dict[str, dict] = {}
        self.entity_cache: Dict[str, EntityContext] = {}
        self._last_updated: Optional[float] = None
        
        # Resolve project root and individual portfolio firm IDs
        self.project_root = project_root
        self.individual_firm_ids = {3288983}  # fallback default
        try:
            org_file = project_root / "config" / "resolved_organizations.json"
            if org_file.exists():
                with open(org_file, "r", encoding="utf-8") as f:
                    orgs = json.load(f)
                self.individual_firm_ids.update(int(o["firm_id"]) for o in orgs if o.get("firm_id"))
        except Exception as e:
            log.warning(f"[RouteRegistry] Failed to load individual portfolio firm IDs: {e}")

        self._load()

    def _load(self):
        """Load from disk, falling back to defaults."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.routes = data.get("routes", {})
                self._last_updated = data.get("last_updated")
                log.info(f"[RouteRegistry] Loaded {len(self.routes)} routes from {self.registry_path}")
            except Exception as e:
                log.warning(f"[RouteRegistry] Failed to load registry: {e}. Using defaults.")
                self.routes = dict(DEFAULT_ROUTE_TEMPLATES)
        else:
            log.info("[RouteRegistry] No registry file found. Seeding with defaults.")
            self.routes = dict(DEFAULT_ROUTE_TEMPLATES)
            self._last_updated = None

        # Load entity cache
        if self.entity_cache_path.exists():
            try:
                with open(self.entity_cache_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for key, ctx_data in raw.items():
                    self.entity_cache[key] = EntityContext(**ctx_data)
                log.info(f"[RouteRegistry] Loaded {len(self.entity_cache)} entity contexts from cache.")
            except Exception as e:
                log.warning(f"[RouteRegistry] Failed to load entity cache: {e}")

    def save(self):
        """Persist to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "routes": self.routes,
            "last_updated": time.time(),
            "route_count": len(self.routes),
        }
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log.info(f"[RouteRegistry] Saved {len(self.routes)} routes to {self.registry_path}")

        # Save entity cache
        if self.entity_cache:
            cache_data = {k: asdict(v) for k, v in self.entity_cache.items()}
            with open(self.entity_cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)

    def is_ready(self) -> bool:
        """Check if the registry has routes available."""
        return len(self.routes) > 0

    def is_stale(self, max_age_hours: float = 24.0) -> bool:
        """Check if the registry data is older than max_age_hours."""
        if self._last_updated is None:
            return True
        age_hours = (time.time() - self._last_updated) / 3600
        return age_hours > max_age_hours

    def resolve_alias(self, endpoint_name: str) -> str:
        """Resolve an endpoint alias to its canonical route name."""
        return _ENDPOINT_ALIASES.get(endpoint_name, endpoint_name)

    def lookup(self, endpoint_name: str, ctx: EntityContext) -> ResolvedRoute:
        """
        Resolve a platform endpoint name to a fully constructed URL.
        
        Args:
            endpoint_name: Platform endpoint name (e.g. "get_investments")
            ctx: EntityContext with the IDs needed for URL template substitution
            
        Returns:
            ResolvedRoute with the complete URL ready for HTTP fetch
            
        Raises:
            KeyError: If the endpoint is not in the registry
            ValueError: If entity_id is required but not provided
        """
        canonical = self.resolve_alias(endpoint_name)

        if canonical not in self.routes:
            raise KeyError(
                f"Endpoint '{endpoint_name}' (canonical: '{canonical}') not found in route registry. "
                f"Available: {list(self.routes.keys())}"
            )

        route = self.routes[canonical]
        template = route["url_template"]
        
        # Dynamic template selection for GP vs. Individual Investor portfolios
        is_individual = False
        try:
            if ctx.firm_id and int(ctx.firm_id) in self.individual_firm_ids:
                is_individual = True
        except (ValueError, TypeError):
            pass

        if canonical == "get_investments" and not is_individual:
            template = "/api/investors/portfolio/firm/{org_id}/list_firm_investments/"
        elif canonical == "get_investment_valuations" and not is_individual:
            template = "/api/investors/portfolio/firm/{org_id}/company/{entity_id}/firm_entity_tabs"
        elif canonical in ("get_capital_calls", "get_investment_transactions") and not is_individual:
            template = "/api/investors/transactions/firm/{firm_id}/entity/{entity_id}/transactions/"
            
        base = route.get("base", "app")

        # Check entity_id requirement
        if route.get("requires_entity_id") and not ctx.entity_id:
            raise ValueError(
                f"Endpoint '{endpoint_name}' requires entity_id but none was provided. "
                f"Call 'get_investments' first to resolve entity IDs."
            )

        url_path = template.format(
            firm_id=ctx.firm_id,
            org_id=ctx.org_id or ctx.firm_id,
            entity_id=ctx.entity_id or "",
            org_uuid=ctx.org_uuid or "",
            fund_uuid=ctx.fund_uuid or "",
            commitment_uuid=ctx.commitment_uuid or "",
            partner_id=ctx.partner_id or "",
            start_date=ctx.start_date or "",
            end_date=ctx.end_date or "",
        )

        base_url = BASE_URLS.get(base, BASE_URLS["app"])
        full_url = f"{base_url}{url_path}"

        return ResolvedRoute(
            url=full_url,
            method=route.get("method", "GET"),
            params=dict(route.get("params", {})),
            category=route.get("category", "unknown"),
            requires_entity_id=route.get("requires_entity_id", False),
            template_name=canonical,
        )

    def list_endpoints(self) -> List[dict]:
        """List all registered endpoints with their metadata."""
        results = []
        for name, route in self.routes.items():
            results.append({
                "name": name,
                "url_template": route["url_template"],
                "requires_entity_id": route.get("requires_entity_id", False),
                "category": route.get("category", "unknown"),
                "base": route.get("base", "app"),
            })
        return results

    def update_from_extraction(self, extracted_urls: List[dict], firm_id: int, entity_id: int = None, org_id: int = None):
        """
        Update the registry with real URL patterns discovered during a full extraction.
        
        Args:
            extracted_urls: List of dicts with 'url', 'category' keys from the extraction manifest
            firm_id: The firm ID used during extraction
            entity_id: The entity ID used during extraction (if any)
            org_id: The organization ID
        """
        updated = 0
        for entry in extracted_urls:
            url = entry.get("url", "")
            category = entry.get("category", "")

            if not url:
                continue

            # Try to templatize the URL by replacing known IDs with placeholders
            templatized = url
            base = "app"

            if "fund-admin.app.carta.com" in url:
                base = "fund-admin"
                templatized = url.split("fund-admin.app.carta.com")[-1]
            elif "app.carta.com" in url:
                templatized = url.split("app.carta.com")[-1]
            else:
                continue  # Skip external URLs

            # Apply regex-based templatization pattern matching
            patterns = [
                (r"/api/investors/portfolio/firm/(?:\d+|{[a-zA-Z_]+})/list_individual_portfolio_investments/(?:\d+|{[a-zA-Z_]+})/list/",
                 "/api/investors/portfolio/firm/{org_id}/list_individual_portfolio_investments/{firm_id}/list/"),
                (r"/api/investors/portfolio/firm/(?:\d+|{[a-zA-Z_]+})/list_firm_investments/",
                 "/api/investors/portfolio/firm/{org_id}/list_firm_investments/"),
                (r"/api/investors/organization/(?:\d+|{[a-zA-Z_]+})/address_api/",
                 "/api/investors/organization/{org_id}/address_api/"),
                (r"/api/corporations/(?:\d+|{[a-zA-Z_]+})/corporation_info/(?:\d+|{[a-zA-Z_]+})/",
                 "/api/corporations/{firm_id}/corporation_info/{entity_id}/"),
                (r"/api/investors/portfolio/fund/(?:\d+|{[a-zA-Z_]+})/entity/(?:\d+|{[a-zA-Z_]+})/tabs/",
                 "/api/investors/portfolio/fund/{firm_id}/entity/{entity_id}/tabs/"),
                (r"/api/investors/transactions/fund/(?:\d+|{[a-zA-Z_]+})/entity/(?:\d+|{[a-zA-Z_]+})/transactions/",
                 "/api/investors/transactions/fund/{firm_id}/entity/{entity_id}/transactions/"),
                (r"/partner-portfolios/(?:\d+|{[a-zA-Z_]+})/fund/(?:\d+|{[a-zA-Z_]+})/portfolio-entity-overview/",
                 "/partner-portfolios/{firm_id}/fund/{entity_id}/portfolio-entity-overview/"),
                (r"/api/investors/fund/(?:\d+|{[a-zA-Z_]+})/get_received_documents/sent_from/(?:\d+|{[a-zA-Z_]+})/",
                 "/api/investors/fund/{firm_id}/get_received_documents/sent_from/{entity_id}/"),
                (r"/v2/partners/organization/(?:[a-f0-9\-]+|{[a-zA-Z_]+})/fund/(?:[a-f0-9\-]+|{[a-zA-Z_]+})/metrics/",
                 "/v2/partners/organization/{org_uuid}/fund/{fund_uuid}/metrics/"),
                (r"/v2/partners/list-primary-partner-contacts/org/(?:[a-f0-9\-]+|{[a-zA-Z_]+})/fund/(?:[a-f0-9\-]+|{[a-zA-Z_]+})",
                 "/v2/partners/list-primary-partner-contacts/org/{org_uuid}/fund/{fund_uuid}"),
            ]
            for pattern, replacement in patterns:
                if re.search(pattern, templatized):
                    templatized = re.sub(pattern, replacement, templatized)
                    break

            needs_entity = "{entity_id}" in templatized
            if entity_id and str(entity_id) in templatized:
                templatized = templatized.replace(str(entity_id), "{entity_id}")
                needs_entity = True
            if firm_id and str(firm_id) in templatized:
                templatized = templatized.replace(str(firm_id), "{firm_id}")
            if org_id and str(org_id) in templatized:
                templatized = templatized.replace(str(org_id), "{org_id}")

            # Determine which endpoint this maps to (by category + URL keywords)
            endpoint_name = self._classify_url_to_endpoint(templatized, category)
            if endpoint_name and endpoint_name in self.routes:
                old_template = self.routes[endpoint_name].get("url_template", "")
                if old_template != templatized:
                    log.info(f"[RouteRegistry] Updated '{endpoint_name}': {old_template} → {templatized}")
                    self.routes[endpoint_name]["url_template"] = templatized
                    self.routes[endpoint_name]["base"] = base
                    self.routes[endpoint_name]["requires_entity_id"] = needs_entity
                    updated += 1

        if updated:
            log.info(f"[RouteRegistry] Updated {updated} route(s) from extraction data.")
            self.save()

    def cache_entity_context(self, company_name: str, ctx: EntityContext):
        """Cache entity context for a company for fast subsequent lookups."""
        self.entity_cache[company_name.lower().strip()] = ctx
        self.save()

    def get_cached_entity_context(self, company_name: str) -> Optional[EntityContext]:
        """Retrieve cached entity context for a company."""
        return self.entity_cache.get(company_name.lower().strip())

    def _classify_url_to_endpoint(self, url_path: str, category: str) -> Optional[str]:
        """Map a URL path to a platform endpoint name based on keywords."""
        path_lower = url_path.lower()

        patterns = {
            "list_individual_portfolio_investments": "get_investments",
            "list_firm_investments": "get_investments",
            "corporation_info": "get_investment_extra_info",
            "address_api": "get_investment_firm",
            "transactions": "get_capital_calls",
            "get_received_documents": "get_documents",
            "portfolio-entity-overview": "get_investment_certificates",
            "list-primary-partner-contacts": "get_investment_team",
            "tabs": "get_investment_valuations",
            "metrics": "get_partner_metrics",
        }

        for keyword, endpoint in patterns.items():
            if keyword in path_lower:
                return endpoint

        return None

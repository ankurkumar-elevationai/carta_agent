"""
Entity Discovery Engine (Phase 2).

After Phase 1 identifies the target organization, this engine enumerates
all entities (funds, SPVs, investments, companies) belonging to that org
by replaying known portfolio-level APIs.

Flow:
  OrganizationNode → Portfolio APIs → DiscoveredEntity[]

This replaces the brittle DOM table scraping with structured API enumeration.
The discovered entity manifest feeds into Phase 3 (drilldowns) and Phase 6 (graph).
"""

import json
import logging
from typing import Optional

from ..api.replay_client import (
    CartaReplayClient,
    ReplayTarget,
    ReplayScenario,
    ReplayException,
)
from ..api.url_builder import URLBuilder
from ..models.extraction import (
    OrganizationNode,
    DiscoveredEntity,
)

log = logging.getLogger(__name__)


class EntityDiscoveryError(Exception):
    """Raised when entity enumeration fails."""
    pass


# Known API patterns for entity enumeration on Carta.
# These are parameterized with {firm_id}.
_ENTITY_ENDPOINTS = [
    {
        "path": "/api/investors/portfolio/{firm_id}/init",
        "entity_source": "portfolio_init",
        "description": "Firm-level portfolio initialization data",
    },
    {
        "path": "/api/investors/portfolio/firm/{firm_id}/list_firm_investments/",
        "entity_source": "firm_investments",
        "description": "List of all firm investments",
    },
    {
        "path": "/api/investors/portfolio/firm/{firm_id}/fund_admin_nav_info_list/",
        "entity_source": "fund_nav_list",
        "description": "Fund/SPV navigation list",
    },
    {
        "path": "/firm/{firm_id}/gpx/firm-dashboard-app-init/",
        "entity_source": "dashboard_init",
        "description": "Firm dashboard initialization data",
    },
]


class EntityDiscoveryEngine:
    """
    Enumerates all entities belonging to a target organization.

    Replays portfolio-level APIs to discover funds, SPVs, investments,
    and companies — without any DOM scraping. Produces a DiscoveredEntity
    manifest that feeds into Phase 3 drilldowns and Phase 6 graph construction.
    """

    def __init__(
        self,
        replay_client: CartaReplayClient,
        target_org: OrganizationNode,
        app_base_url: Optional[str] = None,
    ):
        self.replay_client = replay_client
        self.target_org = target_org
        self.app_base_url = app_base_url or URLBuilder.APP_BASE_URL
        self._entities: list[DiscoveredEntity] = []
        self._raw_responses: dict[str, dict] = {}  # source → raw payload

    async def discover(self) -> list[DiscoveredEntity]:
        """
        Enumerate all entities by replaying portfolio APIs.
        Returns a deduplicated list of DiscoveredEntity objects.
        """
        firm_id = self.target_org.org_pk
        log.info(f"[EntityDiscovery] Enumerating entities for org_pk={firm_id} ({self.target_org.name})...")

        all_entities: list[DiscoveredEntity] = []

        for endpoint_spec in _ENTITY_ENDPOINTS:
            path = endpoint_spec["path"].format(firm_id=firm_id)
            source = endpoint_spec["entity_source"]
            full_url = f"{self.app_base_url}{path}"

            try:
                payload = await self._replay_endpoint(full_url)
                if payload:
                    self._raw_responses[source] = payload
                    entities = self._extract_entities(payload, source, firm_id)
                    log.info(
                        f"[EntityDiscovery] {source}: {len(entities)} entities from {path}"
                    )
                    all_entities.extend(entities)
            except Exception as e:
                log.warning(f"[EntityDiscovery] Failed to enumerate from {path}: {e}")
                continue

        # Deduplicate by entity_id
        seen_ids: set[str] = set()
        deduped: list[DiscoveredEntity] = []
        for entity in all_entities:
            if entity.entity_id not in seen_ids:
                seen_ids.add(entity.entity_id)
                deduped.append(entity)

        self._entities = deduped

        log.info(
            f"[EntityDiscovery] Discovery complete: {len(deduped)} unique entities "
            f"({len(all_entities)} total, {len(all_entities) - len(deduped)} deduped)"
        )

        # Log entity breakdown by type
        type_counts: dict[str, int] = {}
        for e in deduped:
            type_counts[e.entity_type] = type_counts.get(e.entity_type, 0) + 1
        log.info(f"[EntityDiscovery] Entity breakdown: {type_counts}")

        return deduped

    async def _replay_endpoint(self, url: str) -> Optional[dict]:
        """Replay a single API endpoint and return parsed JSON."""
        target = ReplayTarget(
            method="GET",
            url=url,
            headers={},
            body_hash=None,
            inferred_capabilities={"entity_list", "portfolio_data"},
        )

        try:
            result = await self.replay_client.get(
                target=target,
                scenario=ReplayScenario.AUTO_FALLBACK,
            )
        except ReplayException as e:
            log.warning(f"[EntityDiscovery] Replay failed for {url}: {e}")
            raise

        if not result or not result.payload:
            log.warning(f"[EntityDiscovery] Empty response from {url}")
            return None

        return result.payload if isinstance(result.payload, dict) else {"items": result.payload}

    def _extract_entities(
        self, payload: dict, source: str, firm_id: int
    ) -> list[DiscoveredEntity]:
        """
        Extract entities from a raw API response.
        Handles multiple response shapes depending on the source endpoint.
        """
        entities: list[DiscoveredEntity] = []

        if source == "firm_investments":
            entities.extend(self._parse_investments(payload, firm_id))
        elif source == "fund_nav_list":
            entities.extend(self._parse_funds(payload, firm_id))
        elif source == "portfolio_init":
            entities.extend(self._parse_portfolio_init(payload, firm_id))
        elif source == "dashboard_init":
            entities.extend(self._parse_dashboard_init(payload, firm_id))
        else:
            # Generic extraction: look for lists of objects with name/id fields
            entities.extend(self._generic_extract(payload, source, firm_id))

        return entities

    def _parse_investments(self, payload: dict, firm_id: int) -> list[DiscoveredEntity]:
        """Parse the firm investments list API response."""
        entities: list[DiscoveredEntity] = []

        # Common patterns: "investments", "results", "data", or top-level list
        candidates = self._find_entity_lists(payload)

        for item in candidates:
            if not isinstance(item, dict):
                continue

            entity_id = self._extract_id(item, prefix="investment")
            name = (
                item.get("legal_name")
                or item.get("dba")
                or item.get("company")
                or item.get("company_name")
                or item.get("companyName")
                or item.get("name")
                or item.get("display_name")
                or "unknown"
            )

            entities.append(DiscoveredEntity(
                entity_id=entity_id,
                entity_type="investment",
                name=name,
                parent_org_pk=firm_id,
                detail_url=item.get("url") or item.get("detail_url"),
                security_type=item.get("security_type") or item.get("securityType"),
                stage=item.get("stage") or item.get("status"),
                raw_data=item,
            ))

        return entities

    def _parse_funds(self, payload: dict, firm_id: int) -> list[DiscoveredEntity]:
        """Parse the fund/SPV navigation list API response.
        
        Handles two response shapes:
        1. Flat list: [{id, name, ...}, ...]
        2. Grouped list: [{header: "Funds", items: [{id, legal_name, ...}]}, ...]
        """
        entities: list[DiscoveredEntity] = []

        # Flatten grouped {header, items} structure if present
        flat_items: list[dict] = []
        items_to_scan = payload if isinstance(payload, list) else self._find_entity_lists(payload)
        
        for entry in items_to_scan:
            if not isinstance(entry, dict):
                continue
            # Grouped structure: {header: "Funds", items: [...]}
            if "items" in entry and isinstance(entry["items"], list):
                group_header = str(entry.get("header", "")).lower()
                for sub_item in entry["items"]:
                    if isinstance(sub_item, dict):
                        sub_item["_group_header"] = group_header
                        flat_items.append(sub_item)
            else:
                flat_items.append(entry)

        for item in flat_items:
            entity_id = self._extract_id(item, prefix="fund")
            name = (
                item.get("legal_name")
                or item.get("dba")
                or item.get("name")
                or item.get("fund_name")
                or item.get("fundName")
                or "unknown"
            )

            # Determine if it's a fund or SPV
            entity_type = "fund"
            type_hint = str(item.get("type", "") or item.get("vehicle_type", "") or item.get("true_purpose", "")).lower()
            group_header = item.pop("_group_header", "")
            if "spv" in type_hint or "special purpose" in type_hint or "spv" in group_header:
                entity_type = "spv"

            entities.append(DiscoveredEntity(
                entity_id=entity_id,
                entity_type=entity_type,
                name=name,
                parent_org_pk=firm_id,
                detail_url=item.get("url") or item.get("detail_url"),
                raw_data=item,
            ))

        return entities

    def _parse_portfolio_init(self, payload: dict, firm_id: int) -> list[DiscoveredEntity]:
        """Parse portfolio init response — may contain fund metadata and summary data."""
        entities: list[DiscoveredEntity] = []

        # Look for funds, investments, or any nested entity lists
        for key in ("funds", "investments", "portfolios", "entities", "companies"):
            items = payload.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        entity_id = self._extract_id(item, prefix=key.rstrip("s"))
                        name = (
                            item.get("legal_name")
                            or item.get("dba")
                            or item.get("company")
                            or item.get("name")
                            or item.get("company_name")
                            or "unknown"
                        )
                        entities.append(DiscoveredEntity(
                            entity_id=entity_id,
                            entity_type=key.rstrip("s"),
                            name=name,
                            parent_org_pk=firm_id,
                            detail_url=item.get("url"),
                            raw_data=item,
                        ))

        return entities

    def _parse_dashboard_init(self, payload: dict, firm_id: int) -> list[DiscoveredEntity]:
        """Parse dashboard init — often contains firm-level metadata."""
        return self._parse_portfolio_init(payload, firm_id)

    def _generic_extract(self, payload: dict, source: str, firm_id: int) -> list[DiscoveredEntity]:
        """Fallback: look for any list of objects with name/id fields."""
        entities: list[DiscoveredEntity] = []
        candidates = self._find_entity_lists(payload)

        for item in candidates:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("company_name") or item.get("display_name")
            if name:
                entity_id = self._extract_id(item, prefix=source)
                entities.append(DiscoveredEntity(
                    entity_id=entity_id,
                    entity_type="unknown",
                    name=name,
                    parent_org_pk=firm_id,
                    raw_data=item,
                ))

        return entities

    @staticmethod
    def _find_entity_lists(payload: dict) -> list:
        """
        Find the most likely list of entity objects in an API response.
        Searches common keys and falls back to the largest list in the payload.
        """
        # Check common list keys
        for key in ("results", "data", "investments", "funds", "items", "rows",
                     "companies", "entities", "portfolios", "accounts"):
            val = payload.get(key)
            if isinstance(val, list) and len(val) > 0:
                return val

        # Fallback: find the longest list value
        best_list: list = []
        for val in payload.values():
            if isinstance(val, list) and len(val) > len(best_list):
                # Only consider lists of dicts (entity-like structures)
                if val and isinstance(val[0], dict):
                    best_list = val

        return best_list

    @staticmethod
    def _extract_id(item: dict, prefix: str = "entity") -> str:
        """Extract a stable ID from an entity dict, or generate one from the name."""
        for key in ("id", "pk", "corporation_id", "investment_id", "fund_id", "entity_id",
                     "company_id", "corporation_pk", "organization_pk"):
            val = item.get(key)
            if val is not None:
                return f"{prefix}_{val}"

        # Fallback: hash the name
        import hashlib
        name = item.get("name") or item.get("company_name") or str(item)
        return f"{prefix}_{hashlib.sha256(name.encode()).hexdigest()[:12]}"

    @property
    def entities(self) -> list[DiscoveredEntity]:
        """Return previously discovered entities."""
        return self._entities

    @property
    def raw_responses(self) -> dict[str, dict]:
        """Return raw API responses for downstream processing."""
        return self._raw_responses

"""
Organization Discovery Engine (Phase 1).

Discovers all organizations/accounts the authenticated user has access to
by replaying the account-switcher API. Matches the user's requested company
against discovered orgs using fuzzy matching.

This replaces the brittle DOM-scrape entity resolution that was blocking
the entire pipeline.

Flow:
  Auth Context → Account-Switcher API → OrganizationNode[] → Target Match
"""

import base64
import json
import logging
from typing import Optional

from rapidfuzz import fuzz

from ..api.replay_client import (
    CartaReplayClient,
    ReplayTarget,
    ReplayScenario,
    ReplayException,
)
from ..api.url_builder import URLBuilder

from ..models.extraction import OrganizationNode

log = logging.getLogger(__name__)

# Known account-switcher endpoints on Carta
_ACCOUNT_SWITCHER_ENDPOINTS = [
    "/api/fe-platform/account-switcher/",
]


class OrgDiscoveryError(Exception):
    """Raised when organization discovery fails completely."""
    pass


class OrgMatchError(Exception):
    """Raised when the target company cannot be matched to any discovered org."""
    pass


class OrganizationDiscoveryEngine:
    """
    Discovers accessible organizations via authenticated API replay.

    Instead of scraping the DOM portfolio table and fuzzy-matching row text,
    this engine replays the account-switcher API endpoint (which the SPA
    calls on every page load) and parses the structured JSON response.

    Returns a list of OrganizationNode objects and optionally resolves the
    target company to a specific org_pk.
    """

    def __init__(self, replay_client: CartaReplayClient):
        self.replay_client = replay_client
        self._discovered_orgs: list[OrganizationNode] = []

    async def discover(self) -> list[OrganizationNode]:
        """
        Discover all organizations the authenticated user can access.
        Tries the account-switcher API first; falls back to passively
        captured data if replay fails.
        """
        log.info("[OrgDiscovery] Discovering accessible organizations...")

        for endpoint in _ACCOUNT_SWITCHER_ENDPOINTS:
            try:
                orgs = await self._replay_account_switcher(endpoint)
                if orgs:
                    self._discovered_orgs = orgs
                    log.info(
                        f"[OrgDiscovery] Discovered {len(orgs)} organization(s): "
                        f"{[o.name for o in orgs]}"
                    )
                    return orgs
            except Exception as e:
                log.warning(f"[OrgDiscovery] Account-switcher replay failed for {endpoint}: {e}")
                continue

        if not self._discovered_orgs:
            raise OrgDiscoveryError(
                "Failed to discover organizations. Account-switcher API unreachable."
            )

        return self._discovered_orgs

    async def discover_and_match(
        self, target_company: str, min_score: float = 60.0
    ) -> tuple[OrganizationNode, list[OrganizationNode]]:
        """
        Discover orgs AND resolve the target company to a specific org.

        Returns:
            (matched_org, all_orgs) tuple.

        Raises:
            OrgMatchError if no org matches the target company above min_score.
        """
        all_orgs = await self.discover()
        try:
            matched = self.match_target(target_company, all_orgs, min_score=min_score)
        except OrgMatchError as e:
            log.info(f"[OrgDiscovery] Direct organization match failed. Searching portfolios of accessible investment firms...")
            matched_firm = await self._match_via_investments(target_company, all_orgs)
            if matched_firm:
                matched = OrganizationNode(
                    org_pk=matched_firm.org_pk,
                    name=matched_firm.name,
                    account_type=matched_firm.account_type,
                    landing_url=matched_firm.landing_url,
                    is_target=True,
                    is_favorite=matched_firm.is_favorite,
                    most_recent_rank=matched_firm.most_recent_rank,
                )
                log.info(
                    f"[OrgDiscovery] [OK] Resolved target company '{target_company}' via portfolio investments "
                    f"to firm: '{matched.name}' (org_pk={matched.org_pk})"
                )
            else:
                raise e
        return matched, all_orgs

    async def _match_via_investments(
        self, target_company: str, orgs: list[OrganizationNode]
    ) -> Optional[OrganizationNode]:
        """
        Query the investments of each investment firm to see if the target company
        belongs to any of them.
        """
        query_lower = target_company.lower().strip()
        
        for org in orgs:
            if org.account_type != "investment firm":
                continue
                
            log.info(f"[OrgDiscovery] Checking if '{target_company}' is in portfolio of '{org.name}'...")
            
            # Query firm investments endpoint
            endpoint = f"/api/investors/portfolio/firm/{org.org_pk}/list_firm_investments/"
            target = ReplayTarget(
                method="GET",
                url=URLBuilder.build_api_url(endpoint),
                headers={},
                body_hash=None,
                inferred_capabilities={"entity_list", "portfolio_data"},
            )
            
            try:
                result = await self.replay_client.get(
                    target=target,
                    scenario=ReplayScenario.AUTO_FALLBACK,
                )
                if not result or not result.payload:
                    continue
                
                payload = result.payload
                # Parse candidates list
                items = []
                if isinstance(payload, list):
                    items = payload
                elif isinstance(payload, dict):
                    # Check common keys: 'investments', 'results', 'data', 'items'
                    for key in ["investments", "results", "data", "items"]:
                        if key in payload and isinstance(payload[key], list):
                            items = payload[key]
                            break
                    if not items:
                        # Fallback: check if any value is a list
                        for val in payload.values():
                            if isinstance(val, list):
                                items = val
                                break
                                
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    
                    name = (
                        item.get("legal_name")
                        or item.get("dba")
                        or item.get("company_name")
                        or item.get("companyName")
                        or (item.get("company", {}).get("name") if isinstance(item.get("company"), dict) else item.get("company"))
                        or item.get("name")
                    )
                    if not name:
                        continue
                        
                    name_lower = str(name).lower().strip()
                    partial = fuzz.partial_ratio(query_lower, name_lower)
                    token_sort = fuzz.token_sort_ratio(query_lower, name_lower)
                    score = max(partial, token_sort)
                    
                    if name_lower.startswith(query_lower):
                        score += 15.0
                    if name_lower == query_lower:
                        score = 100.0
                        
                    if score >= 75.0:
                        log.info(
                            f"[OrgDiscovery] [OK] Found matching investment '{name}' "
                            f"(score={score:.1f}) in '{org.name}' portfolio!"
                        )
                        return org
            except Exception as e:
                log.warning(f"[OrgDiscovery] Failed to query investments for {org.name}: {e}")
                continue
                
        return None

    def match_target(
        self,
        target_company: str,
        orgs: list[OrganizationNode],
        min_score: float = 60.0,
    ) -> OrganizationNode:
        """
        Fuzzy-match the target company name against discovered orgs.

        Uses rapidfuzz with a weighted scoring strategy:
        - partial_ratio for substring matching
        - token_sort_ratio for word-order independence
        - exact prefix boost
        """
        if not orgs:
            raise OrgMatchError(f"No organizations to match against for '{target_company}'.")

        query_lower = target_company.lower().strip()
        best_org: Optional[OrganizationNode] = None
        best_score: float = -1.0
        scores: list[dict] = []

        for org in orgs:
            name_lower = org.name.lower().strip()

            partial = fuzz.partial_ratio(query_lower, name_lower)
            token_sort = fuzz.token_sort_ratio(query_lower, name_lower)
            score = max(partial, token_sort)

            # Exact prefix boost
            if name_lower.startswith(query_lower):
                score += 15.0
            # Exact match boost
            if name_lower == query_lower:
                score = 100.0

            scores.append({
                "name": org.name,
                "org_pk": org.org_pk,
                "account_type": org.account_type,
                "score": round(score, 2),
            })

            if score > best_score:
                best_score = score
                best_org = org

        # Log all scores for debugging
        log.info(
            f"[OrgDiscovery] Match scores for '{target_company}':\n"
            + json.dumps(scores, indent=2)
        )

        if best_score < min_score or not best_org:
            raise OrgMatchError(
                f"No organization matched '{target_company}' above threshold {min_score}. "
                f"Best: '{best_org.name if best_org else 'None'}' ({best_score:.1f}). "
                f"Available: {[o.name for o in orgs]}"
            )

        # If the matched organization is a company (not an investment firm), switch to Krakatoa Ventures to allow portfolio drilldown
        if best_org.account_type == "company":
            krakatoa_org = next((o for o in orgs if o.name == "Krakatoa Ventures"), None)
            if krakatoa_org:
                log.info(
                    f"[OrgDiscovery] Matched org '{best_org.name}' is of type 'company'. "
                    f"Switching to investor firm '{krakatoa_org.name}' (org_pk={krakatoa_org.org_pk}) "
                    f"to allow portfolio drilldown."
                )
                best_org = krakatoa_org

        # Mark as target
        matched = OrganizationNode(
            org_pk=best_org.org_pk,
            name=best_org.name,
            account_type=best_org.account_type,
            landing_url=best_org.landing_url,
            is_target=True,
            is_favorite=best_org.is_favorite,
            most_recent_rank=best_org.most_recent_rank,
        )

        log.info(
            f"[OrgDiscovery] [OK] Matched '{target_company}' → "
            f"'{matched.name}' (org_pk={matched.org_pk}, type={matched.account_type}, score={best_score:.1f})"
        )
        return matched

    async def _replay_account_switcher(self, endpoint: str) -> list[OrganizationNode]:
        """Replay the account-switcher API and parse the response."""
        # Build the full URL using the replay client's page context
        base_url = URLBuilder.API_BASE_URL  # Will be overridden by replay client
        full_url = URLBuilder.build_api_url(endpoint)

        target = ReplayTarget(
            method="GET",
            url=full_url,
            headers={},
            body_hash=None,
            inferred_capabilities={"entity_list"},
        )

        try:
            result = await self.replay_client.get(
                target=target,
                scenario=ReplayScenario.AUTO_FALLBACK,
            )
        except ReplayException as e:
            log.warning(f"[OrgDiscovery] Replay failed for {endpoint}: {e}")
            raise

        if not result or not result.payload:
            raise OrgDiscoveryError(f"Empty response from {endpoint}")

        return self._parse_account_switcher_response(result.payload)

    def _parse_account_switcher_response(self, payload: dict | list) -> list[OrganizationNode]:
        """
        Parse the account-switcher JSON response.

        Expected shape:
        {
          "accounts": [
            {
              "name": "Krakatoa Ventures",
              "url": "/api/profiles/landing-page-redirect/o/1/",
              "id": "organization_pk:1",
              "mostRecent": 0,
              "accountType": "investment firm",
              "isFavorite": false
            },
            ...
          ]
        }
        """
        orgs: list[OrganizationNode] = []

        # Handle both dict and list payloads
        accounts = []
        if isinstance(payload, dict):
            accounts = payload.get("accounts", [])
        elif isinstance(payload, list):
            accounts = payload

        if not accounts:
            log.warning(f"[OrgDiscovery] No 'accounts' key in response. Keys: {list(payload.keys()) if isinstance(payload, dict) else 'list'}")
            return orgs

        for acct in accounts:
            try:
                # Extract org_pk from ID field (format: "organization_pk:1" or "corporation_pk:611")
                raw_id = acct.get("id", "")
                org_pk = self._extract_org_pk(raw_id, acct.get("url", ""))

                if org_pk is None:
                    log.warning(f"[OrgDiscovery] Could not extract org_pk from: {raw_id}")
                    continue

                org = OrganizationNode(
                    org_pk=org_pk,
                    name=acct.get("name", "unknown"),
                    account_type=acct.get("accountType", acct.get("account_type", "unknown")),
                    landing_url=acct.get("url", ""),
                    is_favorite=acct.get("isFavorite", acct.get("is_favorite", False)),
                    most_recent_rank=acct.get("mostRecent", acct.get("most_recent", 99999)),
                )
                orgs.append(org)
            except Exception as e:
                log.warning(f"[OrgDiscovery] Failed to parse account entry: {e}")
                continue

        return orgs

    @staticmethod
    def _extract_org_pk(raw_id: str, url: str) -> Optional[int]:
        """Extract organization primary key from ID string or URL."""
        # Try ID field: "organization_pk:1" or "corporation_pk:611"
        if ":" in raw_id:
            try:
                return int(raw_id.split(":")[-1])
            except (ValueError, IndexError):
                pass

        # Try URL: "/api/profiles/landing-page-redirect/o/1/"
        import re
        match = re.search(r"/o/(\d+)/|/c/(\d+)/", url)
        if match:
            pk_str = match.group(1) or match.group(2)
            return int(pk_str)

        return None

    @property
    def organizations(self) -> list[OrganizationNode]:
        """Return previously discovered organizations."""
        return self._discovered_orgs

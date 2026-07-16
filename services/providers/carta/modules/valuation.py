from typing import Dict, Any, Set
import logging
from .base import ExtractionModule

log = logging.getLogger(__name__)

class ValuationModule(ExtractionModule):
    @property
    def name(self) -> str:
        return "valuation"

    @property
    def dependencies(self) -> Set[str]:
        return {"investment"}

    @property
    def ttl_seconds(self) -> int:
        return 43200  # 12 hours

    async def extract(self, context: Any, dependency_data: Dict[str, Any]) -> Dict[str, Any]:
        log.info("[ValuationModule] Starting extraction...")
        direct_fetch = context["direct_fetch"]
        firm_id = context["firm_id"]
        entity_id = context.get("entity_id")
        
        if not entity_id:
            log.warning("[ValuationModule] entity_id not in context, resolving from investments...")
            # Try to get entity_id from investment data (e.g. fund-transactions or overview fields)
            investments = dependency_data.get("investment")
            if isinstance(investments, dict):
                # Inspect overview for entity-id
                overview = investments.get("overview", {})
                if isinstance(overview, dict):
                    entity_id = overview.get("entity-id") or overview.get("entity_id")
                    
        result = await direct_fetch.fetch(
            endpoint_name="get_investment_valuations",
            firm_id=firm_id,
            entity_id=entity_id
        )
        
        if result.error and result.status_code >= 400:
            raise RuntimeError(f"Failed to fetch valuations: {result.error}")
            
        tabs_payload = result.payload
        valuations_payload = None
        ledger_payload = None
        holdings_payload = None

        if isinstance(tabs_payload, dict):
            # 1. Fetch 409A Valuations (if available)
            overview = tabs_payload.get("overview", {})
            if isinstance(overview, dict):
                valuation_url = overview.get("portco-409A-valuations-url")
                if valuation_url:
                    log.info(f"[ValuationModule] Found deep valuation URL: {valuation_url}. Fetching...")
                    val_result = await direct_fetch.fetch_url(valuation_url)
                    if val_result.status_code == 200:
                        valuations_payload = val_result.payload
                        log.info("[ValuationModule] Successfully fetched deep valuations (status 200)")
                    else:
                        log.warning(f"[ValuationModule] Failed to fetch deep valuations from {valuation_url}: {val_result.error}")
                        valuations_payload = {"error": f"HTTP {val_result.status_code}: {val_result.error}"}
                else:
                    log.info("[ValuationModule] No portco-409A-valuations-url found in overview tab configuration.")

            # 2. Fetch LP SOI Ledger (contains actual investment valuations/statement of investments)
            investments = tabs_payload.get("investments", {})
            if isinstance(investments, dict):
                ledger_url = investments.get("ledger-url")
                if ledger_url:
                    log.info(f"[ValuationModule] Found ledger URL: {ledger_url}. Fetching...")
                    ledger_result = await direct_fetch.fetch_url(ledger_url)
                    if ledger_result.status_code == 200:
                        ledger_payload = ledger_result.payload
                        log.info("[ValuationModule] Successfully fetched investment ledger")
                    else:
                        log.warning(f"[ValuationModule] Failed to fetch ledger: {ledger_result.error}")
                        ledger_payload = {"error": f"HTTP {ledger_result.status_code}: {ledger_result.error}"}

            # 3. Fetch Fund Investments (contains holdings valuation breakdown)
            if isinstance(overview, dict):
                holdings_url = overview.get("fund-investments-api-url")
                if holdings_url:
                    log.info(f"[ValuationModule] Found holdings URL: {holdings_url}. Fetching...")
                    holdings_result = await direct_fetch.fetch_url(holdings_url)
                    if holdings_result.status_code == 200:
                        holdings_payload = holdings_result.payload
                        log.info("[ValuationModule] Successfully fetched fund investments holdings")
                    else:
                        log.warning(f"[ValuationModule] Failed to fetch holdings: {holdings_result.error}")
                        holdings_payload = {"error": f"HTTP {holdings_result.status_code}: {holdings_result.error}"}

        normalized_metrics = None
        if isinstance(holdings_payload, dict) and "rows" in holdings_payload:
            rows = holdings_payload.get("rows", [])
            if isinstance(rows, list) and len(rows) > 0:
                row = rows[0]
                if isinstance(row, dict):
                    nav_cents = row.get("net_asset_value")
                    contrib_cents = row.get("contributed") or row.get("capital_called")
                    
                    nav = round(float(nav_cents) / 100.0, 2) if nav_cents is not None else 0.0
                    cost = round(float(contrib_cents) / 100.0, 2) if contrib_cents is not None else 0.0
                    
                    normalized_metrics = {
                        "fund_name": row.get("fund_name"),
                        "held_since": str(row.get("vintage_year", "")).replace(".0", ""),
                        "cash_cost_usd": cost,
                        "net_asset_value_usd": nav,
                        "multiple": round((nav / cost), 2) if cost > 0 else 0.0,
                        "currency": row.get("fund_currency", "USD")
                    }

        return {
            "tabs": tabs_payload,
            "valuations": valuations_payload,
            "ledger": ledger_payload,
            "holdings": holdings_payload,
            "normalized_fund_metrics": normalized_metrics
        }

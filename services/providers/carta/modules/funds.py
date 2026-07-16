from typing import Dict, Any, Set
import logging
from .base import ExtractionModule

log = logging.getLogger(__name__)

class FundsModule(ExtractionModule):
    @property
    def name(self) -> str:
        return "funds"

    @property
    def dependencies(self) -> Set[str]:
        return {"investment"}

    @property
    def ttl_seconds(self) -> int:
        return 86400  # 24 hours

    async def extract(self, context: Any, dependency_data: Dict[str, Any]) -> Dict[str, Any]:
        log.info("[FundsModule] Starting extraction...")
        direct_fetch = context["direct_fetch"]
        firm_id = context["firm_id"]
        entity_id = context.get("entity_id")
        
        if not entity_id:
            investments = dependency_data.get("investment")
            if isinstance(investments, dict):
                overview = investments.get("overview", {})
                if isinstance(overview, dict):
                    entity_id = overview.get("entity-id") or overview.get("entity_id")

        result = await direct_fetch.fetch(
            endpoint_name="get_capital_calls",
            firm_id=firm_id,
            entity_id=entity_id
        )
        
        if result.error and result.status_code >= 400:
            log.warning(f"[FundsModule] Failed to fetch capital calls (status {result.status_code}): {result.error}")
            return {
                "results": [],
                "count": 0,
                "error": f"HTTP {result.status_code}: {result.error}"
            }
            
        return result.payload

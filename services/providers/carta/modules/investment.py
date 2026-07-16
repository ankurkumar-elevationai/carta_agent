from typing import Dict, Any, Set
import logging
from .base import ExtractionModule

log = logging.getLogger(__name__)

class InvestmentModule(ExtractionModule):
    @property
    def name(self) -> str:
        return "investment"

    @property
    def dependencies(self) -> Set[str]:
        return set()

    @property
    def ttl_seconds(self) -> int:
        return 86400  # 24 hours

    async def extract(self, context: Any, dependency_data: Dict[str, Any]) -> Dict[str, Any]:
        log.info("[InvestmentModule] Starting extraction...")
        direct_fetch = context["direct_fetch"]
        firm_id = context["firm_id"]
        entity_id = context.get("entity_id")
        
        result = await direct_fetch.fetch(
            endpoint_name="get_investments",
            firm_id=firm_id,
            entity_id=entity_id
        )
        
        if result.error and result.status_code >= 400:
            raise RuntimeError(f"Failed to fetch investments: {result.error}")
            
        return result.payload

"""
Investment Drilldown Engine (Phase 3).

Takes the DiscoveredEntity manifest from Phase 2 and navigates to each
entity's detail page to stimulate and capture entity-specific APIs
(cap table, valuations, securities).
"""

import asyncio
import logging
import time
from typing import List
from playwright.async_api import Page

from ..models.extraction import DiscoveredEntity, DrilldownResult, ActiveEntityContext, active_entity_context_var
from ..browser.traversal import CartaEntityTraversalEngine
import uuid

log = logging.getLogger(__name__)


class InvestmentDrilldownEngine:
    """
    Governs the deep traversal of discovered entities.
    Applies breadth (max_entities) and depth (max_depth) controls to prevent
    unbounded traversal storms.
    """

    def __init__(
        self,
        page: Page,
        api_collector,
        app_base_url: str = "https://app.playground.carta.team",
        max_entities: int = 50,
        max_depth: int = 2,
        tab_timeout: int = 3000,
        entity_cooldown: float = 2.0,
    ):
        self.page = page
        self.api_collector = api_collector
        self.app_base_url = app_base_url
        self.max_entities = max_entities
        self.max_depth = max_depth
        self.tab_timeout = tab_timeout
        self.entity_cooldown = entity_cooldown

    async def drilldown(self, entities: List[DiscoveredEntity]) -> List[DrilldownResult]:
        """
        Execute controlled drilldown on a list of entities.
        """
        results: List[DrilldownResult] = []
        
        # Filter for drillable entities (ones with a detail_url)
        drillable = [e for e in entities if e.detail_url]
        log.info(
            f"[DrilldownEngine] Planning drilldown for {len(drillable)} entities "
            f"(limited to {self.max_entities})"
        )

        target_entities = drillable[:self.max_entities]

        for i, entity in enumerate(target_entities):
            log.info(f"[DrilldownEngine] ({i+1}/{len(target_entities)}) Drilling into {entity.name}...")
            result = await self._drilldown_single(entity)
            results.append(result)
            
            if i < len(target_entities) - 1:
                await asyncio.sleep(self.entity_cooldown)

        return results

    async def _drilldown_single(self, entity: DiscoveredEntity) -> DrilldownResult:
        """Navigate to a single entity and trigger traversal."""
        errors = []
        routes_visited = []
        
        # Construct full URL
        target_url = entity.detail_url
        if not target_url.startswith("http"):
            target_url = f"{self.app_base_url}{target_url}"
            
        # Extract parent fund info if available
        parent_fund_id = entity.raw_data.get("fund_id") or entity.raw_data.get("parent_fund_id") or entity.raw_data.get("fund_uuid")
        parent_fund_name = entity.raw_data.get("fund_name") or entity.raw_data.get("parent_fund_name")

        import uuid
        ctx = ActiveEntityContext(
            organization_id=str(entity.parent_org_pk) if entity.parent_org_pk else "",
            entity_id=entity.entity_id,
            entity_type=entity.entity_type,
            entity_name=entity.name,
            parent_fund_id=str(parent_fund_id) if parent_fund_id else None,
            parent_fund_name=str(parent_fund_name) if parent_fund_name else None,
            route=target_url,
            traversal_session_id=str(uuid.uuid4()),
            capture_timestamp=time.time()
        )
        token = active_entity_context_var.set(ctx)
        
        try:
            # 1. Navigate to the entity's page
            await self.page.goto(target_url, wait_until="domcontentloaded")
            await asyncio.sleep(3.0)  # Wait for SPA init
            routes_visited.append(self.page.url)
            
            if hasattr(self.api_collector, "wait_for_network_quiet"):
                await self.api_collector.wait_for_network_quiet(silence_ms=500, timeout_ms=10000)

            # 2. Run Traversal Engine with provenance tracking
            traversal_engine = CartaEntityTraversalEngine(
                page=self.page, 
                collector=self.api_collector,
                max_depth=self.max_depth
            )
            
            # Hook the interaction tracker if the collector has one
            if hasattr(self.api_collector, "interaction_tracker"):
                self.api_collector.interaction_tracker.begin_interaction(
                    interaction_type="PAGE_LOAD",
                    ui_path=["Entity Detail", entity.name],
                    entity_context=entity.entity_id,
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    organization_id=str(entity.parent_org_pk),
                    drilldown_session=f"session_{int(time.time())}"
                )
                
            await traversal_engine.traverse()
            
            # TraversalQualityGate
            status = "NO_INTELLIGENCE_DISCOVERED" if traversal_engine.metrics.tabs_clicked == 0 else "SUCCESS"
            
            result = DrilldownResult(
                entity_id=entity.entity_id,
                routes_visited=tuple(routes_visited + list(traversal_engine.state.visited_routes)),
                apis_discovered=self.api_collector.classifier.total_classified if hasattr(self.api_collector, "classifier") else 0,
                tabs_explored=traversal_engine.metrics.tabs_explored,
                errors=tuple(errors),
                status=status
            )
            
        except Exception as e:
            log.warning(f"[DrilldownEngine] Failed on {entity.name}: {e}")
            errors.append(str(e))
            result = DrilldownResult(
                entity_id=entity.entity_id,
                routes_visited=tuple(routes_visited),
                errors=tuple(errors)
            )
        finally:
            active_entity_context_var.reset(token)
            
        return result

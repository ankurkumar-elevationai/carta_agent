import asyncio
import logging
from typing import Dict, List, Any
from playwright.async_api import Page

log = logging.getLogger(__name__)

class BusinessDomainDiscoveryEngine:
    """
    Phase 1.5: Hybrid Business Domain Discovery Layer.
    Explores high-level navigation domains and workflow/task families.
    """
    def __init__(self, page: Page, api_collector, app_base_url: str):
        self.page = page
        self.api_collector = api_collector
        self.app_base_url = app_base_url
        self.domains = []
        self.workflows = {}
        self.domain_api_map = {}
        
    async def discover(self) -> Dict[str, Any]:
        """Runs the hybrid discovery layer."""
        log.info("[DomainDiscovery] Starting Business Domain Discovery (Phase 1.5)...")
        
        await self.discover_domains()
        
        for domain in self.domains:
            await self.discover_workflows(domain)
            
        inventory = self.build_inventory()
        log.info("[DomainDiscovery] Phase 1.5 complete.")
        return inventory

    async def discover_domains(self):
        log.info("[DomainDiscovery] Enumerating first-level navigation domains...")
        
        # Do NOT navigate to self.app_base_url to avoid destroying target organization SPA state
        await asyncio.sleep(1.0)
        
        nav_selectors = [
            "nav a", 
            "[role='navigation'] a", 
            "[data-testid*='nav'] a",
            ".sidebar a",
            "ul[role='menu'] li a"
        ]
        
        domain_links = []
        for sel in nav_selectors:
            try:
                elements = self.page.locator(sel)
                count = await elements.count()
                if count > 0:
                    for i in range(count):
                        el = elements.nth(i)
                        if await el.is_visible():
                            text = (await el.inner_text()).strip()
                            href = await el.get_attribute("href")
                            if text and href and text not in [d["name"] for d in domain_links]:
                                domain_links.append({"name": text, "href": href})
            except Exception:
                pass
        
        self.domains = domain_links
        log.info(f"[DomainDiscovery] Found {len(self.domains)} navigation domains.")

    async def discover_workflows(self, domain: Dict[str, str]):
        log.info(f"[DomainDiscovery] Discovering workflows for domain: {domain['name']}")
        
        initial_api_count = self.api_collector.classifier.total_classified
        
        target_url = domain["href"]
        if not target_url.startswith("http"):
            target_url = f"{self.app_base_url}{target_url}"
            
        try:
            await self.page.goto(target_url, wait_until="domcontentloaded")
            await asyncio.sleep(4.0)
            
            wf_selectors = [
                "[data-testid*='task']", 
                "[data-testid*='workflow']", 
                "[class*='task']", 
                "[class*='workflow']",
                ".card",
                ".panel"
            ]
            
            workflows = []
            for sel in wf_selectors:
                try:
                    elements = self.page.locator(sel)
                    count = await elements.count()
                    for i in range(min(count, 5)): # Cap to 5 to avoid traversing infinite lists
                        el = elements.nth(i)
                        if await el.is_visible():
                            text = (await el.inner_text()).strip().split('\n')[0]
                            if text and text not in [w["name"] for w in workflows]:
                                workflows.append({"name": text, "selector_used": sel})
                                
                                try:
                                    await el.click(timeout=3000)
                                    if hasattr(self.api_collector, "wait_for_network_quiet"):
                                        await self.api_collector.wait_for_network_quiet(silence_ms=1000, timeout_ms=5000)
                                    else:
                                        await asyncio.sleep(2.0)
                                        
                                    await self.page.goto(target_url, wait_until="domcontentloaded")
                                    await asyncio.sleep(2.0)
                                except Exception as e:
                                    log.debug(f"[DomainDiscovery] Failed to click workflow {text}: {e}")
                except Exception:
                    pass
            
            self.workflows[domain["name"]] = workflows
            
            final_api_count = self.api_collector.classifier.total_classified
            apis_discovered = final_api_count - initial_api_count
            category_counts = self.api_collector.classifier.summary()
            
            self.domain_api_map[domain["name"]] = {
                "workflows": workflows,
                "api_families_observed": category_counts,
                "new_apis_triggered": apis_discovered
            }
            
        except Exception as e:
            log.warning(f"[DomainDiscovery] Failed to explore domain {domain['name']}: {e}")
            self.workflows[domain["name"]] = []
            self.domain_api_map[domain["name"]] = {
                "workflows": [],
                "api_families_observed": {},
                "new_apis_triggered": 0
            }

    def build_inventory(self) -> Dict[str, Any]:
        log.info("[DomainDiscovery] Building domain inventory and coverage report...")
        
        classifier_summary = self.api_collector.classifier.summary()
        api_families_discovered = len(classifier_summary)
        
        replayable_categories = ["PORTFOLIO", "CAP_TABLE", "VALUATIONS", "SECURITIES", "HOLDINGS", "INVESTORS"]
        replayable_count = sum(1 for cat in classifier_summary.keys() if cat in replayable_categories)
        unreplayable_count = api_families_discovered - replayable_count
        
        total_workflows = sum(len(wfs) for wfs in self.workflows.values())
        
        domains_visited = len([d for d in self.workflows.keys() if len(self.workflows[d]) > 0])
        estimated_coverage = (domains_visited / max(len(self.domains), 1)) * 100.0
        
        coverage_report = {
            "domains_discovered": len(self.domains),
            "workflow_families_discovered": total_workflows,
            "api_families_discovered": api_families_discovered,
            "replayable_api_families": replayable_count,
            "business_entity_yield": 0, # To be populated by subsequent phases
            "estimated_business_coverage": round(estimated_coverage, 2)
        }
        
        return {
            "domain_inventory": self.domains,
            "workflow_inventory": self.workflows,
            "api_family_inventory": classifier_summary,
            "domain_api_map": self.domain_api_map,
            "coverage_report": coverage_report
        }

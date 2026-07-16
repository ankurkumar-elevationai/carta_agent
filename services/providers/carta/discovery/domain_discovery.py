import asyncio
import logging
from typing import Dict, List, Any, Optional
from playwright.async_api import Page

log = logging.getLogger(__name__)

class BusinessDomainDiscoveryEngine:
    """
    Phase 1.5: Hybrid Business Domain Discovery Layer.
    Explores high-level navigation domains and workflow/task families.
    """
    def __init__(self, page: Page, api_collector, app_base_url: str, targets: Optional[List[str]] = None):
        self.page = page
        self.api_collector = api_collector
        self.app_base_url = app_base_url
        self.targets = targets
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
        
        TARGET_TO_TAB_KEYWORDS = {
            "get_investments": ["overview", "investment", "holding", "valuation", "ownership", "portfolio"],
            "get_investment_extra_info": ["overview", "profile", "investment", "holding", "portfolio"],
            "get_investment_team": ["overview", "people", "contact", "investment", "holding", "portfolio"],
            "get_investment_valuations": ["valuation", "investment", "holding", "portfolio"],
            "get_capital_calls": ["transaction", "performance", "cashflow", "activity", "investment", "holding", "portfolio"],
            "get_investment_log": ["overview", "investment", "holding", "portfolio"],
            "get_investment_transactions": ["transaction", "performance", "cashflow", "investment", "holding", "portfolio"],
            "get_investment_firm": ["overview", "investment", "holding", "portfolio"],
            "get_investment_focus": ["overview", "investment", "holding", "valuation", "ownership", "portfolio"],
            "get_investment_sectors": ["overview", "profile", "investment", "holding", "portfolio"],
            "get_investment_certificates": ["cap", "security", "ownership", "holding", "investment", "portfolio"],
            "get_distribution_history": ["transaction", "performance", "cashflow", "investment", "holding", "portfolio"],
            "get_liquidity_distributions": ["transaction", "performance", "cashflow", "investment", "holding", "portfolio"],
            "get_investment_expenses": ["transaction", "performance", "cashflow", "expense", "investment", "portfolio"],
            "get_investment_interest": ["transaction", "performance", "cashflow", "interest", "investment", "portfolio"],
            "get_investment_services": ["service", "vendor", "cost", "investment", "portfolio"],
            "get_usage_logs": ["usage", "log", "asset", "investment", "portfolio"],
            "get_recent_developments": ["overview", "profile", "news", "development", "extra_info", "investment", "portfolio"],
            "get_growth_signals": ["overview", "profile", "traction", "growth", "signal", "research", "investment", "portfolio"],
            
            "inv_investment": ["overview", "investment", "holding", "valuation", "ownership", "portfolio"],
            "inv_asset_extra_info": ["overview", "profile", "investment", "holding", "portfolio"],
            "inv_asset_team": ["overview", "people", "contact", "investment", "holding", "portfolio"],
            "inv_asset_valuation": ["valuation", "investment", "holding", "portfolio"],
            "inv_cap_call": ["transaction", "performance", "cashflow", "activity", "investment", "holding", "portfolio"],
            "investment_log": ["overview", "investment", "holding", "portfolio"],
            "inv_investment_transaction": ["transaction", "performance", "cashflow", "investment", "holding", "portfolio"],
            "inv_investment_firm": ["overview", "investment", "holding", "portfolio"],
            "inv_investment_focus": ["overview", "investment", "holding", "valuation", "ownership", "portfolio"],
            "inv_investment_sector": ["overview", "profile", "investment", "holding", "portfolio"],
            "inv_investment_certificate": ["cap", "security", "ownership", "holding", "investment", "portfolio"],
            "inv_investment_distribution_history": ["transaction", "performance", "cashflow", "investment", "holding", "portfolio"],
            "inv_liquidity_distribution": ["transaction", "performance", "cashflow", "investment", "holding", "portfolio"],
            "inv_investment_expense": ["transaction", "performance", "cashflow", "expense", "investment", "portfolio"],
            "inv_investment_interest": ["transaction", "performance", "cashflow", "interest", "investment", "portfolio"],
            "inv_investment_service": ["service", "vendor", "cost", "investment", "portfolio"],
            "inv_asset_usage_log": ["usage", "log", "asset", "investment", "portfolio"],
            "extra_info_recent_development": ["overview", "profile", "news", "development", "extra_info", "investment", "portfolio"],
            "research_growing_traction": ["overview", "profile", "traction", "growth", "signal", "research", "investment", "portfolio"],
        }

        if self.targets:
            target_keywords = set()
            for t in self.targets:
                if t in TARGET_TO_TAB_KEYWORDS:
                    target_keywords.update(TARGET_TO_TAB_KEYWORDS[t])
                else:
                    target_keywords.add(t.lower())
            
            filtered_domains = []
            for d in domain_links:
                name_lower = d["name"].lower()
                if any(kw in name_lower for kw in target_keywords):
                    filtered_domains.append(d)
            
            if filtered_domains:
                log.info(f"[DomainDiscovery] Filtered domains based on targets: {[d['name'] for d in filtered_domains]}")
                self.domains = filtered_domains
            else:
                log.warning(f"[DomainDiscovery] No domain matched target keywords {target_keywords}, falling back to all discovered domains")
                self.domains = domain_links
        else:
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

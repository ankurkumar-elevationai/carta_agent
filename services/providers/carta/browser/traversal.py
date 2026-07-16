import asyncio
import logging
import re
from typing import Set, Tuple, List, Optional
from enum import Enum
import msgspec
from playwright.async_api import Page, Locator

log = logging.getLogger(__name__)

class NavigationMode(str, Enum):
    MODAL = "modal"
    SIDEPANEL = "sidepanel"
    ROUTE = "route"
    UNKNOWN = "unknown"

class NavigationSnapshot(msgspec.Struct):
    url: str
    dialog_count: int
    history_length: int

class TraversalState(msgspec.Struct):
    visited_tabs: Set[str] = set()
    visited_entities: Set[str] = set()
    visited_routes: Set[str] = set()
    drilldown_depth: int = 0

class TraversalMetrics(msgspec.Struct):
    tabs_detected: int = 0
    tabs_relevant: int = 0
    tabs_clicked: int = 0
    new_endpoints: int = 0
    tabs_explored: int = 0 # kept for compatibility
    entities_discovered: int = 0
    failures: int = 0
    retries: int = 0
    deduplicated_rows: int = 0

TAB_PATTERNS = [
    re.compile(r"overview", re.I),
    re.compile(r"investment", re.I),
    re.compile(r"valuation", re.I),
    re.compile(r"ownership", re.I),
    re.compile(r"holding", re.I),
    re.compile(r"cap[\s-]?table", re.I),
    re.compile(r"security", re.I),
    re.compile(r"document", re.I),
    re.compile(r"performance", re.I),
    re.compile(r"metric", re.I),
    re.compile(r"tax", re.I),
    re.compile(r"partner", re.I),
    re.compile(r"cashflow", re.I),
    re.compile(r"forecast", re.I),
]

class CartaEntityTraversalEngine:
    """
    Robust active traversal engine for Carta SPAs.
    Handles DOM virtualization, network synchronization, and dynamic navigation state.
    """
    def __init__(self, page: Page, collector, max_depth: int = 1, tab_timeout: int = 3000, targets: Optional[List[str]] = None):
        self.page = page
        self.collector = collector
        self.max_depth = max_depth
        self.tab_timeout = tab_timeout
        self.state = TraversalState(visited_tabs=set(), visited_entities=set(), visited_routes=set(), drilldown_depth=0)
        self.metrics = TraversalMetrics()
        
        TARGET_TAB_MAPPING = {
            "get_investments": [r"overview", r"investment", r"holding", r"valuation", r"ownership", r"portfolio"],
            "get_investment_extra_info": [r"overview", r"profile", r"investment", r"holding", r"portfolio"],
            "get_investment_team": [r"overview", r"people", r"contact", r"investment", r"holding", r"portfolio"],
            "get_investment_valuations": [r"valuation", r"investment", r"holding", r"portfolio"],
            "get_capital_calls": [r"transaction", r"performance", r"cashflow", r"activity", r"investment", r"holding", r"portfolio"],
            "get_investment_log": [r"overview", r"investment", r"holding", r"portfolio"],
            "get_investment_transactions": [r"transaction", r"performance", r"cashflow", r"investment", r"holding", r"portfolio"],
            "get_investment_firm": [r"overview", r"investment", r"holding", r"portfolio"],
            "get_investment_focus": [r"overview", r"investment", r"holding", r"valuation", r"ownership", r"portfolio"],
            "get_investment_sectors": [r"overview", r"profile", r"investment", r"holding", r"portfolio"],
            "get_investment_certificates": [r"cap[\s-]?table", r"security", r"ownership", r"holding", r"investment", r"portfolio"],
            "get_distribution_history": [r"transaction", r"performance", r"cashflow", r"investment", r"holding", r"portfolio"],
            "get_liquidity_distributions": [r"transaction", r"performance", r"cashflow", r"investment", r"holding", r"portfolio"],
            
            "inv_investment": [r"overview", r"investment", r"holding", r"valuation", r"ownership", r"portfolio"],
            "inv_asset_extra_info": [r"overview", r"profile", r"investment", r"holding", r"portfolio"],
            "inv_asset_team": [r"overview", r"people", r"contact", r"investment", r"holding", r"portfolio"],
            "inv_asset_valuation": [r"valuation", r"investment", r"holding", r"portfolio"],
            "inv_cap_call": [r"transaction", r"performance", r"cashflow", r"activity", r"investment", r"holding", r"portfolio"],
            "investment_log": [r"overview", r"investment", r"holding", r"portfolio"],
            "inv_investment_transaction": [r"transaction", r"performance", r"cashflow", r"investment", r"holding", r"portfolio"],
            "inv_investment_firm": [r"overview", r"investment", r"holding", r"portfolio"],
            "inv_investment_focus": [r"overview", r"investment", r"holding", r"valuation", r"ownership", r"portfolio"],
            "inv_investment_sector": [r"overview", r"profile", r"investment", r"holding", r"portfolio"],
            "inv_investment_certificate": [r"cap[\s-]?table", r"security", r"ownership", r"holding", r"investment", r"portfolio"],
            "inv_investment_distribution_history": [r"transaction", r"performance", r"cashflow", r"investment", r"holding", r"portfolio"],
            "inv_liquidity_distribution": [r"transaction", r"performance", r"cashflow", r"investment", r"holding", r"portfolio"],
        }
        
        if targets:
            patterns = set()
            for t in targets:
                if t in TARGET_TAB_MAPPING:
                    patterns.update(TARGET_TAB_MAPPING[t])
                else:
                    patterns.add(t.lower())
            self.tab_patterns = [re.compile(p, re.I) for p in patterns]
            log.info(f"[TraversalEngine] Selective traversal targets specified. Custom tab patterns: {patterns}")
        else:
            self.tab_patterns = TAB_PATTERNS

    async def traverse(self):
        log.info("[TraversalEngine] Starting deep entity traversal.")
        await self._cycle_semantic_tabs()
        log.info(f"[TraversalEngine] Traversal metrics: {msgspec.json.encode(self.metrics).decode()}")

    async def _cycle_semantic_tabs(self):
        """Click tabs matching expected regex patterns."""
        import hashlib
        
        # Stage 1: Find candidates
        tab_locators = self.page.locator("a, button, [role='tab'], li, .nav-link, .nav-item")
        count = await tab_locators.count()
        self.metrics.tabs_detected += count
        
        candidates = []
        for i in range(count):
            try:
                tab = tab_locators.nth(i)
                if not await tab.is_visible(timeout=500):
                    continue
                text = (await tab.inner_text()).strip()
                if not text:
                    continue
                
                text_lower = text.lower()
                exclude_keywords = ["all ", "back", "return", "go to", "exit", "list of", "list "]
                if any(ew in text_lower for ew in exclude_keywords):
                    continue
                
                matched_pattern = None
                for pattern in self.tab_patterns:
                    if pattern.search(text):
                        matched_pattern = pattern
                        break
                
                if matched_pattern:
                    candidates.append((text, matched_pattern))
            except Exception:
                continue

        visited_hashes = set()
        
        # Stage 2: Click candidates
        for text, matched_pattern in candidates:
            self.metrics.tabs_relevant += 1
            
            # Anti-looping: Prevent clicking the same semantic element multiple times
            tab_signature = hashlib.sha256(text.encode()).hexdigest()
            if tab_signature in visited_hashes:
                continue
            visited_hashes.add(tab_signature)
            
            if text not in self.state.visited_tabs:
                log.info(f"[TraversalEngine] Clicking semantic tab: '{text}'")
                
                try:
                    # Dynamically locate tab element using text to prevent stale element reference
                    tab_locator = self.page.locator("a, button, [role='tab'], li, .nav-link, .nav-item").filter(has_text=text).first
                    if not await tab_locator.is_visible(timeout=1000):
                        continue
                        
                    # Interaction Provenance Hook
                    if hasattr(self.collector, "interaction_tracker"):
                        self.collector.interaction_tracker.begin_interaction(
                            interaction_type="TAB_CLICK",
                            ui_path=["Tab", text]
                        )
                    
                    initial_endpoints = len(self.collector.discovered_endpoints) if hasattr(self.collector, "discovered_endpoints") else 0
                    
                    await tab_locator.click(timeout=3000)
                    if self.collector and hasattr(self.collector, "wait_for_network_quiet"):
                        await self.collector.wait_for_network_quiet(silence_ms=500, timeout_ms=self.tab_timeout)
                    else:
                        await asyncio.sleep(2.0)
                        
                    # Update endpoints metric
                    if hasattr(self.collector, "discovered_endpoints"):
                        self.metrics.new_endpoints += len(self.collector.discovered_endpoints) - initial_endpoints
                    
                    self.state.visited_tabs.add(text)
                    self.metrics.tabs_clicked += 1
                    self.metrics.tabs_explored += 1
                    
                    # Check for table rows in this tab for drilldown
                    if matched_pattern.search("investment") or matched_pattern.search("cap"):
                        await self._drilldown_virtualized_table()
                except Exception as e:
                    log.warning(f"[TraversalEngine] Failed to explore tab '{text}': {e}")
                    continue

    async def get_row_identity(self, row: Locator) -> str:
        """Fallback hierarchy for row identity."""
        try:
            return (
                await row.get_attribute("data-row-key")
                or await row.get_attribute("href")
                or (await row.inner_text()).strip().lower()
            )
        except Exception:
            return "unknown"

    async def _drilldown_virtualized_table(self):
        """Scroll and interact with rows in a virtualized DOM."""
        log.info("[TraversalEngine] Initiating virtualized table drilldown.")
        rows = self.page.locator("table tbody tr")
        seen = set()
        
        max_scrolls = 200
        scrolls = 0
        
        while scrolls < max_scrolls:
            count = await rows.count()
            for i in range(count):
                row = rows.nth(i)
                try:
                    key = await self.get_row_identity(row)
                except Exception:
                    continue
                    
                if key in seen or key == "unknown":
                    continue
                    
                seen.add(key)
                self.metrics.entities_discovered += 1
                
                # Interaction Provenance Hook
                if hasattr(self.collector, "interaction_tracker"):
                    self.collector.interaction_tracker.begin_interaction(
                        interaction_type="ROW_DRILLDOWN",
                        ui_path=["Table Row", key]
                    )
                
                # Drilldown
                if self.state.drilldown_depth < self.max_depth:
                    self.state.drilldown_depth += 1
                    await self._process_row(row)
                    self.state.drilldown_depth -= 1
                
            previous = len(seen)
            await self.page.mouse.wheel(0, 4000)
            
            if self.collector and hasattr(self.collector, "wait_for_network_quiet"):
                await self.collector.wait_for_network_quiet(silence_ms=500, timeout_ms=10000)
            else:
                await asyncio.sleep(1.5)
                
            if len(seen) == previous:
                # No new rows appeared after scroll
                break
                
            scrolls += 1
            
        self.metrics.deduplicated_rows += len(seen)

    async def _process_row(self, row: Locator):
        """Click a row and safely recover state."""
        try:
            snapshot = await self._take_snapshot()
            
            # Click row or first actionable link in row
            link = row.locator("a, button").first
            if await link.count() > 0:
                await link.click(timeout=3000)
            else:
                await row.click(timeout=3000)
                
            if self.collector and hasattr(self.collector, "wait_for_network_quiet"):
                await self.collector.wait_for_network_quiet(silence_ms=500, timeout_ms=10000)
            else:
                await asyncio.sleep(3.0)
                
            mode = await self._detect_navigation_mode(snapshot)
            await self._recover_navigation_state(mode)
            
        except Exception as e:
            self.metrics.failures += 1
            log.warning(f"[TraversalEngine] Row process failed: {e}. Attempting recovery.")
            await self._recover_navigation_state(NavigationMode.UNKNOWN)

    async def _take_snapshot(self) -> NavigationSnapshot:
        dialog_count = await self.page.locator('[role="dialog"]').count()
        history_length = await self.page.evaluate("window.history.length")
        return NavigationSnapshot(url=self.page.url, dialog_count=dialog_count, history_length=history_length)

    async def _detect_navigation_mode(self, snapshot: NavigationSnapshot) -> NavigationMode:
        current_dialogs = await self.page.locator('[role="dialog"]').count()
        if current_dialogs > snapshot.dialog_count:
            return NavigationMode.MODAL
        elif self.page.url != snapshot.url:
            return NavigationMode.ROUTE
        elif await self.page.locator('[role="complementary"], aside').count() > 0:
            return NavigationMode.SIDEPANEL
        return NavigationMode.UNKNOWN

    async def _recover_navigation_state(self, mode: NavigationMode):
        log.debug(f"[TraversalEngine] Recovering from {mode.value} state.")
        if mode == NavigationMode.MODAL or mode == NavigationMode.UNKNOWN:
            await self.page.keyboard.press("Escape")
            # Fallback close buttons
            close_buttons = [
                '[aria-label="Close"]',
                'button:has-text("Close")',
                '[data-testid="close"]',
            ]
            for btn in close_buttons:
                try:
                    el = self.page.locator(btn).first
                    if await el.is_visible(timeout=500):
                        await el.click()
                        break
                except Exception:
                    pass
        elif mode == NavigationMode.SIDEPANEL:
            await self.page.keyboard.press("Escape")
        elif mode == NavigationMode.ROUTE:
            await self.page.go_back()
            
        if self.collector and hasattr(self.collector, "wait_for_network_quiet"):
            await self.collector.wait_for_network_quiet(silence_ms=500, timeout_ms=10000)
        else:
            await asyncio.sleep(1.0)

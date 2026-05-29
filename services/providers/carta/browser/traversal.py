import asyncio
import logging
import re
from typing import Set, Tuple
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
    tabs_explored: int = 0
    entities_discovered: int = 0
    failures: int = 0
    retries: int = 0
    deduplicated_rows: int = 0

TAB_PATTERNS = [
    re.compile(r"overview", re.I),
    re.compile(r"investment", re.I),
    re.compile(r"valuation", re.I),
    re.compile(r"cap[\s-]?table", re.I),
]

class CartaEntityTraversalEngine:
    """
    Robust active traversal engine for Carta SPAs.
    Handles DOM virtualization, network synchronization, and dynamic navigation state.
    """
    def __init__(self, page: Page, collector, max_depth: int = 1, tab_timeout: int = 10_000):
        self.page = page
        self.collector = collector
        self.max_depth = max_depth
        self.tab_timeout = tab_timeout
        self.state = TraversalState(visited_tabs=set(), visited_entities=set(), visited_routes=set(), drilldown_depth=0)
        self.metrics = TraversalMetrics()

    async def traverse(self):
        log.info("[TraversalEngine] Starting deep entity traversal.")
        await self._cycle_semantic_tabs()
        log.info(f"[TraversalEngine] Traversal metrics: {msgspec.json.encode(self.metrics).decode()}")

    async def _cycle_semantic_tabs(self):
        """Click tabs matching expected regex patterns."""
        tab_locators = self.page.locator("[role='tab'], .tab, button[id*='tab' i]")
        count = await tab_locators.count()
        
        for i in range(count):
            tab = tab_locators.nth(i)
            if not await tab.is_visible():
                continue
                
            text = (await tab.inner_text()).strip()
            
            # Check semantic match
            matched = False
            for pattern in TAB_PATTERNS:
                if pattern.search(text):
                    matched = True
                    break
                    
            if matched and text not in self.state.visited_tabs:
                log.info(f"[TraversalEngine] Clicking semantic tab: '{text}'")
                
                # Interaction Provenance Hook
                if hasattr(self.collector, "interaction_tracker"):
                    self.collector.interaction_tracker.begin_interaction(
                        interaction_type="TAB_CLICK",
                        ui_path=["Tab", text]
                    )
                
                await tab.click()
                if self.collector and hasattr(self.collector, "wait_for_network_quiet"):
                    await self.collector.wait_for_network_quiet(silence_ms=1200, timeout_ms=self.tab_timeout)
                else:
                    await asyncio.sleep(2.0)
                
                self.state.visited_tabs.add(text)
                self.metrics.tabs_explored += 1
                
                # Check for table rows in this tab for drilldown
                if pattern.search("investment") or pattern.search("cap"):
                    await self._drilldown_virtualized_table()

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
        
        max_scrolls = 20
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
                await self.collector.wait_for_network_quiet(silence_ms=500, timeout_ms=3000)
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
                await self.collector.wait_for_network_quiet(silence_ms=1200, timeout_ms=8000)
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
            await self.collector.wait_for_network_quiet(silence_ms=500, timeout_ms=3000)
        else:
            await asyncio.sleep(1.0)

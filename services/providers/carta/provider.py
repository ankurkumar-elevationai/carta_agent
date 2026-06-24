import os
import asyncio
import time
import urllib.request
import logging
import json
import uuid
from datetime import datetime

from services.providers.base import ProviderAgent
from services.entity_resolver import (
    resolve_entity,
    EntityResolutionError,
    RetryableBrowserError,
    EntityValidationError,
    normalize_company_name,
)

from .discovery.org_discovery import (
    OrganizationDiscoveryEngine,
    OrgDiscoveryError,
    OrgMatchError,
)

from .browser.playwright_manager import PlaywrightManager
from .browser.network_monitor import NetworkMonitor
from .utils.settings import settings, CartaRuntimeMode
from .api import CartaAuthContext, CartaRuntimeContext, CartaUIRoutes, CartaReplayClient, DiscoveryAnalyzer, ReplayMode

log = logging.getLogger(__name__)

class CartaProvider(ProviderAgent):
    """
    Carta automation provider with Network Intelligence.
    Supports separate Discovery and Runtime modes.
    """

    _browser_lock = asyncio.Lock()

    LOGIN_BASE_URL = settings.login_base_url
    APP_BASE_URL = settings.app_base_url
    API_BASE_URL = settings.api_base_url

    async def _validate_navigation(self, page):
        """Asserts domain boundary safety and catches 404s."""
        content = await page.content()
        if "Page not found" in content or "404" in await page.title():
            raise RetryableBrowserError(f"Navigation failed: 404 Page Not Found at {page.url}")
        
        if not page.url.startswith(self.APP_BASE_URL):
            raise RetryableBrowserError(f"Navigation violation: Expected {self.APP_BASE_URL}, got {page.url}")

    async def _extract_auth_context(self, page) -> tuple[CartaAuthContext, "CartaRuntimeContext"]:
        log.info("[Carta] Extracting active auth session context...")
        context = page.context
        cookies_list = await context.cookies()
        cookies_dict = {c["name"]: c["value"] for c in cookies_list}
        
        csrf_token = cookies_dict.get("eshares-csrftoken-2") or cookies_dict.get("csrftoken") or ""
        cf_clearance = cookies_dict.get("cf_clearance", "missing")
        persona = cookies_dict.get("x-carta-persona", "missing")

        log.info(f"[Carta] Session metrics: CSRF={bool(csrf_token)} | cf_clearance={cf_clearance[:10]}... | persona={persona}")
        
        user_agent = await page.evaluate("navigator.userAgent")
        
        account_id = None
        try:
            account_id = await page.evaluate("localStorage.getItem('current_organization_pk')")
        except Exception:
            pass

        session_id = str(uuid.uuid4())
        
        import re
        from .api.auth import CartaRuntimeContext

        # 1. Extract Firm ID Tier 1: URL
        firm_id = None
        match = re.search(r"/firm/(\d+)/", page.url)
        if match:
            firm_id = int(match.group(1))

        # 2. Extract Firm ID Tier 2: Storage
        if not firm_id:
            try:
                storage_val = await page.evaluate("localStorage.getItem('current_organization_pk')")
                if storage_val:
                    firm_id = int(storage_val)
            except Exception:
                pass


        runtime_ctx = CartaRuntimeContext(
            login_base_url=self.LOGIN_BASE_URL,
            app_base_url=self.APP_BASE_URL,
            api_base_url=self.API_BASE_URL,
            firm_id=firm_id,
            persona=persona if persona != "missing" else "admin",
            csrf_token=csrf_token,
            current_route=page.url
        )

        auth_ctx = CartaAuthContext(
            session_id=session_id,
            extracted_at=datetime.utcnow(),
            last_refreshed_at=datetime.utcnow(),
            version=1,
            cookies=cookies_dict,
            csrf_token=csrf_token,
            user_agent=user_agent,
            account_id=account_id
        )
        log.info(f"[Carta] Extracted auth context & runtime context (Firm ID: {firm_id})")
        return auth_ctx, runtime_ctx

    async def run(self, company_name: str, task_id: str, replay_only: bool = False) -> dict:
        lock_wait_start = time.monotonic()
        log.info(f"[Carta][{company_name}] Waiting for browser lock...")
        async with self._browser_lock:
            lock_wait_sec = time.monotonic() - lock_wait_start
            log.info(f"[Carta][{company_name}] Acquired browser lock after {lock_wait_sec:.1f}s")
            run_start = time.monotonic()
            try:
                return await asyncio.shield(self._run_internal(company_name, task_id, replay_only))
            finally:
                held_sec = time.monotonic() - run_start
                log.info(f"[Carta][{company_name}] Releasing browser lock (held {held_sec:.1f}s)")

    async def _run_internal(self, company_name: str, task_id: str, replay_only: bool = False) -> dict:
        browser = None
        page = None
        network_monitor = None
        api_collector = None

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        export_dir = os.path.join(project_root, "output", "exports")
        safe_name = normalize_company_name(company_name).replace(" ", "_")
        company_out_dir = os.path.join(export_dir, f"{task_id}_{safe_name}")

        from .utils.profiler import PerformanceProfiler
        profiler = PerformanceProfiler(company_name, task_id, company_out_dir)

        def log_phase(name: str):
            profiler.log_phase(name)

        try:
            # 1: Connect to Persistent Context
            log.info("[Carta] Checking for persistent Chrome on port 9222...")
            import urllib.request
            try:
                urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=2)
            except Exception:
                raise Exception("Could not connect to Chrome debug port. Run 'python scripts/start_persistent_browser.py' first.")

            # 2: Connect CDP
            pw = PlaywrightManager.get()
            log.info("[Carta] Connecting to Chrome via CDP...")
            browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            log.info("[Carta] browser attached to persistent profile")

            # 3: Start Network Intelligence (Discovery Mode)
            from .browser.cdp_pool import CDPPageRegistry
            from .discovery.passive_collector import PassiveNetworkCollector
            from .browser.traversal import CartaEntityTraversalEngine
            
            api_collector = PassiveNetworkCollector(output_dir=os.path.join(company_out_dir, "network"))
            api_collector.start()
            context_pool = CDPPageRegistry(api_collector)
            
            # Hook into every new page to attach CDP automatically
            def on_new_page(new_page):
                asyncio.create_task(context_pool.register_page(new_page))
                
            # Keep a strong reference in the local scope
            context_page_listener = on_new_page
            context.on("page", context_page_listener)

            if context.pages:
                page = context.pages[0]
            else:
                page = await context.new_page()
                
            # Register the main page manually since it might already exist
            await context_pool.register_page(page)
            
            page.set_default_timeout(30_000)

            # 4: Auth & Navigation
            await self._ensure_authenticated(page)
            log.info("[Carta] session valid")
            
            auth_ctx, runtime_ctx = await self._extract_auth_context(page)
            log.info("[Carta] runtime initialized")
            log.info(f"[Carta] firm_id extracted: {runtime_ctx.firm_id}")
            log_phase("setup_and_auth")
            
            # 4.1: Replay-Only Mode Short-Circuit
            if replay_only:
                log.info(f"[Carta] Executing in REPLAY-ONLY mode for {company_name}")
                from .intelligence.replay_orchestrator import ReplayOrchestrator
                
                replay_client = CartaReplayClient(
                    page=page,
                    auth_context=auth_ctx,
                    mode=ReplayMode.EXTRACTION,
                )
                
                orchestrator = ReplayOrchestrator(
                    replay_client=replay_client,
                    graph_path=Path(company_out_dir) / "graph" / "entity_graph.json",
                    output_dir=Path(company_out_dir) / "replay"
                )
                
                # Replay all investments as a default action for replay-only
                replay_res = await orchestrator.replay_category("investment")
                log_phase("replay_extraction")
                
                return {
                    "status": "success",
                    "mode": "replay_only",
                    "company_name": company_name,
                    "task_id": task_id,
                    "replay_results": replay_res
                }

            # 4.5: Organization Discovery (Phase 1 — API-driven)
            log.info(f"[Carta] Phase 1: Discovering organizations...")
            org_replay_client = CartaReplayClient(
                page=page,
                auth_context=auth_ctx,
                mode=ReplayMode.DISCOVERY,
            )
            org_engine = OrganizationDiscoveryEngine(replay_client=org_replay_client)
            
            try:
                target_org, all_orgs = await org_engine.discover_and_match(company_name)
                log.info(
                    f"[Carta] Phase 1 complete: '{target_org.name}' (org_pk={target_org.org_pk}, "
                    f"type={target_org.account_type}) — {len(all_orgs)} total orgs visible"
                )
                # Update runtime context with discovered firm_id
                if target_org.org_pk and target_org.org_pk != runtime_ctx.firm_id:
                    log.info(f"[Carta] Updating firm_id: {runtime_ctx.firm_id} → {target_org.org_pk}")
                    runtime_ctx = CartaRuntimeContext(
                        login_base_url=runtime_ctx.login_base_url,
                        app_base_url=runtime_ctx.app_base_url,
                        api_base_url=runtime_ctx.api_base_url,
                        firm_id=target_org.org_pk,
                        persona=runtime_ctx.persona,
                        csrf_token=runtime_ctx.csrf_token,
                        current_route=runtime_ctx.current_route,
                    )
            except (OrgDiscoveryError, OrgMatchError) as e:
                log.warning(f"[Carta] Org discovery failed ({e}), falling back to DOM navigation...")
                target_org = None
            log_phase("organization_discovery")
            
            # 4.75: Business Domain Discovery (Phase 1.5)
            log.info(f"[Carta] Phase 1.5: Business Domain Discovery...")
            from .discovery.domain_discovery import BusinessDomainDiscoveryEngine
            domain_engine = BusinessDomainDiscoveryEngine(
                page=page, 
                api_collector=api_collector, 
                app_base_url=runtime_ctx.app_base_url
            )
            domain_inventory_data = await domain_engine.discover()
            
            log.info("[Carta] Phase 1.5 complete, artifacts will be exported in finalization phase.")
            log_phase("business_domain_discovery")
            
            # 5: Entity Discovery (Phase 2 — API-driven enumeration)
            entity_manifest = []
            if target_org:
                log.info(f"[Carta] Phase 2: Discovering entities for {target_org.name}...")
                from .discovery.entity_discovery import EntityDiscoveryEngine
                
                entity_engine = EntityDiscoveryEngine(
                    replay_client=org_replay_client,
                    target_org=target_org,
                    app_base_url=runtime_ctx.app_base_url,
                )
                try:
                    entity_manifest = await entity_engine.discover()
                    log.info(
                        f"[Carta] Phase 2 complete: {len(entity_manifest)} entities discovered"
                    )
                except Exception as e:
                    log.warning(f"[Carta] Entity discovery failed: {e}")
                    entity_manifest = []
            log_phase("entity_discovery")
            
            # 5.5: Navigate to target company
            log.info(f"[Carta] Navigating to target company: {company_name}")
            company_page = await self._navigate_to_company(
                page, company_name, runtime_ctx, target_org=target_org
            )
            log_phase("company_navigation")
            
            # 6: Investment Drilldown (Phase 3) & SPA Traversal
            log.info(f"[Carta] Phase 3: Stimulating network traffic for {company_name}...")
            drilldown_results = []
            
            if entity_manifest:
                from .discovery.drilldown_engine import InvestmentDrilldownEngine
                drilldown_engine = InvestmentDrilldownEngine(
                    page=company_page,
                    api_collector=api_collector,
                    app_base_url=runtime_ctx.app_base_url,
                    max_entities=10000,
                    max_depth=3,
                )
                drilldown_results = await drilldown_engine.drilldown(entity_manifest)
                
                # Convert results to dicts for the final output
                drilldown_results_dict = [
                    {
                        "entity_id": dr.entity_id,
                        "routes_visited": dr.routes_visited,
                        "apis_discovered": dr.apis_discovered,
                        "tabs_explored": dr.tabs_explored,
                        "errors": dr.errors
                    }
                    for dr in drilldown_results
                ]
            else:
                # Fallback to single-company traversal if no entity manifest
                log.info(f"[Carta] No entity manifest, falling back to legacy traversal.")
                from .browser.traversal import CartaEntityTraversalEngine
                engine = CartaEntityTraversalEngine(company_page, api_collector)
                await engine.traverse()
                drilldown_results_dict = []
                
            # Log interaction provenance summary
            if hasattr(api_collector, "interaction_tracker"):
                history = api_collector.interaction_tracker.history
                log.info(f"[Carta] Recorded {len(history)} interaction provenances.")
                
            if hasattr(api_collector, "dependency_tracker"):
                deps = api_collector.dependency_tracker.dependencies
                log.info(f"[Carta] Recorded {len(deps)} API dependencies.")
            log_phase("investment_drilldown")
            
            # 7: Export Capture (Phase 4 — API Replay)
            log.info(f"[Carta] Phase 4: Replaying discovered APIs for {company_name}...")
            from .intelligence.intelligence_extractor import IntelligenceExtractor
            from pathlib import Path
            
            replay_client = CartaReplayClient(
                page=company_page,
                auth_context=auth_ctx,
                mode=ReplayMode.EXTRACTION,
            )
            extractor = IntelligenceExtractor(
                classifier=api_collector.classifier,
                replay_client=replay_client,
                output_dir=Path(company_out_dir) / "extracted",
                entity_manifest=entity_manifest,
                api_collector=api_collector,
            )
            try:
                extraction_manifest = await extractor.extract()
                log.info(f"[Carta] API extraction complete: {extraction_manifest.get('summary', {})}")
                
                # Feed extraction metrics and ROI to the profiler
                metrics = extraction_manifest.get("_metrics", {})
                profiler.record_replay_metrics(
                    discovered=metrics.get("endpoints_discovered", 0),
                    replayed=metrics.get("endpoints_replayed", 0),
                    skipped=metrics.get("endpoints_skipped", 0),
                    successful=metrics.get("successful_replays", 0),
                    failed=metrics.get("failed_replays", 0),
                    new_entities=metrics.get("new_entities_found", 0)
                )
                for family, data in metrics.get("roi_metrics", {}).items():
                    attempts = data.get("attempts", 0) if isinstance(data, dict) else 0
                    entities = data.get("entities", 0) if isinstance(data, dict) else data
                    profiler.record_roi(family, attempts, entities)
            finally:
                log_phase("api_extraction")
                
            # 7.5: Export Intelligence (Phase 4.5)
            log.info(f"[Carta] Phase 4.5: Executing Export Intelligence...")
            from .export.export_engine import ExportReplayEngine
            export_engine = ExportReplayEngine(auth_ctx, company_out_dir)
            exports_manifest = []
            
            if hasattr(api_collector, "discovered_exports"):
                for exp in api_collector.discovered_exports:
                    try:
                        artifact = await export_engine.download_export(
                            path=exp["url"],
                            params=None,
                            entity_id=exp["entity_id"] or "unknown",
                            organization_id=exp["organization_id"] or "unknown"
                        )
                        if artifact:
                            exports_manifest.append(artifact)
                    except Exception as e:
                        log.error(f"[Carta] Export download failed: {e}")
                        
            # Save inventory
            if exports_manifest:
                import msgspec
                inventory_path = os.path.join(company_out_dir, "export_inventory.json")
                with open(inventory_path, "w") as f:
                    f.write(msgspec.json.encode(exports_manifest).decode("utf-8"))
                log.info(f"[Carta] Export Intelligence complete. Captured {len(exports_manifest)} exports.")
            log_phase("export_intelligence")
            
            # 8: Semantic Clustering (Phase 5)
            log.info(f"[Carta] Phase 5: Building semantic schema clusters...")
            from .intelligence.schema_clusterer import SchemaClusterer
            clusterer = SchemaClusterer(
                extracted_dir=Path(company_out_dir) / "extracted",
                output_dir=Path(company_out_dir) / "schemas",
            )
            clusters = clusterer.cluster()
            log.info(f"[Carta] Phase 5 complete: {len(clusters)} clusters built.")
            log_phase("semantic_clustering")
            
            # 9: Entity Graph Construction (Phase 6)
            log.info(f"[Carta] Phase 6: Constructing Canonical Entity Graph...")
            from .intelligence.graph_builder import EntityGraphBuilder
            graph_builder = EntityGraphBuilder(
                extracted_dir=Path(company_out_dir) / "extracted",
                output_dir=Path(company_out_dir) / "graph",
                entity_manifest=entity_manifest,
                firm_id=int(target_org.org_pk) if target_org and target_org.org_pk else int(runtime_ctx.firm_id or 0),
                firm_name=target_org.name if target_org else company_name,
            )
            entity_graph = graph_builder.build()
            log.info(f"[Carta] Phase 6 complete: Graph built with {len(entity_graph.nodes)} nodes and {len(entity_graph.edges)} edges.")
            log_phase("entity_graph_construction")
            
            # 9.5: Finalization Phase (Coverage & Artifacts)
            log.info(f"[Carta] Phase 6.5: Generating Final Intelligence Artifacts...")
            if 'domain_engine' in locals():
                final_inventory = domain_engine.build_inventory()
                
                coverage_data = final_inventory.get("coverage_report", {})
                coverage_data["entities_discovered"] = len(entity_manifest)
                coverage_data["entities_registered"] = len(entity_manifest)
                
                linked_entities = set()
                for edge in entity_graph.edges:
                    linked_entities.add(edge.source_id)
                    linked_entities.add(edge.target_id)
                coverage_data["entities_linked"] = len([n for n in entity_graph.nodes.values() if n.node_id in linked_entities])
                
                coverage_data["entities_with_payloads"] = len(extraction_manifest.get("files", [])) if 'extraction_manifest' in locals() else 0
                coverage_data["graph_nodes"] = len(entity_graph.nodes)
                coverage_data["graph_edges"] = len(entity_graph.edges)
                if entity_manifest:
                    coverage_data["business_entity_yield"] = round((len(entity_graph.nodes) / max(len(entity_manifest), 1)) * 100, 2)
                    
                with open(os.path.join(company_out_dir, "domain_inventory.json"), "w") as f:
                    json.dump(final_inventory["domain_inventory"], f, indent=2)
                with open(os.path.join(company_out_dir, "workflow_inventory.json"), "w") as f:
                    json.dump(final_inventory["workflow_inventory"], f, indent=2)
                with open(os.path.join(company_out_dir, "api_family_inventory.json"), "w") as f:
                    json.dump(final_inventory["api_family_inventory"], f, indent=2)
                with open(os.path.join(company_out_dir, "domain_api_map.json"), "w") as f:
                    json.dump(final_inventory["domain_api_map"], f, indent=2)
                with open(os.path.join(company_out_dir, "coverage_report.json"), "w") as f:
                    json.dump(coverage_data, f, indent=2)
            log_phase("artifact_generation")
            
            # 10: Export CSVs and Docs
            log.info(f"[Carta] Exporting CSVs and Docs for {company_name}...")
            exports = await self._export_company_data(context, company_page, company_name, task_id)
            log_phase("data_export")

            extraction_result = {
                "status": "success",
                "company_name": company_name,
                "task_id": task_id,
                "org_pk": target_org.org_pk if target_org else runtime_ctx.firm_id,
                "org_name": target_org.name if target_org else company_name,
                "all_orgs": [o.name for o in all_orgs] if target_org else [],
                "entity_manifest": [
                    {"entity_id": e.entity_id, "name": e.name, "type": e.entity_type}
                    for e in entity_manifest
                ],
                "drilldown_results": drilldown_results_dict,
                "schema_clusters": len(clusters),
                "graph_nodes": len(entity_graph.nodes),
                "graph_edges": len(entity_graph.edges),
                "exports": exports,
                "extraction_manifest": extraction_manifest,
                "network_data_dir": str(api_collector.output_dir)
            }
            
            return extraction_result

        except (EntityResolutionError, EntityValidationError, OrgMatchError) as e:
            log.error(f"[Carta] Entity matching failed for '{company_name}': {e}")
            raise
        except RetryableBrowserError as e:
            log.error(f"[Carta] Retryable browser error for '{company_name}': {e}")
            raise
        except Exception as e:
            log.error(f"[Carta] Unexpected error for '{company_name}': {e}")
            raise RetryableBrowserError(str(e))

        finally:
            # Write performance profile report
            if 'profiler' in locals() and profiler:
                try:
                    profiler.write_report()
                except Exception as pe:
                    log.warning(f"[Carta] Failed to write performance profile: {pe}")

            # Flush API intelligence before teardown
            if api_collector:
                await api_collector.shutdown()

            if page:
                try:
                    # Clear the page instead of closing it so we can reuse the persistent tab next time
                    await page.goto("about:blank")
                except Exception as e:
                    log.warning(f"[Carta] Failed to clear task page: {e}")

            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

            log.info(f"[Carta][{company_name}] Browser teardown complete.")

    # --- Sandbox Auth & Nav Validation ---
    async def _ensure_authenticated(self, page) -> None:
        log.info(f"[Carta] Navigating directly to APP domain: {self.APP_BASE_URL}...")
        
        from .api.exceptions import SessionExpiredError, InvalidRouteError, PersonaMismatchError

        # 1. Navigate to App Base URL
        await page.goto(self.APP_BASE_URL, wait_until="domcontentloaded")
        
        # 2. Wait for page stability
        try:
            # Replaced unreliable networkidle with a safe sleep for SPA routing
            await asyncio.sleep(3.0)
        except Exception:
            pass

        content = await page.content()
        final_url = page.url

        # 3. Validate Session State
        if self.LOGIN_BASE_URL in final_url or "/login" in final_url:
            raise SessionExpiredError("Session invalid. Redirected to login domain. Please log in manually once.")
        
        if "Page not found" in content or "404" in await page.title():
            raise InvalidRouteError(f"Navigation failed: 404 Page Not Found at {final_url}")
        
        if "/investors/" not in final_url:
            raise InvalidRouteError(f"Navigation violation: Expected '/investors/' route, got {final_url}")

        log.info("[Carta] Persistent session verified successfully.")

    async def _navigate_to_company(self, page, company_name: str, runtime_ctx, target_org=None):
        """Navigate to the target company's portfolio page.
        
        If target_org is provided (from Phase 1 org discovery), uses the 
        discovered org_pk directly. Otherwise falls back to DOM-based navigation.
        """
        log.info(f"[Carta] Navigating to portfolio overview...")
        from .api.exceptions import InvalidRouteError
        
        # Use org-discovery firm_id if available, otherwise fall back to runtime_ctx
        firm_id = target_org.org_pk if target_org else runtime_ctx.firm_id
        
        if not firm_id:
            raise InvalidRouteError("Cannot navigate without a valid firm_id.")
            
        route = CartaUIRoutes.investments(firm_id)
        target_url = f"{runtime_ctx.app_base_url}{route}"
        
        await page.goto(target_url, wait_until="domcontentloaded")
        await asyncio.sleep(4.0)  # Wait for SPA initialization instead of networkidle
        
        final_url = page.url
        content = await page.content()
        
        if self.LOGIN_BASE_URL in final_url or "/login" in final_url:
            raise InvalidRouteError("Session invalid. Redirected to login domain.")
        
        if "Page not found" in content or "404" in await page.title():
            raise InvalidRouteError(f"Navigation failed: 404 Page Not Found at {final_url}")
            
        if not final_url.startswith(runtime_ctx.app_base_url):
            raise InvalidRouteError(f"Navigation violation: Expected app base url, got {final_url}")

        log.info("[Carta] Waiting for portfolio table...")
        try:
            await page.wait_for_selector(
                "table, [data-testid='holdings-table'], [data-testid='portfolio-table'], [class*='holdings'], [class*='portfolio'], [class*='investments-table']",
                timeout=30_000,
            )
        except Exception:
            raise RetryableBrowserError("Carta portfolio/holdings table did not load within 30s.")

        # If we have a target_org from Phase 1, we're already on the right firm page.
        # The portfolio list shows investments. For now, we DON'T need to click 
        # into a specific company row — the traversal engine will handle that.
        if target_org:
            log.info(
                f"[Carta] ✓ Navigated to '{target_org.name}' portfolio "
                f"(org_pk={target_org.org_pk}, firm_id={firm_id})"
            )
            return page

        # Legacy fallback: DOM-based entity search & resolution
        log.info(f"[Carta] Searching for company: {company_name}")
        search_selector = "input[placeholder*='Search' i], input[placeholder*='Filter' i], input[aria-label*='Search' i], input[type='search']"
        search_count = await page.locator(search_selector).count()

        if search_count > 0:
            search_input = page.locator(search_selector).first
            await search_input.click()
            await search_input.fill(company_name)
            await asyncio.sleep(3.0)  # Wait for live search results to load

        log.info("[Carta] Extracting table rows for entity resolution...")
        raw_candidates = await page.evaluate("""
            () => {
                const selectors = [
                    'tr[data-testid], tr[class*="row"], tbody tr',
                    '[class*="holdings-row"], [class*="portfolio-row"]',
                    '[data-testid*="company"], [data-testid*="investment"]'
                ];
                let rows = [];
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0) {
                        els.forEach((el, idx) => {
                            const text = el.innerText.trim().split('\\n')[0];
                            if (text) rows.push({ index: idx, text: text });
                        });
                        break;
                    }
                }
                return rows;
            }
        """)

        if not raw_candidates:
            raise EntityResolutionError(f"No portfolio rows found for query: '{company_name}'.")

        best = resolve_entity(company_name, raw_candidates)
        log.info(f"[Carta] Selected: '{best.text}' (score={best.score:.1f})")

        row_selectors = ['tr[data-testid]', 'tr[class*="row"]', 'tbody tr', '[class*="holdings-row"]', '[class*="portfolio-row"]']
        clicked = False
        for sel in row_selectors:
            rows = page.locator(sel)
            count = await rows.count()
            if count > best.index:
                target_row = rows.nth(best.index)
                await target_row.wait_for(state="visible", timeout=10_000)

                link = target_row.locator("a, button").first
                link_count = await link.count()
                if link_count > 0:
                    await link.click()
                else:
                    await target_row.click()
                clicked = True
                break

        if not clicked:
            raise RetryableBrowserError(f"Could not click company row for '{company_name}'.")

        await asyncio.sleep(5.0)  # Wait for SPA navigation to the firm's detail page
        page_title = await page.title()
        log.info(f"[Carta] Company page title: '{page_title}'")
        normalized_query = normalize_company_name(company_name)
        normalized_title = normalize_company_name(page_title)
        if normalized_query and normalized_query not in normalized_title:
            raise EntityValidationError(f"Expected company '{company_name}' not confirmed in page title '{page_title}'.")

        return page

    async def _export_company_data(self, context, page, company_name: str, task_id: str) -> list:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        base_export_dir = os.path.join(project_root, "output", "exports")
        safe_name = normalize_company_name(company_name).replace(" ", "_")
        company_out_dir = os.path.join(base_export_dir, f"{task_id}_{safe_name}")
        os.makedirs(company_out_dir, exist_ok=True)
        
        exports = []
        holdings_path = await self._export_holdings(page, company_name, task_id, company_out_dir)
        if holdings_path:
            exports.append({"type": "holdings_csv", "path": holdings_path})
        docs = await self._download_documents(context, page, company_name, task_id, company_out_dir)
        exports.extend(docs)
        if not exports:
            raise Exception(f"No exportable data found for '{company_name}' on Carta.")
        return exports

    async def _export_holdings(self, page, company_name: str, task_id: str, export_dir: str) -> str | None:
        log.info(f"[Carta] Looking for holdings Export button...")
        export_btn_selector = "button:has-text('Export'), button[aria-label*='Export' i], button[aria-label*='Download' i], [data-testid='export-button'], [data-testid='download-button']"
        tab_selector = "button:has-text('Holdings'), a:has-text('Holdings'), button:has-text('Cap Table'), a:has-text('Cap Table'), [role='tab']:has-text('Holdings')"
        try:
            tab_locator = page.locator(tab_selector).first
            if await tab_locator.is_visible(timeout=3000):
                log.info("[Carta] Clicking Holdings/Cap Table tab...")
                await tab_locator.click(timeout=5000)
                await asyncio.sleep(3.0)  # Let holdings tab initialize
        except Exception as e:
            log.warning(f"[Carta] Failed to interact with Holdings tab: {e}")

        export_count = await page.locator(export_btn_selector).count()
        if export_count == 0:
            log.warning("[Carta] No Export button found on company page.")
            return None

        log.info("[Carta] Clicking Export button...")
        safe_name = normalize_company_name(company_name).replace(" ", "_")
        dest_path = os.path.join(export_dir, f"{task_id}_{safe_name}_holdings")

        try:
            async with page.expect_download(timeout=60_000) as dl_info:
                await page.locator(export_btn_selector).first.click(timeout=5000)
                await asyncio.sleep(1.5)
                csv_option = page.locator("button:has-text('CSV'), a:has-text('CSV'), [role='menuitem']:has-text('CSV'), button:has-text('.csv')").first
                if await csv_option.is_visible(timeout=3000):
                    log.info("[Carta] Selecting CSV format...")
                    await csv_option.click(timeout=5000)

            download = await dl_info.value
            suggested = download.suggested_filename or f"{task_id}_holdings.csv"
            ext = os.path.splitext(suggested)[1] or ".csv"
            final_path = dest_path + ext
            await download.save_as(final_path)
            log.info(f"[Carta] Holdings export saved: {final_path}")
            return final_path
        except Exception as e:
            log.warning(f"[Carta] Holdings export download failed: {e}")
            return None

    async def _download_documents(self, context, page, company_name: str, task_id: str, export_dir: str) -> list:
        MAX_DOCS = 5
        exports = []
        doc_tab_selector = "button:has-text('Documents'), a:has-text('Documents'), [role='tab']:has-text('Documents'), [data-testid*='documents']"
        try:
            doc_tab_locator = page.locator(doc_tab_selector).first
            if not await doc_tab_locator.is_visible(timeout=3000):
                log.info("[Carta] No Documents tab found.")
                return exports

            log.info("[Carta] Navigating to Documents section...")
            await doc_tab_locator.click(timeout=5000)
            await asyncio.sleep(3.0)  # Let documents initialize
        except Exception as e:
            log.warning(f"[Carta] Failed to interact with Documents tab: {e}")
            return exports

        doc_link_selector = "a[download], a[href*='.pdf'], a[href*='/documents/'], button[aria-label*='Download' i]"
        doc_links = page.locator(doc_link_selector)
        doc_count = await doc_links.count()
        log.info(f"[Carta] Found {doc_count} document(s). Downloading up to {MAX_DOCS}.")

        safe_name = normalize_company_name(company_name).replace(" ", "_")
        for i in range(min(doc_count, MAX_DOCS)):
            try:
                link = doc_links.nth(i)
                dest_path = os.path.join(export_dir, f"{task_id}_{safe_name}_doc_{i+1}.pdf")
                async with page.expect_download(timeout=30_000) as dl_info:
                    await link.click()
                download = await dl_info.value
                suggested = download.suggested_filename
                if suggested:
                    ext = os.path.splitext(suggested)[1] or ".pdf"
                    dest_path = os.path.join(export_dir, f"{task_id}_{safe_name}_doc_{i+1}{ext}")
                await download.save_as(dest_path)
                log.info(f"[Carta] Document {i+1} saved: {dest_path}")
                exports.append({"type": "document", "path": dest_path})
            except Exception as e:
                log.warning(f"[Carta] Failed to download document {i+1}: {e}")
                continue
        return exports

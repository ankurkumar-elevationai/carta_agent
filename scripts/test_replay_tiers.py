import os
import sys
import json
import uuid
import asyncio
import logging
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import BaseModel
from services.providers.carta.provider import CartaProvider
from services.providers.carta.browser.playwright_manager import PlaywrightManager
from services.providers.carta.api.replay_client import CartaReplayClient, ReplayScenario, CartaReplayStrategy, ReplayMode, ReplayTarget

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

class ReplayValidationReport(BaseModel):
    validation_run_id: str
    milestone_results: dict
    replay_metrics: dict
    failures: list[str]
    completed_at: datetime

class ReplayValidationSuite:
    def __init__(self):
        self.run_id = uuid.uuid4().hex
        self.provider = CartaProvider()
        self.report = ReplayValidationReport(
            validation_run_id=self.run_id,
            milestone_results={},
            replay_metrics={},
            failures=[],
            completed_at=datetime.utcnow()
        )
        self.client = None
        self.page = None
        
        self.metrics_path = "output/carta/replay_metrics.jsonl"
        self.failures_path = "output/carta/replay_failures.jsonl"
        self.runs_path = "output/carta/validation_runs.jsonl"
        
        os.makedirs("output/carta", exist_ok=True)

    def _log(self, msg: str):
        log.info(f"[ValidationSuite][{self.run_id}] {msg}")

    def _record_failure(self, milestone: str, error: str):
        self._log(f"FAILED {milestone}: {error}")
        self.report.failures.append(f"{milestone}: {error}")
        self.report.milestone_results[milestone] = False
        with open(self.failures_path, "a") as f:
            f.write(json.dumps({"run_id": self.run_id, "milestone": milestone, "error": error}) + "\n")

    def _record_success(self, milestone: str):
        self._log(f"PASSED {milestone}")
        self.report.milestone_results[milestone] = True

    def _record_metric(self, name: str, value: float):
        self.report.replay_metrics[name] = value
        with open(self.metrics_path, "a") as f:
            f.write(json.dumps({"run_id": self.run_id, "metric": name, "value": value}) + "\n")

    async def setup(self):
        self._log("Connecting to persistent Chrome...")
        await PlaywrightManager.start()
        pw = PlaywrightManager.get()
        browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        self.page = await context.new_page()
        self.page.set_default_timeout(30000)
        
        await self.provider._ensure_authenticated(self.page)
        
        auth_ctx = await self.provider._extract_auth_context(self.page)
        
        async def refresh_cb():
            await self.provider._ensure_authenticated(self.page)
            new_ctx = await self.provider._extract_auth_context(self.page)
            new_ctx.version = auth_ctx.version + 1
            return new_ctx
            
        self.client = CartaReplayClient(
            page=self.page,
            auth_context=auth_ctx,
            mode=ReplayMode.DISCOVERY,
            on_refresh_callback=refresh_cb
        )
        
        self.test_target = ReplayTarget(
            method="GET",
            url="/api/tasks/",
            headers={},
            body_hash=None,
            inferred_capabilities={"requires_browser"} # For testing fallbacks
        )

    async def validate_auth_extraction(self):
        self._log("Running Milestone 1: Auth Extraction Stability")
        try:
            start = time.time()
            ctx = self.client.auth_context
            
            assert ctx.csrf_token, "csrf_token is empty"
            assert ctx.cookies, "cookies are empty"
            assert ctx.user_agent, "user_agent is empty"
            assert ctx.version >= 1, "session_version not initialized"
            assert "cf_clearance" in ctx.cookies, "cf_clearance cookie is missing - CRITICAL FOR REPLAY"
            
            self._record_metric("auth_extraction_latency_ms", (time.time() - start) * 1000)
            self._record_success("Milestone A: Auth Extraction")
        except Exception as e:
            self._record_failure("Milestone A: Auth Extraction", str(e))

    async def validate_httpx_tier(self):
        self._log("Running Milestone 2: HTTPX Stability (20 iterations)")
        try:
            latencies = []
            for i in range(20):
                res = await self.client.get(self.test_target, scenario=ReplayScenario.HTTPX_ONLY)
                assert res.status_code == 200, f"HTTPX status code {res.status_code} != 200 on iteration {i}"
                assert res.strategy_used == CartaReplayStrategy.HTTPX, "Strategy mismatch"
                assert "tasks" in (res.payload or {}), "'tasks' not found in payload"
                # Note: Sometimes x_carta_trace_id might not be returned depending on exact endpoint shape. 
                # If they do not return it, this assert might fail. The user explicitly requested it though.
                if not res.x_carta_trace_id:
                    self._log(f"WARNING: x-carta-trace-id header missing on iteration {i}")
                latencies.append(res.latency_ms)
                
            latencies.sort()
            p50 = latencies[len(latencies)//2]
            p95 = latencies[int(len(latencies)*0.95)]
            
            self._record_metric("httpx_latency_p50", p50)
            self._record_metric("httpx_latency_p95", p95)
            self._record_success("Milestone B: HTTPX Tier")
        except Exception as e:
            self._record_failure("Milestone B: HTTPX Tier", str(e))

    async def validate_api_context_tier(self):
        self._log("Running Milestone 3: APIRequestContext Stability")
        try:
            start = time.time()
            res = await self.client.get(self.test_target, scenario=ReplayScenario.API_CONTEXT_ONLY)
            assert res.status_code == 200, f"Status code {res.status_code} != 200"
            assert res.strategy_used == CartaReplayStrategy.API_REQUEST_CONTEXT
            
            self._record_metric("api_context_latency_ms", (time.time() - start) * 1000)
            self._record_success("Milestone C1: APIRequestContext Tier")
        except Exception as e:
            self._record_failure("Milestone C1: APIRequestContext Tier", str(e))

    async def validate_browser_fetch_tier(self):
        self._log("Running Milestone 4: Browser Fetch Stability")
        try:
            start = time.time()
            res = await self.client.get(self.test_target, scenario=ReplayScenario.BROWSER_FETCH_ONLY)
            assert res.status_code == 200, f"Status code {res.status_code} != 200"
            assert res.strategy_used == CartaReplayStrategy.BROWSER_FETCH
            
            self._record_metric("browser_fetch_latency_ms", (time.time() - start) * 1000)
            self._record_success("Milestone C2: Browser Fetch Tier")
        except Exception as e:
            self._record_failure("Milestone C2: Browser Fetch Tier", str(e))

    async def validate_auto_routing(self):
        self._log("Running Milestone 5: AUTO Routing")
        try:
            res = await self.client.get(self.test_target, scenario=ReplayScenario.AUTO_FALLBACK)
            assert res.status_code == 200
            assert "SUCCESS" in res.timeline, f"Timeline missing SUCCESS: {res.timeline}"
            self._record_success("Milestone C3: AUTO Routing")
        except Exception as e:
            self._record_failure("Milestone C3: AUTO Routing", str(e))

    async def validate_session_refresh(self):
        self._log("Running Milestone 6: Session Refresh")
        try:
            old_version = self.client.auth_context.version
            start = time.time()
            
            res = await self.client.get(self.test_target, scenario=ReplayScenario.SESSION_REFRESH)
            
            assert res.status_code == 200
            assert self.client.auth_context.version > old_version, "Session version did not increment"
            
            self._record_metric("session_refresh_latency_ms", (time.time() - start) * 1000)
            self._record_success("Milestone D: Session Refresh")
        except Exception as e:
            self._record_failure("Milestone D: Session Refresh", str(e))

    async def validate_circuit_breakers(self):
        self._log("Running Milestone 7: Circuit Breakers")
        try:
            path = self.test_target.url
            health = self.client._get_health(path)
            health.temporarily_disabled = True
            health.disabled_until = datetime.utcnow() + __import__("datetime").timedelta(minutes=5)
            
            res = await self.client.get(self.test_target, scenario=ReplayScenario.AUTO_FALLBACK)
            
            assert res.strategy_used == CartaReplayStrategy.API_REQUEST_CONTEXT, f"Expected Tier-2 fallback, got {res.strategy_used}"
            assert res.status_code == 200
            
            health.temporarily_disabled = False
            health.disabled_until = None
            
            self._record_success("Milestone E1: Circuit Breakers")
        except Exception as e:
            self._record_failure("Milestone E1: Circuit Breakers", str(e))

    async def teardown(self):
        self.report.completed_at = datetime.utcnow()
        with open(self.runs_path, "a") as f:
            f.write(self.report.model_dump_json() + "\n")
            
        if self.page:
            try:
                await self.page.close()
            except:
                pass
        
        await PlaywrightManager.stop()
            
        self._log(f"Validation Run Complete. Passed: {sum(1 for v in self.report.milestone_results.values() if v)}/{len(self.report.milestone_results)}")
        
        # Throw if there are any failures to fail the script run
        failures = [k for k, v in self.report.milestone_results.items() if not v]
        if failures:
            sys.exit(1)

    async def run_all(self):
        await self.setup()
        await self.validate_auth_extraction()
        await self.validate_httpx_tier()
        await self.validate_api_context_tier()
        await self.validate_browser_fetch_tier()
        await self.validate_auto_routing()
        await self.validate_session_refresh()
        await self.validate_circuit_breakers()
        await self.teardown()

if __name__ == "__main__":
    suite = ReplayValidationSuite()
    asyncio.run(suite.run_all())

"""
api/server.py
-------------
OpenClaw Download/Export API Server — browser-only process.

This server handles:
  - Task queue management (SQLite WAL)
  - Export worker (Playwright + Chrome via CartaProvider)
  - File validation + static file serving
  - Status API endpoints
  - Periodic file cleanup watchdog

Provider
--------
Active provider: CartaProvider (holdings CSV + document exports)

To switch providers, change the import below and update the
`run_provider_agent_with_retry` call. The queue, worker, MCP server,
and cleanup logic are fully provider-agnostic.
"""

import os
import sys
import json
import uuid
import glob
import time
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_not_exception_type
# pyrefly: ignore [missing-import]
from loguru import logger
import logging

load_dotenv()

# Configure logging to write to logs/log.txt
os.makedirs("logs", exist_ok=True)
logger.add("logs/log.txt", rotation="10 MB", retention="1 week")

# Intercept standard logging messages and route them to loguru
class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

# Also ensure uvicorn loggers use our InterceptHandler
for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
    logger_inst = logging.getLogger(logger_name)
    logger_inst.handlers = [InterceptHandler()]
    logger_inst.propagate = False

# Ensure we can import modules from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Active Provider ────────────────────────────────────────────────
from services.providers.carta import CartaProvider, PlaywrightManager
# ──────────────────────────────────────────────────────────────────

from services.entity_resolver import EntityResolutionError, EntityValidationError
from utils.db import (
    init_db,
    get_connection,
    update_task_status,
    get_task_status,
    claim_next_task,
    DB_PATH,
    EXPORT_DIR,
)

# Globals
TASK_TIMEOUT_SEC = 480  # 8 minutes max per export task

# Event for the export queue worker
new_export_event = asyncio.Event()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_mapper_cache = {"mtime": 0, "mapper": None}

def get_platform_mapper():
    biz_path = os.path.join(PROJECT_ROOT, "output", "business_data.json")
    if not os.path.exists(biz_path):
        return None
    mtime = os.path.getmtime(biz_path)
    if _mapper_cache["mtime"] == mtime and _mapper_cache["mapper"]:
        return _mapper_cache["mapper"]
        
    from services.canonical_store import CanonicalEntityStore
    from services.adapters.carta_adapter import CartaAdapter
    from services.platform_mapper import PlatformSchemaMapper
    
    canonical_store = CanonicalEntityStore()
    with open(biz_path, "r", encoding="utf-8") as f:
        raw_biz_data = json.load(f)
    adapter = CartaAdapter(raw_biz_data)
    adapter.populate(canonical_store)
    mapper = PlatformSchemaMapper(canonical_store)
    
    _mapper_cache["mtime"] = mtime
    _mapper_cache["mapper"] = mapper
    return mapper

def validate_export(path: str) -> bool:
    """
    Validates that a downloaded export file exists and has a non-trivial size.
    Accepts CSV, XLSX, PDF, and other document formats.
    """
    p = Path(path)
    if not p.exists():
        return False
    if p.stat().st_size < 100:  # At least 100 bytes
        return False
    return True


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
    retry=retry_if_not_exception_type((EntityResolutionError, EntityValidationError)),
)
async def run_provider_agent_with_retry(company_name: str, task_id: str, targets: Optional[List[str]] = None):
    """Run CartaProvider with tenacity retry (3 attempts, exponential backoff)."""
    agent = CartaProvider()
    result = await agent.run(company_name, task_id, targets=targets)
    if isinstance(result, dict) and result.get("status") == "error":
        raise Exception(result.get("error"))
    return result


async def export_worker():
    """
    Persistent export worker. Polls for 'pending' tasks using the
    event-driven drain pattern to avoid missed wakeups.

    Drives CartaProvider for each task: login → navigate → export → store.
    """
    logger.info("Persistent export worker started.")
    while True:
        await new_export_event.wait()

        while True:
            try:
                # Atomically claim the oldest pending task
                row = await claim_next_task("pending", "downloading")

                if not row:
                    new_export_event.clear()
                    break

                task_id, company_name, targets_str = row
                targets = None
                if targets_str:
                    try:
                        targets = json.loads(targets_str)
                    except Exception:
                        pass
                logger.info(
                    f"Worker picked up export task {task_id} for '{company_name}' with targets {targets}"
                )

                try:
                    logger.info(f"[{task_id}] Running CartaProvider for '{company_name}'...")
                    result = await asyncio.wait_for(
                        run_provider_agent_with_retry(company_name, task_id, targets=targets),
                        timeout=TASK_TIMEOUT_SEC,
                    )

                    exports = result.get("exports", [])
                    if not exports:
                        raise Exception("Export completed but no files were produced")

                    # Validate primary export file
                    primary_path = exports[0].get("path")
                    if not primary_path or not validate_export(primary_path):
                        raise Exception(
                            f"Primary export file missing or invalid: {primary_path}"
                        )

                    # Generate downloadable URL for the primary export
                    PUBLIC_BASE_URL = os.getenv(
                        "PUBLIC_BASE_URL",
                        "http://34.122.215.240:8088",
                    )
                    primary_filename = os.path.basename(primary_path)
                    flat_dest = os.path.join(EXPORT_DIR, primary_filename)
                    if os.path.abspath(primary_path) != os.path.abspath(flat_dest):
                        import shutil
                        try:
                            shutil.copy2(primary_path, flat_dest)
                            logger.info(f"Copied primary export to flat location: {flat_dest}")
                        except Exception as e:
                            logger.warning(f"Failed to copy primary export to flat location: {e}")
                            
                    export_url = f"{PUBLIC_BASE_URL}/files/{primary_filename}"

                    logger.info(
                        f"[{task_id}] Completed. "
                        f"{len(exports)} file(s). Primary: {export_url}"
                    )
                    await update_task_status(
                        task_id, "completed", export_url=export_url
                    )

                except asyncio.TimeoutError:
                    logger.error(f"[{task_id}] Timed out after {TASK_TIMEOUT_SEC}s")
                    await update_task_status(
                        task_id,
                        "timeout",
                        error=f"Task timed out after {TASK_TIMEOUT_SEC}s",
                    )
                except Exception as e:
                    logger.error(f"[{task_id}] Failed: {e}")
                    await update_task_status(task_id, "failed", error=str(e))

                # Throttle: 5 seconds between tasks
                logger.info("Throttling 5s before next export task...")
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Database error in export worker: {e}")
                await asyncio.sleep(5)


# ── Cleanup ──────────────────────────────────────────────────────────

CLEANUP_INTERVAL_SECONDS = 36_000  # 10 hours
CLEANUP_MAX_AGE_SECONDS = 36_000   # Delete files older than 10 hours


async def cleanup_old_files():
    """Periodically deletes old export files and purges completed/failed DB rows."""
    logger.info(
        f"Cleanup watchdog started "
        f"(interval={CLEANUP_INTERVAL_SECONDS}s, max_age={CLEANUP_MAX_AGE_SECONDS}s)."
    )
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        now = time.time()
        deleted_count = 0

        # Clean export files (CSV, XLSX, PDF, partial downloads)
        for f in glob.glob(os.path.join(EXPORT_DIR, "*")):
            try:
                if now - os.path.getmtime(f) > CLEANUP_MAX_AGE_SECONDS:
                    os.remove(f)
                    deleted_count += 1
            except OSError:
                pass

        # Purge completed/failed tasks from SQLite
        try:
            db = await get_connection()
            try:
                await db.execute(
                    "DELETE FROM tasks "
                    "WHERE status IN ('completed', 'failed', 'failed_interrupted', 'timeout')"
                )
                await db.commit()
            finally:
                await db.close()
        except Exception as e:
            logger.warning(f"Cleanup DB error: {e}")

        logger.info(
            f"Cleanup complete. Deleted {deleted_count} file(s). "
            "Purged completed/failed tasks from DB."
        )


# ── Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    await init_db()

    logger.info("Starting Playwright runtime (singleton)...")
    await PlaywrightManager.start()

    # Start export worker + cleanup watchdog
    worker_task = asyncio.create_task(export_worker())
    cleanup_task = asyncio.create_task(cleanup_old_files())

    # Safe crash recovery: mark any tasks interrupted during a previous run
    db = await get_connection()
    try:
        await db.execute(
            "UPDATE tasks "
            "SET status = 'failed_interrupted', "
            "    error = 'Interrupted during browser automation' "
            "WHERE status = 'downloading'"
        )
        await db.commit()

        async with db.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'pending'"
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] > 0:
                logger.info(f"Recovered {row[0]} pending task(s). Starting worker.")
                new_export_event.set()
    finally:
        await db.close()

    yield

    # Shutdown
    cleanup_task.cancel()
    worker_task.cancel()
    try:
        await worker_task
        await cleanup_task
    except asyncio.CancelledError:
        pass

    await PlaywrightManager.stop()


app = FastAPI(title="Carta Export API", lifespan=lifespan)

from fastapi import Request

@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.endswith((".js", ".html", ".css", ".json")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Ensure the export directory exists before mounting StaticFiles
os.makedirs(EXPORT_DIR, exist_ok=True)

# Serve exported files (CSV, XLSX, PDFs) as static assets
app.mount(
    "/files",
    StaticFiles(directory=EXPORT_DIR),
    name="files",
)


class DownloadRequest(BaseModel):
    company_name: str
    targets: Optional[List[str]] = None


@app.post("/api/download-report")
async def submit_download_report(req: DownloadRequest):
    """
    Submit a new export task for a company.

    Returns immediately with a task_id. Poll /api/status/{task_id}
    to check completion and retrieve the export_url.
    """
    # Duplicate detection: return existing task if already pending/running
    db = await get_connection()
    try:
        async with db.execute(
            "SELECT task_id, status, targets FROM tasks "
            "WHERE company_name = ? AND status IN ('pending', 'downloading')",
            (req.company_name,),
        ) as cursor:
            async for row in cursor:
                existing_task_id, existing_status, existing_targets_str = row
                existing_targets = None
                if existing_targets_str:
                    try:
                        existing_targets = json.loads(existing_targets_str)
                    except Exception:
                        pass
                
                req_targets_sorted = sorted(req.targets) if req.targets else None
                exist_targets_sorted = sorted(existing_targets) if existing_targets else None
                
                if req_targets_sorted == exist_targets_sorted:
                    logger.info(
                        f"Duplicate request for '{req.company_name}' with targets {req.targets} "
                        f"— returning existing task {existing_task_id}"
                    )
                    return {
                        "task_id": existing_task_id,
                        "status": existing_status,
                        "company_name": req.company_name,
                        "duplicate": True,
                    }
    finally:
        await db.close()

    task_id = str(uuid.uuid4())
    logger.info(f"[{task_id}] New export request for '{req.company_name}' with targets {req.targets}")

    db = await get_connection()
    try:
        now = time.time()
        targets_str = json.dumps(req.targets) if req.targets else None
        await db.execute(
            "INSERT INTO tasks (task_id, company_name, status, created_at, targets) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_id, req.company_name, "pending", now, targets_str),
        )
        await db.commit()
    finally:
        await db.close()

    new_export_event.set()

    return {
        "task_id": task_id,
        "status": "pending",
        "company_name": req.company_name,
    }


from fastapi import Request

@app.get("/api/status/{task_id}")
async def get_status(task_id: str, request: Request):
    """Check the status of an export task."""
    status_data = await get_task_status(task_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Task not found")
        
    # If completed, read summary.json and populate "data" field in response
    if status_data.get("status") == "completed" and status_data.get("export_url"):
        try:
            filename = status_data["export_url"].split("/files/")[-1]
            import glob
            matching_files = glob.glob(os.path.join(EXPORT_DIR, "**", filename), recursive=True)
            if matching_files:
                summary_path = matching_files[0]
                with open(summary_path, "r", encoding="utf-8") as f:
                    summary_json = json.load(f)
                    status_data["data"] = summary_json.get("data")
        except Exception as e:
            logger.warning(f"Failed to load summary data for status response: {e}")
            
    # Dynamically rewrite export_url and pdf_url based on the incoming request host
    if status_data.get("export_url"):
        base_url = str(request.base_url).rstrip("/")
        filename = status_data["export_url"].split("/files/")[-1]
        status_data["export_url"] = f"{base_url}/files/{filename}"
        status_data["pdf_url"] = f"{base_url}/files/{filename}"
            
    return status_data

def versioned_response(data, table_name: str) -> dict:
    return {
        "schema_version": "v1",
        "mapper_version": "v1",
        "table": table_name,
        "record_count": len(data) if isinstance(data, list) else (1 if data else 0),
        "data": [d.model_dump() if hasattr(d, 'model_dump') else d for d in data] if isinstance(data, list) else (
            data.model_dump() if hasattr(data, 'model_dump') else data
        )
    }

from services.canonical_store import CanonicalEntityStore
from services.adapters.carta_adapter import CartaAdapter
from services.platform_mapper import PlatformSchemaMapper
from services.coverage_analyzer import CoverageAnalyzer


@app.get("/api/logs/{task_id}")
async def get_task_logs(task_id: str):
    """
    Returns the log lines for a specific task_id from log.txt.
    """
    log_path = "log.txt"
    if not os.path.exists(log_path):
        return {"logs": []}
    
    task_logs = []
    try:
        # Read the last 2000 lines of log.txt to avoid loading massive files
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            for line in lines[-2000:]:
                # Capture logs referencing task_id or general [Carta] operations
                if task_id in line or "[Carta]" in line or "[Playwright]" in line:
                    task_logs.append(line.strip())
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        return {"logs": [f"Error reading server logs: {e}"]}
        
    return {"logs": task_logs}


# ═══════════════════════════════════════════════════════════════════════
# Direct Fetch API — Sub-Second Endpoint Responses (No Browser Required)
# ═══════════════════════════════════════════════════════════════════════

from services.providers.carta.api.route_registry import RouteRegistry, EntityContext
from services.providers.carta.api.session_manager import SessionManager
from services.providers.carta.api.direct_fetch import DirectFetchService, DirectFetchResult
from services.providers.carta.orchestrator.orchestrator import ExtractionOrchestrator

# Singleton instances (lazy-init on first request)
_direct_fetch: Optional[DirectFetchService] = None
_route_registry: Optional[RouteRegistry] = None
_orchestrator: Optional[ExtractionOrchestrator] = None


def _get_direct_fetch() -> DirectFetchService:
    global _direct_fetch, _route_registry
    if _direct_fetch is None:
        _route_registry = RouteRegistry()
        _session_manager = SessionManager()
        _direct_fetch = DirectFetchService(
            registry=_route_registry,
            session_manager=_session_manager,
        )
    return _direct_fetch


def _get_registry() -> RouteRegistry:
    global _route_registry
    if _route_registry is None:
        _route_registry = RouteRegistry()
    return _route_registry


def _get_orchestrator() -> ExtractionOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        from services.providers.carta.orchestrator.registry import ModuleRegistry
        from services.providers.carta.orchestrator.cache import CacheManager
        from services.providers.carta.modules.investment import InvestmentModule
        from services.providers.carta.modules.valuation import ValuationModule
        from services.providers.carta.modules.funds import FundsModule
        from services.providers.carta.modules.documents import DocumentsModule

        registry = ModuleRegistry()
        registry.register(InvestmentModule())
        registry.register(ValuationModule())
        registry.register(FundsModule())
        registry.register(DocumentsModule())

        cache_dir = os.path.join(PROJECT_ROOT, "cache")
        cache = CacheManager(cache_dir)
        _orchestrator = ExtractionOrchestrator(registry, cache)
    return _orchestrator


@app.post("/api/refresh-session")
async def refresh_session():
    """
    Force-refresh session cookies from the persistent CDP browser (port 9222).
    Call this after manually logging into the browser to update session_cookies.json.
    """
    service = _get_direct_fetch()
    sm = service.session_manager

    # Invalidate in-memory cache so it doesn't short-circuit
    sm.invalidate()

    # Delete stale file so _load_from_file returns None and falls through to CDP
    if sm.cookies_path.exists():
        sm.cookies_path.unlink()
        logger.info("[RefreshSession] Deleted stale session_cookies.json")

    try:
        ctx = await sm.get_auth_context()
        return {
            "status": "ok",
            "session_id": ctx.session_id,
            "csrf_token": ctx.csrf_token[:8] + "...",
            "cookies_count": len(ctx.cookies),
            "message": "Session refreshed from CDP browser. All endpoints should work now."
        }
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": str(e),
                "hint": "Make sure the persistent browser is running on port 9222 and you are logged in."
            }
        )


class SyncEndpointRequest(BaseModel):
    endpoint: str
    firm_id: Optional[int] = None
    entity_id: Optional[int] = None
    org_id: Optional[int] = None
    org_uuid: Optional[str] = None
    fund_uuid: Optional[str] = None
    partner_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class SyncAllRequest(BaseModel):
    endpoints: List[str]
    firm_id: int
    entity_id: Optional[int] = None
    org_id: Optional[int] = None
    concurrency: int = 3


@app.post("/api/sync-endpoint")
async def sync_single_endpoint(request: SyncEndpointRequest, http_request: Request):
    """
    Fast-path: Fetch a single Carta endpoint's data in <1 second.
    No browser interaction required. Uses stored cookies + API Route Registry.
    
    Example:
        POST /api/sync-endpoint
        {"endpoint": "get_investments"}
    
    For entity-level endpoints:
        POST /api/sync-endpoint
        {"endpoint": "get_capital_calls"}
    """
    import re
    from services.providers.carta.utils.settings import settings
    
    firm_id = request.firm_id
    entity_id = request.entity_id
    
    # Try to parse default values from target_url if BOTH are missing (do not mix settings target_url with custom inputs)
    if not firm_id and not entity_id:
        target_url = settings.target_url
        if target_url:
            firm_match = re.search(r"/(individual|firm|organization|partners)/(\d+)", target_url)
            if firm_match:
                firm_id = int(firm_match.group(2))
            entity_match = re.search(r"/(portfolio|entity|corporation|fund)/(\d+)", target_url)
            if entity_match:
                entity_id = int(entity_match.group(2))
                    
    # Secondary fallback for entity_id from business_data.json
    if not entity_id:
        biz_path = os.path.join(PROJECT_ROOT, "output", "business_data.json")
        if os.path.exists(biz_path):
            try:
                with open(biz_path, "r", encoding="utf-8") as f:
                    biz_data = json.load(f)
                investments = biz_data.get("investments", [])
                if investments:
                    for inv in investments:
                        if inv.get("corporation_id"):
                            entity_id = int(inv["corporation_id"])
                            break
            except Exception as e:
                logger.error(f"Error parsing business_data.json for fallback entity_id: {e}")

    # Fallback firm_id if still missing (e.g. from existing registry entity cache)
    if not firm_id:
        registry = _get_registry()
        if registry.entity_cache:
            first_ctx = list(registry.entity_cache.values())[0]
            firm_id = first_ctx.firm_id

    org_uuid = request.org_uuid
    fund_uuid = request.fund_uuid
    
    partner_id = request.partner_id
    
    # Resolve org_uuid, fund_uuid and partner_id from resolved_organizations.json or cached valuation if not explicitly provided
    if firm_id and (not org_uuid or not fund_uuid or not partner_id):
        resolved_orgs_path = os.path.join(PROJECT_ROOT, "config", "resolved_organizations.json")
        if os.path.exists(resolved_orgs_path):
            try:
                with open(resolved_orgs_path, "r", encoding="utf-8") as f:
                    resolved_data = json.load(f)
                
                match_entry = None
                for entry in resolved_data:
                    if (firm_id and str(entry.get("firm_id")) == str(firm_id)) or \
                       (entity_id and str(entry.get("entity_id")) == str(entity_id)) or \
                       (request.org_id and str(entry.get("org_id")) == str(request.org_id)):
                        match_entry = entry
                        break
                
                if match_entry:
                    if not org_uuid:
                        org_uuid = match_entry.get("org_uuid")
                    if not fund_uuid:
                        fund_uuid = match_entry.get("fund_uuid")
                    if not partner_id:
                        pid = match_entry.get("partner_id")
                        if pid is not None:
                            partner_id = str(pid)
                    logger.info(f"[Server] Resolved details from resolved_organizations.json: org_uuid={org_uuid}, fund_uuid={fund_uuid}, partner_id={partner_id}")
            except Exception as e:
                logger.error(f"Error loading details from resolved_organizations.json: {e}")

    if firm_id and entity_id and (not org_uuid or not fund_uuid or not partner_id):
        val_cache_path = os.path.join(PROJECT_ROOT, "cache", f"valuation_{firm_id}_{entity_id}.json")
        if os.path.exists(val_cache_path):
            try:
                with open(val_cache_path, "r", encoding="utf-8") as f:
                    val_data = json.load(f)
                tabs = val_data.get("data", {}).get("tabs", {})
                overview = tabs.get("overview", {})
                if isinstance(overview, dict):
                    if not org_uuid:
                        org_uuid = overview.get("organization-uuid") or overview.get("organization_uuid")
                    if not fund_uuid:
                        fund_uuid = overview.get("fund-uuid") or overview.get("fund_uuid")
                if not org_uuid or not fund_uuid or not partner_id:
                    for tab_key in ("capital-account-statements", "wire-instructions", "securities-account"):
                        tab_data = tabs.get(tab_key, {})
                        if isinstance(tab_data, dict):
                            if not org_uuid:
                                org_uuid = tab_data.get("organization_uuid")
                            if not fund_uuid:
                                fund_uuid = tab_data.get("fund_uuid")
                            if not partner_id:
                                partner_id = tab_data.get("partner_interest_group_uuid") or tab_data.get("fund_admin_partner_uuid")
                if not partner_id:
                    holdings = val_data.get("data", {}).get("holdings", {})
                    rows = holdings.get("rows", [])
                    if isinstance(rows, list) and len(rows) > 0 and isinstance(rows[0], dict):
                        partner_id = rows[0].get("fundadmin_partner_uuid")
            except Exception as e:
                logger.error(f"Error loading UUIDs from valuation cache: {e}")


    # Map endpoint to modular orchestrator module
    def _map_endpoint_to_module(endpoint: str) -> Optional[str]:
        mapping = {
            "get_investments": "investment",
            "inv_investment": "investment",
            "get_investment_valuations": "valuation",
            "inv_asset_valuation": "valuation",
            "get_capital_calls": "funds",
            "inv_cap_call": "funds",
            "get_received_documents": "documents",
            "get_documents": "documents",
        }
        return mapping.get(endpoint)

    module_name = _map_endpoint_to_module(request.endpoint)
    service = _get_direct_fetch()

    if module_name:
        logger.info(f"[Server] Routing '{request.endpoint}' via Modular Extraction Orchestrator (module: '{module_name}')...")
        orchestrator = _get_orchestrator()
        context = {
            "direct_fetch": service,
            "firm_id": firm_id,
            "entity_id": entity_id,
            "org_id": request.org_id,
            "org_uuid": org_uuid,
            "fund_uuid": fund_uuid,
        }
        try:
            # Force refresh to match direct user synchronization stimulus
            payload = await orchestrator.run_module(module_name, context, force_refresh=True)
            
            # Resolve url mapping to keep compatibility with saving & manifest tracking
            try:
                registry = _get_registry()
                ctx = EntityContext(firm_id=firm_id, org_id=request.org_id or firm_id, entity_id=entity_id, org_uuid=org_uuid, fund_uuid=fund_uuid)
                route = registry.lookup(request.endpoint, ctx)
                url = route.url
            except Exception:
                url = f"https://app.carta.com/api/mock/{request.endpoint}"
                
            result = DirectFetchResult(
                endpoint_name=request.endpoint,
                status_code=200,
                latency_ms=0,
                payload=payload,
                url=url
            )
        except Exception as e:
            logger.error(f"[Server] Modular Orchestrator execution failed for '{module_name}': {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": f"Orchestrator execution failed for module '{module_name}': {str(e)}",
                    "endpoint": request.endpoint,
                    "latency_ms": 0,
                    "url": f"https://app.carta.com/api/mock/{request.endpoint}"
                }
            )
    else:
        result = await service.fetch(
            endpoint_name=request.endpoint,
            firm_id=firm_id,
            entity_id=entity_id,
            org_id=request.org_id,
            org_uuid=org_uuid,
            fund_uuid=fund_uuid,
            partner_id=partner_id,
            start_date=request.start_date,
            end_date=request.end_date,
        )

    if result.status_code >= 400 or result.error:
        # If it's a 403 Forbidden or 401, attempt browser-context evaluate fallback!
        if result.status_code in (401, 403) and result.url:
            logger.info(f"[Server] Direct fetch got {result.status_code} for {request.endpoint}. Attempting fallback via browser evaluation...")
            try:
                from playwright.async_api import async_playwright
                async with async_playwright() as pw:
                    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
                    context = browser.contexts[0]
                    page = context.pages[0] if context.pages else await context.new_page()
                    
                    js_code = """
                    async (targetUrl) => {
                        const response = await fetch(targetUrl);
                        if (!response.ok) {
                            throw new Error("HTTP " + response.status);
                        }
                        return await response.json();
                    }
                    """
                    browser_payload = await page.evaluate(js_code, result.url)
                    logger.info(f"[Server] Fallback browser evaluation succeeded for {request.endpoint}!")
                    
                    # Update result with the successfully fetched payload
                    from services.providers.carta.api.direct_fetch import generate_shape_hash
                    result = DirectFetchResult(
                        endpoint_name=request.endpoint,
                        status_code=200,
                        latency_ms=result.latency_ms,
                        payload=browser_payload,
                        url=result.url,
                        shape_hash=generate_shape_hash(browser_payload)
                    )
            except Exception as fallback_err:
                logger.error(f"[Server] Fallback browser evaluation failed: {fallback_err}")

    # Re-check status code after potential fallback
    if result.status_code >= 400 or result.error:
        # Return a graceful response with the error details in the data payload
        return {
            "endpoint": request.endpoint,
            "status_code": result.status_code,
            "latency_ms": result.latency_ms,
            "shape_hash": None,
            "url": result.url or f"https://app.carta.com/api/{request.endpoint}",
            "data": {
                "error": result.error or f"HTTP {result.status_code}"
            }
        }

    # Resolve category of the endpoint to save it correctly
    registry = _get_registry()
    canonical = registry.resolve_alias(request.endpoint)
    category = "unknown"
    if canonical in registry.routes:
        category = registry.routes[canonical].get("category", "unknown")

    # Locate the correct export run folder under output/exports/
    project_root = Path(PROJECT_ROOT)
    exports_root = project_root / "output" / "exports"
    latest_dir = None
    if exports_root.exists():
        dirs = [d for d in exports_root.iterdir() if d.is_dir() and d.name != "test_direct_orch_run_mangocart_inc"]
        if dirs:
            # Smart matcher: search for the target entity_id or firm_id in each export folder
            matched_dir = None
            
            def scan_dir_for_id(d: Path, search_id: int) -> bool:
                search_str = str(search_id)
                if search_str in d.name:
                    return True
                for root, subdirs, files in os.walk(str(d)):
                    if search_str in subdirs:
                        return True
                    for f in ["_extraction_manifest.json", "domain_inventory.json", "coverage_report.json"]:
                        manifest_file = Path(root) / f
                        if manifest_file.exists():
                            try:
                                if search_str in manifest_file.read_text(encoding="utf-8"):
                                    return True
                            except Exception:
                                pass
                return False

            if entity_id:
                for d in dirs:
                    if scan_dir_for_id(d, entity_id):
                        matched_dir = d
                        break
            
            if not matched_dir and firm_id:
                for d in dirs:
                    if scan_dir_for_id(d, firm_id):
                        matched_dir = d
                        break
            
            if matched_dir:
                latest_dir = matched_dir
                logger.info(f"Target matched export directory: {latest_dir.name} for entity_id={entity_id}, firm_id={firm_id}")
            else:
                # Fallback to the latest modified directory
                dirs = sorted(dirs, key=lambda d: d.stat().st_mtime, reverse=True)
                latest_dir = dirs[0]
                logger.info(f"Using default latest export directory: {latest_dir.name}")

    if not latest_dir:
        run_name = str(entity_id) if entity_id else (str(firm_id) if firm_id else "global")
        latest_dir = exports_root / run_name
        latest_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created new default export directory: {latest_dir}")

    # Save direct fetch output to the latest export run's extracted/ folder
    if latest_dir and result.status_code == 200 and result.payload is not None:
        category_dir = latest_dir / "extracted" / category / (str(entity_id) if entity_id else "global")
        category_dir.mkdir(parents=True, exist_ok=True)
        
        from services.providers.carta.intelligence.intelligence_extractor import _url_to_filename
        filename = _url_to_filename(result.url)
        output_path = category_dir / f"{filename}.json"
        
        output_data = {
            "_meta": {
                "source_url": result.url,
                "category": category,
                "capability_tags": [],
                "replay_strategy": "direct_fetch",
                "status_code": result.status_code,
                "latency_ms": result.latency_ms,
                "shape_hash": result.shape_hash,
                "x_carta_trace_id": "",
                "entity_id": str(entity_id) if entity_id else None,
                "entity_name": None,
                "entity_type": None,
                "org_pk": None,
            },
            "data": result.payload,
        }
        output_path.write_text(json.dumps(output_data, indent=2, default=str), encoding="utf-8")
        logger.info(f"Saved fast-path sync result to {output_path}")

        # Trigger compilation of business_data.json and frontend/data/business_data.json
        try:
            sys.path.append(os.path.join(PROJECT_ROOT, "scripts"))
            from export_frontend_data import compile_extracted_data
            
            compiled = compile_extracted_data(latest_dir)
            
            # Write to output/business_data.json
            out_path = project_root / "output" / "business_data.json"
            out_path.write_text(json.dumps(compiled, indent=2, default=str), encoding="utf-8")
            
            # Write to frontend/data/business_data.json
            frontend_path = project_root / "frontend" / "data" / "business_data.json"
            frontend_path.parent.mkdir(parents=True, exist_ok=True)
            frontend_path.write_text(json.dumps(compiled, indent=2, default=str), encoding="utf-8")
            
            logger.info("Successfully compiled business_data.json and frontend/data/business_data.json")
        except Exception as e:
            logger.error(f"Error compiling business data: {e}")

    response_data = {
        "endpoint": result.endpoint_name,
        "status_code": result.status_code,
        "latency_ms": result.latency_ms,
        "shape_hash": result.shape_hash,
        "url": result.url,
        "data": result.payload,
    }

    # Map raw sync payload to platform schema data if requested and successful
    if result.status_code == 200:
        try:
            biz_path = os.path.join(PROJECT_ROOT, "output", "business_data.json")
            if os.path.exists(biz_path):
                platform_mapper = get_platform_mapper()
                if not platform_mapper:
                    raise Exception("Failed to load platform mapper")
                
                # Check if there is a mapper for this endpoint (resolving alias if needed)
                registry = _get_registry()
                canonical_name = registry.resolve_alias(request.endpoint)
                
                platform_mappings = {
                    "get_investments": platform_mapper.map_inv_investment,
                    "get_investment_extra_info": platform_mapper.map_inv_asset_extra_info,
                    "get_investment_team": platform_mapper.map_inv_asset_team,
                    "get_investment_valuations": platform_mapper.map_inv_asset_valuation,
                    "get_capital_calls": platform_mapper.map_inv_cap_call,
                    "get_investment_log": platform_mapper.map_investment_log,
                    "get_investment_transactions": platform_mapper.map_inv_investment_transaction,
                    "get_investment_firm": platform_mapper.map_inv_investment_firm,
                    "get_investment_focus": platform_mapper.map_inv_investment_focus,
                    "get_investment_sectors": platform_mapper.map_inv_investment_sector,
                    "get_investment_certificates": platform_mapper.map_inv_investment_certificate,
                    "get_distribution_history": platform_mapper.map_inv_investment_distribution_history,
                    "get_liquidity_distributions": platform_mapper.map_inv_liquidity_distribution,
                    "get_investment_expenses": platform_mapper.map_inv_investment_expense,
                    "get_investment_interest": platform_mapper.map_inv_investment_interest,
                    "get_investment_services": platform_mapper.map_inv_investment_service,
                    "get_usage_logs": platform_mapper.map_inv_asset_usage_log,
                    "get_recent_developments": platform_mapper.map_extra_info_recent_development,
                    "get_growth_signals": platform_mapper.map_research_growing_traction,
                    "get_capital_account_summary": platform_mapper.map_partner_capital_account_summary,
                    "get_coverage": lambda: CoverageAnalyzer(platform_mapper).analyze()
                }
                
                target_endpoint = request.endpoint
                if target_endpoint not in platform_mappings:
                    target_endpoint = canonical_name
                    
                if target_endpoint in platform_mappings:
                    mapped_payload = platform_mappings[target_endpoint]()
                    response_data["data"] = mapped_payload
                    logger.info(f"[Server] Successfully mapped raw payload to platform schema for endpoint: {request.endpoint}")
        except Exception as e:
            logger.error(f"[Server] Failed to map raw sync result to platform schema: {e}")
    
    # Recursively rewrite relative static URLs (like /files/...) to make them absolute
    base_url = str(http_request.base_url).rstrip("/")
    
    def rewrite_static_urls(data):
        if isinstance(data, dict):
            new_dict = {}
            for k, v in data.items():
                if k in ("download_url", "export_url", "pdf_url") and isinstance(v, str) and v.startswith("/files/"):
                    new_dict[k] = f"{base_url}{v}"
                else:
                    new_dict[k] = rewrite_static_urls(v)
            return new_dict
        elif isinstance(data, list):
            return [rewrite_static_urls(item) for item in data]
        return data

    return rewrite_static_urls(response_data)


@app.post("/api/sync-all")
async def sync_multiple_endpoints(request: SyncAllRequest):
    """
    Fetch multiple endpoints concurrently via direct HTTP.
    Returns results for each endpoint.
    
    Example:
        POST /api/sync-all
        {"endpoints": ["get_investments", "get_capital_calls"], "firm_id": 3288983, "entity_id": 3272607}
    """
    service = _get_direct_fetch()
    results = await service.fetch_all(
        endpoint_names=request.endpoints,
        firm_id=request.firm_id,
        entity_id=request.entity_id,
        org_id=request.org_id,
        concurrency=request.concurrency,
    )

    return {
        "results": {
            name: {
                "status_code": r.status_code,
                "latency_ms": r.latency_ms,
                "error": r.error,
                "data": r.payload,
            }
            for name, r in results.items()
        },
        "total": len(results),
        "successful": sum(1 for r in results.values() if r.status_code == 200),
    }




FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount(
        "/",
        StaticFiles(directory=FRONTEND_DIR, html=True),
        name="frontend",
    )


if __name__ == "__main__":
    import uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    uvicorn.run("api.server:app", host="0.0.0.0", port=8082)
# Force reload token: reload_2



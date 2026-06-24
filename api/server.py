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

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_not_exception_type
# pyrefly: ignore [missing-import]
from loguru import logger
import logging

load_dotenv()

# Configure logging to write to log.txt
logger.add("log.txt", rotation="10 MB", retention="1 week")

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
async def run_provider_agent_with_retry(company_name: str, task_id: str):
    """Run CartaProvider with tenacity retry (3 attempts, exponential backoff)."""
    agent = CartaProvider()
    result = await agent.run(company_name, task_id)
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

                task_id, company_name = row
                logger.info(
                    f"Worker picked up export task {task_id} for '{company_name}'"
                )

                try:
                    logger.info(f"[{task_id}] Running CartaProvider for '{company_name}'...")
                    result = await asyncio.wait_for(
                        run_provider_agent_with_retry(company_name, task_id),
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
                        "http://34.122.215.240:8082",
                    )
                    primary_filename = os.path.basename(primary_path)
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
            "SELECT task_id, status FROM tasks "
            "WHERE company_name = ? AND status IN ('pending', 'downloading')",
            (req.company_name,),
        ) as cursor:
            existing = await cursor.fetchone()
            if existing:
                logger.info(
                    f"Duplicate request for '{req.company_name}' "
                    f"— returning existing task {existing[0]}"
                )
                return {
                    "task_id": existing[0],
                    "status": existing[1],
                    "company_name": req.company_name,
                    "duplicate": True,
                }
    finally:
        await db.close()

    task_id = str(uuid.uuid4())
    logger.info(f"[{task_id}] New export request for '{req.company_name}'")

    db = await get_connection()
    try:
        now = time.time()
        await db.execute(
            "INSERT INTO tasks (task_id, company_name, status, created_at) "
            "VALUES (?, ?, ?, ?)",
            (task_id, req.company_name, "pending", now),
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


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """Check the status of an export task."""
    status_data = await get_task_status(task_id)
    if not status_data:
        raise HTTPException(status_code=404, detail="Task not found")
    return status_data


if __name__ == "__main__":
    import uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    uvicorn.run("api.server:app", host="0.0.0.0", port=8082)

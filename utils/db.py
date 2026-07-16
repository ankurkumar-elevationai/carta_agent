"""
utils/db.py
-----------
Shared SQLite helpers for the OpenClaw task queue.

CRITICAL: Uses WAL journal mode for safe concurrent access across processes.

Provider-agnostic: works for Carta exports, OpenClaw PDFs, and any
future provider that queues download/export tasks.
"""

import os
import json
import time
import logging
import aiosqlite

log = logging.getLogger(__name__)

# Resolve paths relative to the project root, not the current working directory.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "tasks.db")

# Output directory for all provider exports (CSV, XLSX, PDF documents, etc.)
EXPORT_DIR = os.path.join(PROJECT_ROOT, "output", "exports")

# Legacy alias kept for any code that still references PDF_DIR directly
PDF_DIR = EXPORT_DIR


async def get_connection() -> aiosqlite.Connection:
    """
    Create and configure a new aiosqlite connection with production pragmas.
    Caller is responsible for closing the connection.
    """
    db = await aiosqlite.connect(DB_PATH)
    # WAL mode: allows concurrent readers + single writer without blocking
    await db.execute("PRAGMA journal_mode=WAL;")
    # NORMAL sync is safe with WAL and dramatically reduces fsync overhead
    await db.execute("PRAGMA synchronous=NORMAL;")
    # Wait up to 5 seconds if the DB is locked by another process
    await db.execute("PRAGMA busy_timeout=5000;")
    return db


async def init_db():
    """Initialize the task queue schema with indexes for worker polling."""
    os.makedirs(EXPORT_DIR, exist_ok=True)

    db = await get_connection()
    try:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id      TEXT PRIMARY KEY,
                company_name TEXT,
                status       TEXT,
                export_url   TEXT,
                error        TEXT,
                created_at   REAL,
                targets      TEXT
            )
        ''')
        # Index for download worker polling: quickly find oldest pending task
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_tasks_status_created
            ON tasks(status, created_at ASC)
        ''')

        # Safe migration: add columns if upgrading from older schema
        for col, default in [
            ("created_at", "REAL"),
            ("export_url", "TEXT"),
            ("targets", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE tasks ADD COLUMN {col} {default}")
                if col == "created_at":
                    now = time.time()
                    await db.execute(
                        "UPDATE tasks SET created_at = ? WHERE created_at IS NULL",
                        (now,),
                    )
            except Exception:
                pass  # column already exists

        # Migrate legacy pdf_url column → export_url if needed
        try:
            await db.execute(
                "UPDATE tasks SET export_url = pdf_url "
                "WHERE export_url IS NULL AND pdf_url IS NOT NULL"
            )
        except Exception:
            pass  # pdf_url column doesn't exist (clean install)

        await db.commit()
        log.info(f"Database initialized at {DB_PATH} (WAL mode)")
    finally:
        await db.close()


async def update_task_status(
    task_id: str,
    status: str,
    export_url: str = None,
    error: str = None,
    # Legacy parameter alias kept for callers that still use pdf_url=
    pdf_url: str = None,
):
    """Update a task's status and optional metadata fields."""
    # Accept either export_url or pdf_url (legacy compat)
    resolved_url = export_url or pdf_url

    db = await get_connection()
    try:
        query = "UPDATE tasks SET status = ?"
        params = [status]
        if resolved_url is not None:
            query += ", export_url = ?"
            params.append(resolved_url)
        if error is not None:
            query += ", error = ?"
            params.append(error)

        query += " WHERE task_id = ?"
        params.append(task_id)

        await db.execute(query, params)
        await db.commit()
    finally:
        await db.close()


async def get_task_status(task_id: str) -> dict | None:
    """Retrieve a task's current status and result metadata."""
    db = await get_connection()
    try:
        async with db.execute(
            "SELECT status, export_url, error FROM tasks WHERE task_id = ?",
            (task_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

            return {
                "task_id": task_id,
                "status": row[0],
                "export_url": row[1],
                # Legacy alias so downstream consumers that read pdf_url still work
                "pdf_url": row[1],
                "error": row[2],
            }
    finally:
        await db.close()


async def claim_next_task(source_status: str, target_status: str) -> tuple | None:
    """
    Atomically claim the oldest task with source_status by updating it to
    target_status. Returns (task_id, company_name) or None if no tasks available.

    Uses a single UPDATE...RETURNING to prevent race conditions between
    multiple workers or processes.
    """
    db = await get_connection()
    try:
        cursor = await db.execute(
            f'''
            UPDATE tasks
            SET status = ?
            WHERE task_id = (
                SELECT task_id FROM tasks
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
            )
            RETURNING task_id, company_name, targets
            ''',
            (target_status, source_status),
        )
        row = await cursor.fetchone()
        await db.commit()
        return row  # (task_id, company_name, targets) or None
    finally:
        await db.close()

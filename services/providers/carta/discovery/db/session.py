import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

log = logging.getLogger(__name__)

# Base class for SQLAlchemy models
Base = declarative_base()

# Configure engine (fallback to local if not provided in .env)
# Using asyncpg driver for Postgres
DB_URL = os.getenv(
    "DISCOVERY_DB_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/carta_discovery"
)

# Global engine and session maker
try:
    engine = create_async_engine(
        DB_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )
    async_session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )
except Exception as e:
    log.error(f"[DB] Failed to initialize async engine: {e}")
    engine = None
    async_session_maker = None


async def init_db():
    """Create all tables if they don't exist."""
    if engine is None:
        return
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("[DB] Initialized database schemas.")
    except Exception as e:
        log.error(f"[DB] Could not create tables: {e}")


async def get_session() -> AsyncSession:
    """Dependency for getting DB session."""
    if async_session_maker is None:
        raise RuntimeError("Database engine not initialized.")
    async with async_session_maker() as session:
        yield session

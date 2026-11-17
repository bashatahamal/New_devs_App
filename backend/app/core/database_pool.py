import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)


def _async_database_url(url: str) -> str:
    """Return the configured Postgres URL using the asyncpg driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the database connection pool once (safe to call repeatedly)."""
        if self.session_factory is not None:
            return
        async with self._init_lock:
            if self.session_factory is not None:
                return
            try:
                # Async engines use AsyncAdaptedQueuePool by default; QueuePool is rejected.
                self.engine = create_async_engine(
                    _async_database_url(settings.database_url),
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                    pool_timeout=settings.database_pool_timeout,
                    pool_pre_ping=True,  # Validate connections
                    pool_recycle=settings.database_pool_recycle,
                    echo=False  # Set to True for SQL debugging
                )

                self.session_factory = async_sessionmaker(
                    bind=self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False
                )

                logger.info("✅ Database connection pool initialized")

            except Exception as e:
                logger.error(f"❌ Database pool initialization failed: {e}")
                self.engine = None
                self.session_factory = None

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """Yield a database session from the pool and close it afterwards."""
        if not self.session_factory:
            raise RuntimeError("Database pool not initialized")
        async with self.session_factory() as session:
            yield session

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session

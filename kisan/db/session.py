from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from kisan.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    s = get_settings()
    kwargs = {}
    if s.database_url.startswith("postgresql"):
        # PgBouncer in transaction mode sits in front of Citus in prod: disable
        # asyncpg's prepared-statement cache so pooled connections stay safe.
        kwargs = {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_pre_ping": True,
            "connect_args": {"statement_cache_size": 0},
        }
    return create_async_engine(s.database_url, **kwargs)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session

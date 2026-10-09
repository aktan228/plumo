"""Async engine and session factory. Local Postgres, Docker or Supabase."""

from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def normalize_database_url(url: str) -> str:
    """Accept the string Supabase shows (`postgresql://` or `postgres://`) as is."""

    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


def engine_options(url: str) -> tuple[dict[str, Any], bool]:
    """asyncpg connect args and whether to skip the local pool.

    Supabase transaction pooler (port 6543, pgbouncer) drops prepared
    statements between transactions, so the asyncpg statement cache is off and
    statement names are unique. Supabase always needs TLS.
    """

    parts = urlsplit(url.replace("+asyncpg", ""))
    host = parts.hostname or ""
    args: dict[str, Any] = {}
    if host.endswith("supabase.com") or host.endswith("supabase.co"):
        args["ssl"] = "require"
    pooled = parts.port == 6543 or "pooler.supabase.com" in host
    if pooled:
        args["statement_cache_size"] = 0
        args["prepared_statement_name_func"] = lambda: f"__plumo_{uuid4().hex}__"
    return args, pooled


def create_engine(database_url: str, *, null_pool: bool = False) -> AsyncEngine:
    url = normalize_database_url(database_url)
    connect_args, pooled = engine_options(url)
    if null_pool or pooled:
        # pgbouncer already pools; a second pool on top only holds dead connections.
        return create_async_engine(url, poolclass=NullPool, connect_args=connect_args)
    return create_async_engine(url, pool_pre_ping=True, connect_args=connect_args)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

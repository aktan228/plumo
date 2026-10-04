"""Shared fixtures. Integration tests use the plumo_test database."""

import os
from collections.abc import AsyncIterator

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.container import Runtime, build_agent, build_runtime
from app.infrastructure.database.base import Base
from app.infrastructure.database.models import (  # noqa: F401
    BusinessRow,
    ConversationRow,
    CustomerChannelRow,
    CustomerRow,
    CustomerSummaryRow,
    HandoffRequestRow,
    InteractionLogRow,
    KnowledgeItemRow,
    MeetingRow,
    MessageRow,
    UsageLogRow,
)
from app.infrastructure.database.session import create_engine, create_session_factory
from app.main import create_app
from app.seed import seed


def test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://plumo:plumo@localhost:5432/plumo",
    )
    head, _, _name = base.rpartition("/")
    return f"{head}/plumo_test"


def _admin_dsn(url: str) -> str:
    plain = url.replace("postgresql+asyncpg://", "postgresql://")
    head, _, _name = plain.rpartition("/")
    return f"{head}/plumo"


async def _ensure_database() -> None:
    conn = await asyncpg.connect(_admin_dsn(test_database_url()))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'plumo_test'")
        if not exists:
            await conn.execute("CREATE DATABASE plumo_test")
    finally:
        await conn.close()


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    await _ensure_database()
    db = create_engine(test_database_url())
    async with db.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield db
    await db.dispose()


@pytest.fixture
async def session(engine: AsyncEngine):
    factory = create_session_factory(engine)
    async with factory() as db_session:
        for table in reversed(Base.metadata.sorted_tables):
            await db_session.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
        await db_session.commit()
        yield db_session
        await db_session.rollback()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url=test_database_url(),
        ai_mode="mock",
        small_model_provider="mock",
        big_model_provider="mock",
        stt_provider="mock",
        tts_provider="mock",
        language_detector="mock",
        handoff_provider="mock",
        router="rules",
        default_language="ru",
        default_business_id=None,
        log_level="WARNING",
        small_model_confidence_threshold=0.7,
    )


@pytest.fixture
def runtime(settings: Settings, engine: AsyncEngine) -> Runtime:
    return build_runtime(settings, engine=engine)


@pytest.fixture
async def agent(session, runtime):
    await seed(session)
    return build_agent(session, runtime)


@pytest.fixture
async def client(engine: AsyncEngine, settings: Settings):
    factory = create_session_factory(engine)
    async with factory() as db_session:
        for table in reversed(Base.metadata.sorted_tables):
            await db_session.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
        await seed(db_session)
        await db_session.commit()
    app_runtime = build_runtime(settings, engine=engine)
    application = create_app(settings=settings, runtime=app_runtime)
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http

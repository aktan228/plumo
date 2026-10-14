"""Shared fixtures. Integration tests use the plumo_test database."""

import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg
import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.container import Runtime, build_agent, build_runtime
from app.domain.models import Business
from app.infrastructure.channels.credentials import CredentialStore
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
    VoiceCallRow,
)
from app.infrastructure.database.repositories import BusinessRepository
from app.infrastructure.database.session import create_engine, create_session_factory
from app.main import create_app
from app.seed import seed
from app.worker import Worker
from channel_stand import APP_SECRET, IG_TOKEN, TG_TOKEN, FakeProviders, Stand

# A developer's backend/.env may describe a live stand (APP_ENV=stand, MANAGER_PAUSE_HOURS=0).
# Tests run against the defaults the code documents, whatever that file says.
os.environ["APP_ENV"] = "development"
os.environ["MANAGER_PAUSE_HOURS"] = "24"


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


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    await _ensure_database()
    db = create_engine(test_database_url(), null_pool=True)
    async with db.begin() as connection:
        # drop_all first: create_all never alters a table left by an older schema.
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
        await db_session.close()


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
async def client(engine: AsyncEngine, settings: Settings, monkeypatch):
    # A developer .env with PLUMO_API_KEY must not turn the contract tests into 401s.
    monkeypatch.delenv("PLUMO_API_KEY", raising=False)
    factory = create_session_factory(engine)
    async with factory() as db_session:
        for table in reversed(Base.metadata.sorted_tables):
            await db_session.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
        business = await seed(db_session)
        # Dashboard routes need a signed-in operator; the demo business's one by default.
        token = await operator_token(db_session, business.id, "operator@demo.test")
        await db_session.commit()
    app_runtime = build_runtime(settings, engine=engine)
    application = create_app(settings=settings, runtime=app_runtime)
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
        ) as http:
            yield http


TEST_PASSWORD = "operator-password-1"


async def operator_token(db_session, business_id, email: str, name: str = "Азамат") -> str:
    """An operator of `business_id` with a live session; returns the session token."""

    import secrets
    from datetime import UTC, datetime, timedelta

    from app.application.services.auth_service import hash_password, token_hash
    from app.infrastructure.database.channel_repositories import OperatorRepository

    operators = OperatorRepository(db_session)
    operator = await operators.add(
        business_id=business_id, email=email, password_hash=hash_password(TEST_PASSWORD), display_name=name
    )
    token = secrets.token_urlsafe(32)
    await operators.add_session(operator.id, token_hash(token), datetime.now(UTC) + timedelta(hours=1))
    return token


@pytest.fixture
async def stand(engine, settings, monkeypatch, tmp_path):
    monkeypatch.delenv("PLUMO_API_KEY", raising=False)
    monkeypatch.setenv("CHANNEL_SECRET_KEY", "test-channel-secret")
    monkeypatch.setenv("INSTAGRAM_APP_SECRET", APP_SECRET)
    monkeypatch.setenv("INSTAGRAM_VERIFY_TOKEN", "ig-verify-token")
    monkeypatch.setenv("TG_TEST_TOKEN", TG_TOKEN)
    monkeypatch.setenv("IG_TEST_TOKEN", IG_TOKEN)
    factory = create_session_factory(engine)
    async with factory() as db_session:
        for table in reversed(Base.metadata.sorted_tables):
            await db_session.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
        business = await seed(db_session)
        token = await operator_token(db_session, business.id, "operator@demo.test")
        now = datetime.now(UTC)
        other = await BusinessRepository(db_session).add(Business(uuid4(), "Other Shop", "", "", {}, "", now, now))
        other_token = await operator_token(db_session, other.id, "operator@other.test", "Бакыт")
        await db_session.commit()
    credentials = tmp_path / "channel-credentials.json"
    credentials.write_text(
        json.dumps(
            {
                "credentials": [
                    {"ref": "tg-test", "channel": "telegram", "label": "Тестовый бот", "token_env": "TG_TEST_TOKEN", "business_ids": [str(business.id)]},
                    {"ref": "ig-test", "channel": "instagram", "label": "Тестовый Instagram", "token_env": "IG_TEST_TOKEN", "business_ids": [str(business.id)]},
                    {"ref": "tg-other", "channel": "telegram", "label": "Бот другого бизнеса", "token_env": "TG_TEST_TOKEN", "business_ids": [str(other.id)]},
                ]
            }
        ),
        encoding="utf-8",
    )
    stand_settings = settings.model_copy(
        update={"public_base_url": "https://plumo.test", "channel_credentials_file": str(credentials)}
    )
    runtime = build_runtime(stand_settings, engine=engine)
    providers = FakeProviders()
    runtime.channel_gateway.credentials = CredentialStore(str(credentials))
    runtime.channel_gateway.transport = httpx.MockTransport(providers.handler)
    application = create_app(settings=stand_settings, runtime=runtime)
    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application, raise_app_exceptions=False)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
        ) as http:
            yield Stand(
                client=http,
                runtime=runtime,
                providers=providers,
                business=business,
                engine=engine,
                worker=Worker(runtime, worker_id="test-worker"),
                app=application,
                tokens={"own": token, "other": other_token, "other_business": other.id},
            )

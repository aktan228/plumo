"""Readiness reflects only the current published version and the operator's own evidence."""

from uuid import uuid4
from test_onboarding import wizard as wizard
from test_published_agent import publish
from app.domain.models import utcnow
from app.infrastructure.database.models import (
    ChannelConnectionRow,
    TestSessionRow as SandboxSession,
    TestTurnRow as SandboxTurn,
)


async def state(wizard, index=0):
    response = await wizard.http.get(
        "/api/v1/dashboard/readiness", headers={"authorization": f"Bearer {wizard.tokens[index]}"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def part(value, key):
    return next(item for item in value["items"] if item["key"] == key)


async def test_empty_and_published_readiness_is_tenant_scoped(wizard):
    assert (await state(wizard))["completed"] == 0
    assert (await wizard.http.get("/api/v1/dashboard/readiness", headers={"authorization": ""})).status_code == 401
    await publish(wizard)
    own = await state(wizard)
    assert own["completed"] == 2 and part(own, "materials")["count"] == 2
    assert part(own, "test")["status"] == "pending" and own["ready"] is False
    assert (await state(wizard, 1))["completed"] == 0
    guessed = await wizard.http.get("/api/v1/dashboard/readiness", params={"business_id": str(wizard.ids[1])})
    assert guessed.json() == own


async def test_mock_rules_and_obsolete_tests_are_not_live_model_evidence(wizard):
    published = await publish(wizard)
    ident, request = uuid4(), uuid4()
    async with wizard.factory() as db:
        db.add(
            SandboxSession(
                id=ident,
                business_id=wizard.ids[0],
                publication_version=published["version"],
                state={},
                attempts=1,
                paused=False,
            )
        )
        await db.flush()
        db.add(
            SandboxTurn(
                session_id=ident,
                request_id=request,
                text="fictional test",
                status="succeeded",
                result={"mock": True, "model": "mock_small"},
                day="2026-10-25",
                created_at=utcnow(),
            )
        )
        await db.commit()
    assert part(await state(wizard), "test")["status"] == "demo"
    async with wizard.factory() as db:
        row = await db.get(SandboxTurn, (ident, request))
        row.result = {"mock": False, "model": "rules:business_greeting"}
        await db.commit()
    assert part(await state(wizard), "test")["status"] == "started"
    async with wizard.factory() as db:
        row = await db.get(SandboxTurn, (ident, request))
        row.result = {"mock": False, "model": "controlled-provider:test"}
        await db.commit()
    assert part(await state(wizard), "test")["ready"] is True
    assert part(await state(wizard, 1), "test")["ready"] is False
    await publish(wizard)
    assert part(await state(wizard), "test")["status"] == "pending"


async def test_connected_channel_needs_proof_and_errors_revoke_readiness(wizard):
    await publish(wizard)
    ident = uuid4()
    async with wizard.factory() as db:
        db.add(
            ChannelConnectionRow(
                id=ident,
                business_id=wizard.ids[0],
                channel="telegram",
                credential_ref="stored",
                auth_method="bot_token",
                external_account_id="fixture-123",
                display_name="Fictional bot",
                status="connected",
                agent_enabled=False,
                last_check_ok=True,
                details={"telegram_verification": {"state": "pending"}},
            )
        )
        await db.commit()
    assert part(await state(wizard), "channel")["status"] == "connected"
    async with wizard.factory() as db:
        row = await db.get(ChannelConnectionRow, ident)
        row.details = {"telegram_verification": {"state": "verified"}}
        await db.commit()
    assert part(await state(wizard), "channel")["ready"] is True
    async with wizard.factory() as db:
        row = await db.get(ChannelConnectionRow, ident)
        row.agent_enabled = True
        await db.commit()
    assert (await state(wizard))["running"] is True
    assert (await state(wizard, 1))["running"] is False
    async with wizard.factory() as db:
        row = await db.get(ChannelConnectionRow, ident)
        row.status = "error"
        await db.commit()
    assert part(await state(wizard), "channel")["ready"] is False

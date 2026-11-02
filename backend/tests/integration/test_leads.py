"""J-07: a website request is stored first; the team notification may fail without losing it."""

import pytest
from sqlalchemy import func, select

from app.api.routes.leads import LIMITER
from app.application.services.leads import send_due
from app.domain.errors import DeliveryUnknown, ProviderTransientError
from app.infrastructure.database.models import LeadRow


@pytest.fixture(autouse=True)
def fresh_limit():
    LIMITER._failures.clear()
    yield
    LIMITER._failures.clear()


def _lead(key="k" * 20, **extra):
    return {"idempotency_key": key, "source": "landing", "name": "Айжан", "company": "Тестовая студия",
            "email": "Owner@Example.com", "message": "Хотим пилот в Telegram", "plan": "Старт", **extra}


class Team:
    def __init__(self, script=()):
        self.sent, self.script = [], list(script)

    async def send_text(self, chat_id, text):
        step = self.script.pop(0) if self.script else None
        if step is not None:
            raise step
        self.sent.append((chat_id, text))


async def _rows(client):
    async with client._transport.app.state.runtime.session_factory() as session:
        return list((await session.scalars(select(LeadRow))).all())


async def test_repeated_submission_returns_the_same_number(client):
    first = await client.post("/api/v1/leads", json=_lead())
    again = await client.post("/api/v1/leads", json=_lead())
    assert first.status_code == 201 and again.status_code == 201
    assert first.json()["number"] == again.json()["number"]
    rows = await _rows(client)
    assert len(rows) == 1 and rows[0].email == "owner@example.com" and rows[0].notify_status == "queued"


async def test_the_request_survives_a_failing_notification(client, monkeypatch):
    monkeypatch.setenv("TEAM_TELEGRAM_CHAT_ID", "-100777")
    await client.post("/api/v1/leads", json=_lead())
    factory = client._transport.app.state.runtime.session_factory

    team = Team([ProviderTransientError("503")])
    await send_due(factory, team)
    lead = (await _rows(client))[0]
    assert lead.notify_status == "queued" and lead.notify_attempts == 1 and team.sent == []

    async with factory() as session:
        (await session.get(LeadRow, lead.id)).notify_after = func.now()
        await session.commit()
    await send_due(factory, team)
    lead = (await _rows(client))[0]
    assert lead.notify_status == "sent" and team.sent[0][0] == "-100777" and f"№{lead.id}" in team.sent[0][1]


async def test_no_answer_and_no_team_chat_end_without_resending(client, monkeypatch):
    factory = client._transport.app.state.runtime.session_factory
    monkeypatch.setenv("TEAM_TELEGRAM_CHAT_ID", "-100777")
    await client.post("/api/v1/leads", json=_lead("a" * 20))
    await send_due(factory, Team([DeliveryUnknown("timeout")]))
    monkeypatch.delenv("TEAM_TELEGRAM_CHAT_ID")
    await client.post("/api/v1/leads", json=_lead("b" * 20))
    await send_due(factory, Team())
    states = sorted((row.notify_status, row.notify_error) for row in await _rows(client))
    assert states == [("cancelled", "team_chat_not_configured"), ("failed", "notify_rejected")]


async def test_too_many_requests_from_one_address(client):
    for number in range(5):
        assert (await client.post("/api/v1/leads", json=_lead(f"key-{number:02d}-" + "x" * 12))).status_code == 201
    blocked = await client.post("/api/v1/leads", json=_lead("key-99-" + "x" * 12))
    assert blocked.status_code == 429
    assert len(await _rows(client)) == 5


async def test_fields_are_validated(client):
    for bad in (_lead(business_id="x"), _lead(message="а" * 2001), _lead(email="нет"), _lead(name="a\nb"), _lead(idempotency_key="short")):
        assert (await client.post("/api/v1/leads", json=bad)).status_code == 422
    assert await _rows(client) == []

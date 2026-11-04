"""Exact local-day boundaries, independent metric counts and tenant-scoped journal estimates."""
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from test_onboarding import wizard as wizard
from app.infrastructure.database.models import (
    CustomerRow, ConversationRow, MessageRow, HandoffRequestRow, OutboundMessageRow,
    InteractionLogRow, UsageLogRow, TestSessionRow as SandboxSession, TestTurnRow as SandboxTurn,
)


def stamp(value):
    return datetime.fromisoformat(value + "+00:00")


async def stats(wizard, **params):
    response = await wizard.http.get("/api/v1/dashboard/statistics", params={"date_from": "2026-11-01", "date_to": "2026-11-02", **params})
    assert response.status_code == 200, response.text
    return response.json()


async def test_day_boundaries_counts_status_cohort_and_cost_coverage(wizard):
    own, foreign = wizard.ids
    customer, other_customer = uuid4(), uuid4()
    a, b, other, cli = [uuid4() for _ in range(4)]
    start, next_day, end = stamp("2026-10-31T18:00:00"), stamp("2026-11-01T18:00:00"), stamp("2026-11-02T18:00:00")
    async with wizard.factory() as db:
        db.add_all([CustomerRow(id=customer, business_id=own), CustomerRow(id=other_customer, business_id=foreign)])
        await db.flush()
        for ident, business, person, channel, began in [(a, own, customer, "telegram", start),
                (b, own, customer, "instagram", stamp("2026-11-02T17:59:59")),
                (other, foreign, other_customer, "telegram", start), (cli, own, customer, "cli", start)]:
            db.add(ConversationRow(id=ident, business_id=business, customer_id=person, channel=channel, started_at=began))
        await db.flush()
        for ident, person, role, at in [(a, customer, "assistant", stamp("2026-10-31T17:59:59")),
                (a, customer, "assistant", start), (b, customer, "manager", next_day),
                (a, customer, "assistant", end), (other, other_customer, "assistant", start), (cli, customer, "assistant", start)]:
            db.add(MessageRow(id=uuid4(), conversation_id=ident, customer_id=person, role=role, text="fictional", timestamp=at))
        db.add(HandoffRequestRow(id=uuid4(), customer_id=customer, conversation_id=a, reason="user_requested_human",
                                priority="normal", status="PENDING", created_at=next_day))
        for index, (business, ident, status, at) in enumerate([(own, a, "failed", start), (own, a, "unknown", next_day),
                (own, a, "sent", start), (foreign, a, "failed", start), (own, other, "unknown", start)]):
            db.add(OutboundMessageRow(id=uuid4(), business_id=business, conversation_id=ident, author_role="manager",
                text="fictional", idempotency_key=f"stats-{index}", mode_version=0, status=status, created_at=at))
        for business, ident, person, cost in [(own, a, customer, ".25"), (foreign, other, other_customer, "99"), (own, other, other_customer, "88")]:
            log_id = uuid4()
            db.add(InteractionLogRow(id=log_id, request_id=str(log_id), correlation_id="stats", customer_id=person,
                conversation_id=ident, business_id=business, channel="telegram", language="ru", input_text="fictional",
                route="small", route_reason="test", model="mock_small", confidence=1, response_text="fictional",
                latency_ms=1, estimated_cost=Decimal(cost), created_at=start))
            await db.flush()
            db.add(UsageLogRow(id=uuid4(), interaction_log_id=log_id, request_id=str(log_id), model="mock_small",
                input_tokens=1, output_tokens=1, estimated_cost=Decimal(cost), latency_ms=1, created_at=start))
        await db.commit()
    result = await stats(wizard, business_id=str(foreign))
    assert result["totals"] == {"conversations": 2, "agent_replies": 1, "handoffs": 1, "manager_replies": 1, "failed": 1, "unknown": 1}
    assert result["days"][0] == {"day": "2026-11-01", "conversations": 1, "agent_replies": 1, "handoffs": 0, "manager_replies": 0, "failed": 1, "unknown": 0}
    assert result["days"][1]["manager_replies"] == 1 and result["days"][1]["unknown"] == 1
    for key, value in result["totals"].items():
        assert value == sum(day[key] for day in result["days"])
    assert result["logged_ai_estimate_usd"] == .25 and result["logged_interactions"] == 1
    assert result["mock_interactions"] == 1 and result["cost_coverage"] == "partial_journal_only"
    assert result["timezone"] == "Asia/Bishkek" and "fictional" not in str(result)
    other_result = (await wizard.http.get("/api/v1/dashboard/statistics",
        params={"date_from": "2026-11-01", "date_to": "2026-11-02"},
        headers={"authorization": f"Bearer {wizard.tokens[1]}"})).json()
    assert other_result["totals"]["conversations"] == 1
    assert other_result["totals"]["agent_replies"] == 1
    assert other_result["totals"]["failed"] == 0 and other_result["totals"]["unknown"] == 0
    assert other_result["logged_ai_estimate_usd"] == 99


async def test_no_events_is_zero_but_missing_cost_is_null_and_sandbox_is_excluded(wizard):
    async with wizard.factory() as db:
        ident = uuid4()
        db.add(SandboxSession(id=ident, business_id=wizard.ids[0], publication_version=1, state={}))
        await db.flush()
        db.add(SandboxTurn(session_id=ident, request_id=uuid4(), text="sandbox", status="succeeded", day="2026-11-01",
                           result={"estimated_cost": 99, "handoff": True}, created_at=stamp("2026-11-01T00:00:00")))
        await db.commit()
    result = await stats(wizard)
    assert all(value == 0 for value in result["totals"].values())
    assert len(result["days"]) == 2 and result["logged_ai_estimate_usd"] is None
    assert result["logged_interactions"] == 0
    single = await stats(wizard, date_to="2026-11-01")
    assert len(single["days"]) == 1


async def test_auth_and_period_validation(wizard):
    path = "/api/v1/dashboard/statistics"
    assert (await wizard.http.get(path, headers={"authorization": ""})).status_code == 401
    assert (await wizard.http.get(path, headers={"x-api-key": "wrong"})).status_code == 401
    for params in [{"date_from": "2026-11-02", "date_to": "2026-11-01"},
                   {"date_from": "2026-01-01", "date_to": "2026-11-01"}, {"date_to": "0001-01-01"},
                   {"date_from": "not-a-date"}, {"date_to": "9999-12-31"}]:
        assert (await wizard.http.get(path, params=params)).status_code == 422
    default = (await wizard.http.get(path)).json()
    assert len(default["days"]) == 7

"""Messenger pilot statistics; event counts and delivery-cohort snapshots, not billing."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import Services, current_operator, get_services
from app.application.services.auth_service import OperatorContext
from app.domain.errors import InvalidMessage
from app.domain.models import utcnow

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
BISHKEK = timezone(timedelta(hours=6))
KEYS = ("conversations", "agent_replies", "handoffs", "manager_replies", "failed", "unknown")


class Counts(BaseModel):
    conversations: int = 0
    agent_replies: int = 0
    handoffs: int = 0
    manager_replies: int = 0
    failed: int = 0
    unknown: int = 0


class Day(Counts):
    day: date


class StatisticsOut(BaseModel):
    date_from: date
    date_to: date
    timezone: str
    generated_at: datetime
    totals: Counts
    days: list[Day]
    logged_ai_estimate_usd: float | None
    logged_interactions: int
    mock_interactions: int
    cost_coverage: str


def period(date_from, date_to):
    end = date_to or utcnow().astimezone(BISHKEK).date()
    if not 2000 <= end.year <= 2100:
        raise InvalidMessage("Choose dates within 2000–2100", code="invalid_period")
    start = date_from or end - timedelta(days=6)
    if start > end or (end - start).days > 91 or start.year < 2000 or end.year > 2100:
        raise InvalidMessage("Choose an ordered period of 1–92 days, within 2000–2100", code="invalid_period")
    return start, end


@router.get("/statistics", response_model=StatisticsOut, summary="Статистика мессенджеров своего бизнеса по дням Бишкека")
async def statistics(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
):
    start, end = period(date_from, date_to)
    params = {"business_id": operator.business_id, "start": start, "end": end + timedelta(days=1)}
    # Every metric is aggregated before joining; message/handoff multiplicity cannot inflate counts.
    query = """WITH own AS (
        SELECT id FROM conversations WHERE business_id=:business_id AND channel IN ('telegram','instagram','whatsapp')
    ), events AS (
        SELECT c.started_at AS stamp, 'conversations' AS kind FROM conversations c JOIN own ON own.id=c.id
        UNION ALL SELECT m.timestamp, CASE m.role WHEN 'assistant' THEN 'agent_replies' ELSE 'manager_replies' END
            FROM messages m JOIN own ON own.id=m.conversation_id WHERE m.role IN ('assistant','manager')
        UNION ALL SELECT h.created_at, 'handoffs' FROM handoff_requests h JOIN own ON own.id=h.conversation_id
        UNION ALL SELECT o.created_at, o.status FROM outbound_messages o JOIN own ON own.id=o.conversation_id
            WHERE o.business_id=:business_id AND o.status IN ('failed','unknown')
    ) SELECT timezone('Asia/Bishkek', stamp)::date AS day, kind, count(*) AS count
      FROM events WHERE stamp >= (CAST(:start AS date)::timestamp AT TIME ZONE 'Asia/Bishkek')
        AND stamp < (CAST(:end AS date)::timestamp AT TIME ZONE 'Asia/Bishkek') GROUP BY day, kind ORDER BY day"""
    rows = (await services.session.execute(text(query), params)).mappings()
    days = {start + timedelta(days=index): {key: 0 for key in KEYS} for index in range((end - start).days + 1)}
    for row in rows:
        days[row["day"]][row["kind"]] = row["count"]
    # Partial journal estimate only. Do not double-count usage rows or claim external/provider invoice coverage.
    cost = (await services.session.execute(text("""SELECT count(*) AS samples, sum(l.estimated_cost) AS estimate,
        count(*) FILTER (WHERE l.model LIKE 'mock%') AS mocks
        FROM interaction_logs l JOIN conversations c ON c.id=l.conversation_id
        WHERE l.business_id=:business_id AND c.business_id=:business_id
          AND c.channel IN ('telegram','instagram','whatsapp')
          AND l.created_at >= (CAST(:start AS date)::timestamp AT TIME ZONE 'Asia/Bishkek')
          AND l.created_at < (CAST(:end AS date)::timestamp AT TIME ZONE 'Asia/Bishkek')"""), params)).mappings().one()
    return StatisticsOut(date_from=start, date_to=end, timezone="Asia/Bishkek", generated_at=utcnow(),
        totals=Counts(**{key: sum(day[key] for day in days.values()) for key in KEYS}),
        days=[Day(day=day, **values) for day, values in days.items()],
        logged_ai_estimate_usd=float(cost["estimate"]) if cost["samples"] else None,
        logged_interactions=cost["samples"], mock_interactions=cost["mocks"], cost_coverage="partial_journal_only")

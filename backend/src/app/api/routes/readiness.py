"""Readiness from committed data, scoped to the authenticated operator's business."""

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from app.api.deps import Services, current_operator, get_services
from app.application.services.auth_service import OperatorContext
from app.infrastructure.database.models import (
    BusinessRow,
    ChannelConnectionRow,
    KnowledgeItemRow,
    OutboundMessageRow,
    TestSessionRow,
    TestTurnRow,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/readiness", summary="Готовность своего бизнеса, материалов, теста и канала")
async def readiness(operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    db, business_id = services.session, operator.business_id
    business = await db.get(BusinessRow, business_id)
    publication = (business.profile or {}).get("onboarding_publication") or {}
    version = publication.get("draft_version")
    materials = await db.scalar(
        select(func.count())
        .select_from(KnowledgeItemRow)
        .where(KnowledgeItemRow.business_id == business_id, KnowledgeItemRow.active.is_(True))
    )
    evidence = (0, False, False)
    if version is not None:
        model = TestTurnRow.result["model"].astext
        mock = TestTurnRow.result["mock"].as_boolean()
        query = (
            select(
                func.count(),
                func.bool_or(and_(mock.is_(False), ~model.like("rules:%"), ~model.like("mock%"))),
                func.bool_or(mock.is_(True)),
            )
            .select_from(TestTurnRow)
            .join(TestSessionRow, TestSessionRow.id == TestTurnRow.session_id)
            .where(
                TestSessionRow.business_id == business_id,
                TestSessionRow.publication_version == version,
                TestTurnRow.status == "succeeded",
            )
        )
        evidence = (await db.execute(query)).one()
    tested = bool(evidence[1])
    test_status = "ready" if tested else "demo" if evidence[2] else "started" if evidence[0] else "pending"
    connections = list(
        (
            await db.scalars(
                select(ChannelConnectionRow).where(
                    ChannelConnectionRow.business_id == business_id, ChannelConnectionRow.status != "disconnected"
                )
            )
        ).all()
    )
    channel_ready, running, connected = False, False, False
    for connection in connections:
        healthy = connection.status == "connected" and connection.last_check_ok is True
        connected = connected or healthy
        if connection.auth_method == "bot_token":
            verified = (connection.details.get("telegram_verification") or {}).get("state") == "verified"
        else:
            sent = await db.scalar(
                select(func.count())
                .select_from(OutboundMessageRow)
                .where(
                    OutboundMessageRow.business_id == business_id,
                    OutboundMessageRow.connection_id == connection.id,
                    OutboundMessageRow.status == "sent",
                )
            )
            verified = connection.last_event_at is not None and bool(sent)
        if healthy and verified:
            channel_ready = True
            running = running or connection.agent_enabled
    items = [
        {"key": "business", "status": "ready" if version is not None else "pending", "ready": version is not None},
        {
            "key": "materials",
            "status": "ready" if materials else "pending",
            "ready": bool(materials),
            "count": materials,
        },
        {"key": "test", "status": test_status, "ready": tested},
        {
            "key": "channel",
            "status": "running" if running else "ready" if channel_ready else "connected" if connected else "pending",
            "ready": channel_ready,
        },
    ]
    completed = sum(item["ready"] for item in items)
    return {"items": items, "completed": completed, "total": 4, "ready": completed == 4, "running": running}

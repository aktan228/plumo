"""Tenant-scoped manager binding and delivery visibility; no arbitrary chat id input."""
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import Services, current_operator, get_services
from app.application.services.auth_service import OperatorContext
from app.application.services.manager_recipient import ManagerRecipientService, manager_configured
from app.infrastructure.database.models import ConversationRow, HandoffRequestRow, JobRow, ManagerNotificationRow
from app.domain.errors import InvalidState, NotFound
from app.domain.models import utcnow

router = APIRouter(prefix="/manager-recipient", tags=["manager"])


class VersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int = Field(ge=0, le=2_000_000_000)


class ResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["mark_sent", "mark_failed", "retry"]


def notification_state(job, handoff, attempt, live):
    if attempt and attempt.state in ("unknown", "sent"):
        return attempt.state
    if job.status == "failed":
        return "failed"
    if attempt:
        return attempt.state
    return ("sent" if live else "demo") if handoff.notified_at else job.status


async def output(services, row):
    result = ManagerRecipientService(services.session).output(row, configured=manager_configured() and services.runtime.settings.handoff_provider == "telegram")
    rows = (await services.session.execute(select(JobRow, HandoffRequestRow, ManagerNotificationRow)
        .join(HandoffRequestRow, HandoffRequestRow.id == JobRow.handoff_id)
        .join(ConversationRow, ConversationRow.id == HandoffRequestRow.conversation_id)
        .outerjoin(ManagerNotificationRow, (ManagerNotificationRow.handoff_id == JobRow.handoff_id) & (ManagerNotificationRow.business_id == row.business_id))
        .where(JobRow.business_id == row.business_id, ConversationRow.business_id == row.business_id, JobRow.kind == "notify_handoff")
        .order_by(JobRow.id.desc()).limit(10))).all()
    result["notifications"] = [{"handoff_id": handoff.id, "conversation_id": handoff.conversation_id,
        "state": notification_state(job, handoff, attempt, services.runtime.settings.handoff_provider == "telegram"),
        "error": job.last_error, "updated_at": job.updated_at} for job, handoff, attempt in rows]
    return result


@router.get("")
async def overview(operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    row = await ManagerRecipientService(services.session).get(operator.business_id)
    return await output(services, row)


@router.post("/link")
async def link(body: VersionIn, operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    if services.runtime.settings.handoff_provider != "telegram":
        from app.domain.errors import NotConfigured
        raise NotConfigured("The notification bot is not enabled", code="manager_bot_not_configured")
    row, url = await ManagerRecipientService(services.session).begin(operator.business_id, body.version)
    result = await output(services, row)
    result["link"] = url
    await services.session.commit()
    return result


@router.post("/notifications/{handoff_id}/resolve")
async def resolve(handoff_id: UUID, body: ResolveIn, operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    session = services.session
    job = await session.scalar(select(JobRow)
        .join(HandoffRequestRow, HandoffRequestRow.id == JobRow.handoff_id)
        .join(ConversationRow, ConversationRow.id == HandoffRequestRow.conversation_id)
        .where(JobRow.handoff_id == handoff_id, ConversationRow.business_id == operator.business_id,
        JobRow.business_id == operator.business_id, JobRow.kind == "notify_handoff").with_for_update(of=JobRow))
    if job is None:
        raise NotFound("Notification not found")
    attempt = await session.scalar(select(ManagerNotificationRow).where(
        ManagerNotificationRow.handoff_id == handoff_id, ManagerNotificationRow.business_id == operator.business_id
    ).with_for_update())
    handoff = await session.get(HandoffRequestRow, handoff_id)
    if attempt is None:
        from app.application.services.handoff_notifier import resolve_notification
        await resolve_notification(session, handoff_id, operator.business_id, body.action)
        await session.commit()
        return {"ok": True}
    if job.status != "failed" or handoff.notified_at is not None:
        raise InvalidState("Refresh the notification state before resolving it")
    if body.action == "retry":
        recipient = await ManagerRecipientService(session).get(operator.business_id)
        if not recipient.chat_id:
            raise InvalidState("Confirm a manager recipient first", code="manager_recipient_missing")
        if attempt:
            attempt.state, attempt.updated_at = "retryable", utcnow()
        job.status, job.attempts, job.last_error = "queued", 0, None
        job.run_at, job.finished_at, job.locked_by, job.locked_until = utcnow(), None, None, None
        handoff.notify_status, handoff.notify_error = "queued", None
    else:
        if not attempt or attempt.state != "unknown":
            raise InvalidState("Only an unknown delivery can be marked manually")
        attempt.state = "sent" if body.action == "mark_sent" else "failed"
        handoff.notify_status = attempt.state
        attempt.updated_at = utcnow()
        job.last_error = "confirmed_by_operator" if body.action == "mark_sent" else "marked_failed"
        if body.action == "mark_sent":
            handoff.notified_at, job.status = utcnow(), "done"
    job.updated_at = utcnow()
    handoff.notify_generation += 1
    await session.commit()
    return {"ok": True}


@router.post("/{action}")
async def change(action: str, body: VersionIn, operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    from app.domain.errors import InvalidMessage
    if action not in ("confirm", "disconnect", "cancel"):
        raise InvalidMessage("Unsupported recipient action")
    row = await ManagerRecipientService(services.session).change(operator.business_id, body.version, action, operator.operator_id)
    result = await output(services, row)
    await services.session.commit()
    return result

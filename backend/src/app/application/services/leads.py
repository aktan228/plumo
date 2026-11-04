"""Pilot requests from the website (J-07).

The request is stored first and answered with its number; the team is told afterwards by
the worker (`send_due`), so a Telegram failure never loses a request. The same
idempotency key returns the same number instead of a second request.
"""

import logging
import os
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.domain.errors import ProviderTransientError, ProviderUnavailable
from app.domain.models import utcnow
from app.infrastructure.database.models import LeadRow

logger = logging.getLogger("plumo.leads")

MAX_ATTEMPTS = 6


async def store_lead(session, fields: dict) -> tuple[int, bool]:
    """(number, created). A repeated key returns the first request's number."""

    now = utcnow()
    created = await session.scalar(
        insert(LeadRow)
        .values(**fields, notify_status="queued", notify_attempts=0, notify_after=now, created_at=now)
        .on_conflict_do_nothing(index_elements=[LeadRow.idempotency_key])
        .returning(LeadRow.id)
    )
    if created is not None:
        return created, True
    existing = await session.scalar(select(LeadRow.id).where(LeadRow.idempotency_key == fields["idempotency_key"]))
    return existing, False


def render(lead: LeadRow) -> str:
    """Plain text for the team chat. Contact data goes to the team, never to logs."""

    lines = [f"Заявка №{lead.id} с сайта ({lead.source})", f"Имя: {lead.name}", f"Почта: {lead.email}"]
    if lead.company:
        lines.append(f"Компания: {lead.company}")
    if lead.plan:
        lines.append(f"Тариф: {lead.plan}")
    if lead.message:
        lines += ["", lead.message[:1500]]
    return "\n".join(lines)


async def send_due(session_factory, provider, limit: int = 20) -> int:
    """Tell the team about stored requests. One request per short transaction, locked while sent."""

    chat_id = os.getenv("TEAM_TELEGRAM_CHAT_ID", "").strip()
    handled = 0
    for _ in range(limit):
        async with session_factory() as session:
            lead = await session.scalar(
                select(LeadRow)
                .where(LeadRow.notify_status == "queued", LeadRow.notify_after <= utcnow())
                .order_by(LeadRow.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if lead is None:
                return handled
            handled += 1
            lead.notify_attempts += 1
            if not chat_id:
                lead.notify_status, lead.notify_error = "cancelled", "team_chat_not_configured"
            else:
                try:
                    await provider.send_text(chat_id, render(lead))
                    lead.notify_status, lead.notify_error = "sent", None
                except ProviderTransientError as exc:
                    if lead.notify_attempts >= MAX_ATTEMPTS:
                        lead.notify_status, lead.notify_error = "failed", "retries_exhausted"
                    else:
                        delay = max(30.0 * 2 ** lead.notify_attempts, exc.retry_after or 0.0)
                        lead.notify_after, lead.notify_error = utcnow() + timedelta(seconds=delay), "transient"
                except ProviderUnavailable:
                    # Includes "no answer after sending": not resent automatically, the request itself is safe.
                    lead.notify_status, lead.notify_error = "failed", "notify_rejected"
            await session.commit()
            logger.info("lead_notify", extra={"lead_id": lead.id, "status": lead.notify_status})
    return handled

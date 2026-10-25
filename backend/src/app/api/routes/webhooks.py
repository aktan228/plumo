"""Telegram and Instagram webhooks.

Authenticity is checked first (Telegram secret header, Meta signature over the
raw body). Then the event and its job are stored in one transaction, and only
after commit the provider gets 2xx. No model call happens here: the worker does it.
If the database fails, the provider gets an error and repeats the delivery.
"""

import hmac
import json
import logging
import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import Services, get_services
from app.domain.enums import ConnectionStatus, InboundKind, InboundStatus, JobKind
from app.domain.errors import Forbidden, InvalidMessage, NotConfigured, Unauthorized
from app.domain.models import ChannelConnection, InboundEvent, utcnow
from app.infrastructure.channels.base import ChannelEvent
from app.infrastructure.channels.gateway import channel_secret_key, telegram_webhook_secret
from app.infrastructure.channels.instagram import parse_entry, valid_signature
from app.infrastructure.channels.telegram import parse_update
from app.application.services.telegram_verification import verification_data

logger = logging.getLogger("plumo.webhooks")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

MAX_BODY = 1_000_000
_ACTIONABLE = (InboundKind.text, InboundKind.start, InboundKind.unsupported)


@router.post("/telegram/{connection_id}", summary="Telegram Bot API webhook (X-Telegram-Bot-Api-Secret-Token)")
async def telegram_webhook(connection_id: UUID, request: Request, services: Services = Depends(get_services)) -> dict:
    connection = await services.connections.get(connection_id)
    given = request.headers.get("x-telegram-bot-api-secret-token", "")
    key = channel_secret_key()
    if not key:
        raise NotConfigured("CHANNEL_SECRET_KEY is not set", code="secret_key_missing")
    # The id in the URL only says which secret to expect; it authorizes nothing by itself.
    if (
        connection is None
        or connection.channel != "telegram"
        or connection.status == ConnectionStatus.disconnected
        or not connection.webhook_nonce
        or not hmac.compare_digest(given.encode(), telegram_webhook_secret(connection.id, connection.webhook_nonce, key).encode())
    ):
        raise Unauthorized("webhook secret does not match")
    update = _json(await _body(request))
    event = parse_update(update) if isinstance(update, dict) else None
    if event is not None:
        await _store(services, connection, event)
    await services.session.commit()
    return {"ok": True}


@router.get("/instagram", summary="Meta: проверка callback URL (hub.challenge)", response_class=PlainTextResponse)
async def instagram_verify(
    mode: str = Query(default="", alias="hub.mode"),
    token: str = Query(default="", alias="hub.verify_token"),
    challenge: str = Query(default="", alias="hub.challenge", max_length=200),
) -> PlainTextResponse:
    expected = os.getenv("INSTAGRAM_VERIFY_TOKEN", "").strip()
    if not expected:
        raise NotConfigured("INSTAGRAM_VERIFY_TOKEN is not set", code="instagram_app_not_configured")
    if mode != "subscribe" or not hmac.compare_digest(token.encode(), expected.encode()):
        raise Forbidden("verify token does not match")
    return PlainTextResponse(challenge)


@router.post("/instagram", summary="Meta: события Instagram (X-Hub-Signature-256)")
async def instagram_webhook(request: Request, services: Services = Depends(get_services)) -> dict:
    secret = os.getenv("INSTAGRAM_APP_SECRET", "").strip()
    if not secret:
        raise NotConfigured("INSTAGRAM_APP_SECRET is not set", code="instagram_app_not_configured")
    raw = await _body(request)
    if not valid_signature(secret, raw, request.headers.get("x-hub-signature-256")):
        raise Unauthorized("signature does not match")
    payload = _json(raw)
    if not isinstance(payload, dict) or payload.get("object") != "instagram":
        return {"ok": True}
    stored = skipped = 0
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        account_id = str(entry.get("id") or "")
        # The business comes from our own record of who connected this account, never from the payload.
        connection = await services.connections.active_by_account("instagram", account_id) if account_id else None
        if connection is None:
            skipped += 1
            continue
        for event in parse_entry(entry):
            if await _store(services, connection, event):
                stored += 1
    await services.session.commit()
    if skipped:
        logger.warning("instagram_unknown_account", extra={"entries": skipped})
    return {"ok": True}


async def _store(services: Services, connection: ChannelConnection, event: ChannelEvent) -> bool:
    """Save the event once per (connection, external id); queue the agent if it is a customer message."""

    verification = verification_data(event) if connection.channel == "telegram" else None
    actionable = event.kind in _ACTIONABLE and bool(event.sender_id)
    inbound = InboundEvent(
        id=uuid4(),
        business_id=connection.business_id,
        connection_id=connection.id,
        channel=connection.channel,
        external_event_id=event.external_event_id,
        kind=event.kind if actionable else InboundKind.ignored,
        status=InboundStatus.queued if actionable else InboundStatus.ignored,
        received_at=utcnow(),
        sender_id=event.sender_id,
        provider_message_id=event.provider_message_id,
        text=None if verification else event.text if actionable else None,
        # An ignored update keeps only its type: no names or text of people we will not answer.
        data=verification if verification else event.data if actionable else {"update_type": event.data.get("update_type")},
        provider_time=event.provider_time,
    )
    created = await services.inbound_events.add_if_new(inbound)
    if created and actionable:
        await services.jobs.enqueue(
            kind=JobKind.verify_telegram if verification else JobKind.process_inbound,
            business_id=connection.business_id,
            # One customer's messages are handled one after another, in arrival order.
            ordering_key=f"verify:{connection.id}" if verification else f"in:{connection.id}:{event.sender_id}",
            inbound_event_id=inbound.id,
        )
    await services.connections.touch_event(connection.id)
    if not created:
        logger.info("webhook_duplicate", extra={"connection_id": str(connection.id)})
    return created


async def _body(request: Request) -> bytes:
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise InvalidMessage("webhook body is too large")
    return raw


def _json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise InvalidMessage("webhook body is not JSON") from None

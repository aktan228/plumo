"""Proof that Telegram can deliver to Plumo and accept a control message, without an LLM."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from app.domain.enums import ConnectionStatus, InboundStatus
from app.domain.models import utcnow
from app.infrastructure.channels.base import ChannelError
from app.infrastructure.database.channel_repositories import ConnectionRepository, InboundEventRepository, JobQueue

PREFIX = "/start plumo_check_"
CONFIRMATION = "Подключение Plumo проверено. Вернитесь в кабинет и включите ответы агента, когда будете готовы."


def new_verification():
    return {"state": "pending", "nonce": secrets.token_urlsafe(24), "expires_at": (utcnow() + timedelta(minutes=15)).isoformat()}


def verification_out(connection):
    raw = connection.details.get("telegram_verification") or {}
    state = raw.get("state", "required")
    if state == "pending" and raw.get("expires_at", "") < utcnow().isoformat():
        state = "expired"
    link = None
    if state == "pending" and raw.get("nonce") and connection.username:
        link = f"https://t.me/{connection.username}?start=plumo_check_{raw['nonce']}"
    return {"state": state, "link": link, "expires_at": raw.get("expires_at"), "verified_at": raw.get("verified_at"), "error": raw.get("error")}


def verification_data(event):
    parameter = str(event.data.get("start_parameter") or "")
    if event.kind != "start" or not parameter.startswith("plumo_check_"):
        return None
    code = parameter[len("plumo_check_"):].strip()[:128]
    return {"chat_id": str(event.data.get("chat_id") or ""), "verification_hash": hashlib.sha256(code.encode()).hexdigest()}


class TelegramVerificationWorker:
    def __init__(self, factory, gateway):
        self.factory, self.gateway = factory, gateway

    async def run(self, job, worker_id):
        async with self.factory() as db:
            events, jobs, connections = InboundEventRepository(db), JobQueue(db), ConnectionRepository(db)
            lease = await jobs.get(job.id)
            if not lease or lease.locked_by != worker_id[:64] or lease.attempts != job.attempts or lease.status != "running":
                return
            event = await events.get(job.inbound_event_id)
            connection = await connections.lock(event.connection_id) if event else None
            data = (connection.details.get("telegram_verification") or {}) if connection else {}
            matches = bool(data.get("nonce") and event and hmac.compare_digest(hashlib.sha256(data["nonce"].encode()).hexdigest(), str(event.data.get("verification_hash") or "")))
            if not connection or connection.status != ConnectionStatus.connected or not matches or not data.get("expires_at") or datetime.fromisoformat(data["expires_at"]) < utcnow():
                if event:
                    await events.mark(event.id, InboundStatus.ignored, "verification_invalid")
                if not await jobs.complete(job, worker_id):
                    await db.rollback()
                    return
                await db.commit()
                return
            if data.get("state") == "verified":
                await events.mark(event.id, InboundStatus.processed)
                if not await jobs.complete(job, worker_id):
                    await db.rollback()
                    return
                await db.commit()
                return
            if data.get("state") in ("sending", "unknown"):
                # A previous process may have sent this message before dying; never resend automatically.
                data = {**data, "state": "unknown", "error": "verification_delivery_unknown"}
                connection.details = {**connection.details, "telegram_verification": data}
                await connections.save(connection)
                await events.mark(event.id, InboundStatus.failed, "verification_delivery_unknown")
                if not await jobs.complete(job, worker_id):
                    await db.rollback()
                    return
                await db.commit()
                return
            chat_id = str(event.data.get("chat_id") or "")
            if not chat_id.lstrip("-").isdigit():
                await events.mark(event.id, InboundStatus.ignored, "verification_invalid")
                if not await jobs.complete(job, worker_id):
                    await db.rollback()
                    return
                await db.commit()
                return
            nonce = data["nonce"]
            connection.details = {**connection.details, "telegram_verification": {**data, "state": "sending", "event_id": str(event.id)}}
            await connections.save(connection)
            await db.commit()
        error, provider_id = None, None
        try:
            provider_id = await self.gateway.send_text(connection, chat_id, CONFIRMATION)
        except ChannelError as exc:
            error = exc
        async with self.factory() as db:
            connections, events, jobs = ConnectionRepository(db), InboundEventRepository(db), JobQueue(db)
            lease = await jobs.get(job.id)
            if not lease or lease.locked_by != worker_id[:64] or lease.attempts != job.attempts or lease.status != "running":
                return
            current = await connections.lock(connection.id)
            data = (current.details.get("telegram_verification") or {}) if current else {}
            if not current or current.status != ConnectionStatus.connected or data.get("nonce") != nonce:
                if not await jobs.complete(job, worker_id):
                    await db.rollback()
                    return
                await db.commit()
                return
            if error and error.kind in ("transient", "rate_limited") and job.attempts < job.max_attempts:
                current.details = {**current.details, "telegram_verification": {**data, "state": "pending", "error": error.code}}
                await connections.save(current)
                if not await jobs.retry(job, worker_id, max(2, error.retry_after or 5), error.code):
                    await db.rollback()
                    return
            else:
                outcome = "verified" if error is None else "unknown" if error.kind == "ambiguous" else "failed"
                current.details = {**current.details, "telegram_verification": {**data, "state": outcome, "verified_at": utcnow().isoformat() if not error else None, "provider_message_id": provider_id, "error": error.code if error else None}}
                await connections.save(current)
                await events.mark(event.id, InboundStatus.processed if not error else InboundStatus.failed, error.code if error else None)
                if not await jobs.complete(job, worker_id):
                    await db.rollback()
                    return
            await db.commit()

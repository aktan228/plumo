"""Signed binding, tenant isolation, durable sends and manual unknown resolution."""
import asyncio
import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from test_onboarding import wizard as wizard
from app.container import build_agent
from app.domain.errors import ProviderDeliveryUnknown, ProviderTransientError
from app.domain.models import InboundMessage, utcnow
from app.infrastructure.database.models import JobRow, ManagerNotificationRow, ManagerRecipientRow
from app.worker import Worker

SECRET = "manager-webhook-test-secret-1234567890"


class ScopedRecorder:
    def __init__(self):
        self.calls = []
        self.script = []

    async def notify_to(self, handoff, chat_id):
        self.calls.append((str(handoff.id), chat_id))
        step = self.script.pop(0) if self.script else None
        if step is not None:
            raise step


@pytest.fixture
async def manager(wizard, monkeypatch):
    monkeypatch.setenv("MANAGER_BOT_TOKEN", "12345:test-only")
    monkeypatch.setenv("MANAGER_BOT_USERNAME", "plumo_manager_test_bot")
    monkeypatch.setenv("MANAGER_WEBHOOK_SECRET", SECRET)
    wizard.runtime.settings.handoff_provider = "telegram"
    wizard.runtime.handoff_provider = ScopedRecorder()
    return wizard


def headers(manager, index=0):
    return {"authorization": f"Bearer {manager.tokens[index]}"}


async def overview(manager, index=0):
    response = await manager.http.get("/api/v1/manager-recipient", headers=headers(manager, index))
    assert response.status_code == 200, response.text
    return response.json()


async def new_link(manager, index=0):
    row = await overview(manager, index)
    response = await manager.http.post("/api/v1/manager-recipient/link", json={"version": row["version"]}, headers=headers(manager, index))
    assert response.status_code == 200, response.text
    return response.json()["link"].split("mgr_")[1]


async def event(manager, code, chat_id=101, *, secret=SECRET, chat_type="private", sender=None):
    return await manager.http.post("/api/v1/webhooks/manager-telegram", headers={"x-telegram-bot-api-secret-token": secret}, json={
        "update_id": 1, "message": {"text": f"/start mgr_{code}", "chat": {"id": chat_id, "type": chat_type},
        "from": {"id": chat_id if sender is None else sender, "is_bot": False, "username": f"manager{chat_id}"}},
    })


async def bind(manager, index=0, chat_id=101):
    code = await new_link(manager, index)
    assert (await event(manager, code, chat_id)).status_code == 200
    row = await overview(manager, index)
    response = await manager.http.post("/api/v1/manager-recipient/confirm", json={"version": row["version"]}, headers=headers(manager, index))
    assert response.status_code == 200, response.text
    return response.json()


async def handoff(manager, index=0):
    async with manager.factory() as session:
        result = await build_agent(session, manager.runtime).process_message(InboundMessage(
            channel="telegram", external_user_id=f"manager-test-{uuid4()}", text="Позовите менеджера",
            business_id=manager.ids[index], message_id=str(uuid4()),
        ))
        assert result.handoff_required
        await session.commit()


async def test_binding_is_hashed_signed_one_time_and_explicitly_confirmed(manager):
    code = await new_link(manager)
    async with manager.factory() as session:
        row = await session.get(ManagerRecipientRow, manager.ids[0])
        assert row.pending_hash == hashlib.sha256(code.encode()).hexdigest() and code not in row.pending_hash
    assert (await event(manager, code, secret="forged")).status_code == 401
    assert (await event(manager, code, chat_type="group")).status_code == 200
    assert (await event(manager, code, sender=202)).status_code == 200
    assert (await overview(manager))["candidate"] is None
    assert (await event(manager, code)).status_code == 200
    row = await overview(manager)
    assert row["candidate"]["chat_id"] == "101" and row["recipient"] is None
    assert (await event(manager, code, chat_id=999)).status_code == 200
    assert (await overview(manager))["candidate"]["chat_id"] == "101"
    response = await manager.http.post("/api/v1/manager-recipient/confirm", json={"version": row["version"]})
    assert response.json()["recipient"]["chat_id"] == "101"
    assert (await overview(manager, 1))["recipient"] is None
    assert (await manager.http.post("/api/v1/manager-recipient/confirm", json={"version": row["version"]})).status_code == 409


async def test_dashboard_auth_and_link_generation_cooldown(manager):
    assert (await manager.http.get("/api/v1/manager-recipient", headers={"authorization": ""})).status_code == 401
    assert (await manager.http.post("/api/v1/manager-recipient/link", json={"version": 0}, headers={"x-api-key": "wrong"})).status_code == 401
    code = await new_link(manager)
    row = await overview(manager)
    response = await manager.http.post("/api/v1/manager-recipient/link", json={"version": row["version"]})
    assert response.status_code == 409 and response.json()["code"] == "manager_link_cooldown"
    # Telegram callbacks authenticate independently of the dashboard service/session keys.
    response = await manager.http.post("/api/v1/webhooks/manager-telegram", headers={
        "x-api-key": "", "authorization": "", "x-telegram-bot-api-secret-token": SECRET,
    }, json={"message": {"text": f"/start mgr_{code}", "chat": {"id": 101, "type": "private"}, "from": {"id": 101, "is_bot": False}}})
    assert response.status_code == 200 and (await overview(manager))["candidate"]["chat_id"] == "101"


async def test_expired_link_and_untrusted_form_never_activate_a_chat(manager):
    code = await new_link(manager)
    async with manager.factory() as session:
        await session.execute(update(ManagerRecipientRow).values(expires_at=utcnow() - timedelta(seconds=1)))
        await session.commit()
    await event(manager, code)
    row = await overview(manager)
    assert row["candidate"] is None and row["recipient"] is None
    assert (await manager.http.post("/api/v1/manager-recipient/confirm", json={"version": row["version"]})).status_code == 409
    assert (await manager.http.post("/api/v1/manager-recipient/confirm", json={"version": row["version"], "chat_id": "999"})).status_code == 422
    assert (await manager.http.post("/api/v1/manager-recipient/link", json={"version": 0, "business_id": str(manager.ids[1])})).status_code == 422


async def test_change_keeps_old_recipient_until_confirmation_and_disconnect_revokes(manager):
    row = await bind(manager)
    code = await new_link(manager)
    await event(manager, code, 303)
    row = await overview(manager)
    assert row["recipient"]["chat_id"] == "101" and row["candidate"]["chat_id"] == "303"
    assert (await manager.http.post("/api/v1/manager-recipient/cancel", json={"version": row["version"]}, headers=headers(manager, 1))).status_code == 409
    response = await manager.http.post("/api/v1/manager-recipient/disconnect", json={"version": row["version"]})
    assert response.json()["recipient"] is None and response.json()["candidate"] is None
    await event(manager, code, 303)
    assert (await overview(manager))["recipient"] is None


async def test_notifications_go_only_to_each_tenants_confirmed_recipient(manager):
    await bind(manager, 0, 101)
    await bind(manager, 1, 202)
    await handoff(manager, 0)
    await handoff(manager, 1)
    assert await Worker(manager.runtime).drain() == 2
    assert [chat for _, chat in manager.runtime.handoff_provider.calls] == ["101", "202"]
    a, b = await overview(manager, 0), await overview(manager, 1)
    assert len(a["notifications"]) == len(b["notifications"]) == 1
    assert a["notifications"][0]["state"] == b["notifications"][0]["state"] == "sent"
    assert a["notifications"][0]["handoff_id"] != b["notifications"][0]["handoff_id"]


async def test_missing_recipient_has_no_shared_fallback_and_can_be_retried_after_binding(manager, monkeypatch):
    monkeypatch.setenv("TELEGRAM_MANAGER_CHAT_ID", "999")
    await handoff(manager)
    await Worker(manager.runtime).drain()
    assert manager.runtime.handoff_provider.calls == []
    item = (await overview(manager))["notifications"][0]
    assert item["error"] == "notify_recipient_missing"
    await bind(manager)
    response = await manager.http.post(f"/api/v1/manager-recipient/notifications/{item['handoff_id']}/resolve", json={"action": "retry"})
    assert response.status_code == 200, response.text
    await Worker(manager.runtime).drain()
    assert manager.runtime.handoff_provider.calls[0][1] == "101"


async def test_unknown_delivery_needs_manual_resolution_and_other_tenant_is_denied(manager):
    await bind(manager)
    manager.runtime.handoff_provider.script = [ProviderDeliveryUnknown("unknown")]
    await handoff(manager)
    worker = Worker(manager.runtime)
    await worker.drain()
    item = (await overview(manager))["notifications"][0]
    assert item["state"] == "unknown"
    assert await worker.drain() == 0
    path = f"/api/v1/manager-recipient/notifications/{item['handoff_id']}/resolve"
    assert (await manager.http.post(path, json={"action": "mark_sent"}, headers=headers(manager, 1))).status_code == 404
    assert (await manager.http.post(path, json={"action": "mark_sent"})).status_code == 200
    assert (await overview(manager))["notifications"][0]["state"] == "sent"
    assert len(manager.runtime.handoff_provider.calls) == 1


@pytest.mark.parametrize("disconnect", [False, True])
async def test_crashed_send_is_unknown_after_restart_not_sent_twice(manager, disconnect):
    await bind(manager)
    manager.runtime.handoff_provider.script = [asyncio.CancelledError()]
    await handoff(manager)
    with pytest.raises(asyncio.CancelledError):
        await Worker(manager.runtime).run_once()
    if disconnect:
        row = await overview(manager)
        assert (await manager.http.post("/api/v1/manager-recipient/disconnect", json={"version": row["version"]})).status_code == 200
    async with manager.factory() as session:
        assert (await session.scalar(select(ManagerNotificationRow))).state == "sending"
        await session.execute(update(JobRow).values(status="queued", run_at=utcnow(), locked_by=None, locked_until=None))
        await session.commit()
    await Worker(manager.runtime).drain()
    assert (await overview(manager))["notifications"][0]["state"] == "unknown"
    assert len(manager.runtime.handoff_provider.calls) == 1


async def test_safe_failure_retries_and_manual_unknown_retry_is_explicit(manager):
    await bind(manager)
    manager.runtime.handoff_provider.script = [ProviderTransientError("not sent"), ProviderDeliveryUnknown("timeout")]
    await handoff(manager)
    worker = Worker(manager.runtime)
    await worker.drain()
    async with manager.factory() as session:
        await session.execute(update(JobRow).where(JobRow.status == "queued").values(run_at=utcnow()))
        await session.commit()
    await worker.drain()
    item = (await overview(manager))["notifications"][0]
    assert item["state"] == "unknown"
    response = await manager.http.post(f"/api/v1/manager-recipient/notifications/{item['handoff_id']}/resolve", json={"action": "retry"})
    assert response.status_code == 200, response.text
    await worker.drain()
    assert (await overview(manager))["notifications"][0]["state"] == "sent"
    assert len(manager.runtime.handoff_provider.calls) == 3


async def test_late_result_of_old_attempt_cannot_overwrite_a_manual_retry(manager):
    from types import SimpleNamespace
    from app.application.services.handoff_notifier import HandoffNotifier
    await bind(manager)
    manager.runtime.handoff_provider.script = [ProviderDeliveryUnknown("timeout")]
    await handoff(manager)
    await Worker(manager.runtime).drain()
    async with manager.factory() as session:
        attempt = await session.scalar(select(ManagerNotificationRow))
        old = attempt.generation
        job = SimpleNamespace(handoff_id=attempt.handoff_id, business_id=attempt.business_id)
        # Model a fresh attempt after an explicitly approved retry.
        attempt.state, attempt.generation = "sending", old + 1
        await session.commit()
    notifier = HandoffNotifier(manager.factory, manager.runtime.handoff_provider)
    assert await notifier._attempt(job, "sent", old) is False
    async with manager.factory() as session:
        assert (await session.scalar(select(ManagerNotificationRow))).state == "sending"
    assert await notifier._attempt(job, "sent", old + 1) is True


async def test_mismatched_job_tenant_does_not_expose_or_resolve_a_foreign_handoff(manager):
    await bind(manager)
    manager.runtime.handoff_provider.script = [ProviderDeliveryUnknown("timeout")]
    await handoff(manager)
    await Worker(manager.runtime).drain()
    item = (await overview(manager))["notifications"][0]
    async with manager.factory() as session:
        await session.execute(update(JobRow).values(business_id=manager.ids[1]))
        await session.commit()
    assert (await overview(manager, 1))["notifications"] == []
    response = await manager.http.post(f"/api/v1/manager-recipient/notifications/{item['handoff_id']}/resolve",
        json={"action": "mark_sent"}, headers=headers(manager, 1))
    assert response.status_code == 404

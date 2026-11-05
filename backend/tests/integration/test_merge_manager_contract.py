"""The two manager APIs share one recipient; canonical retries keep the dashboard fence."""
from sqlalchemy import select

from test_onboarding import wizard as wizard
from test_handoff_notify import Recorder, _ask_for_a_manager
from app.application.services.handoff_notifier import HandoffNotifier
from app.infrastructure.database.models import HandoffRequestRow, JobRow, ManagerRecipientRow
from app.infrastructure.database.channel_repositories import JobQueue


async def test_both_manager_apis_share_recipient_and_disconnect_version(wizard):
    async with wizard.factory() as session:
        session.add(ManagerRecipientRow(business_id=wizard.ids[0], chat_id="101", chat_label="Shared manager", version=4))
        await session.commit()
    legacy = (await wizard.http.get("/api/v1/manager-recipient")).json()
    canonical = (await wizard.http.get("/api/v1/manager-notifications")).json()
    assert legacy["recipient"]["name"] == canonical["recipient"]["label"] == "Shared manager"
    result = await wizard.http.post("/api/v1/manager-notifications/disconnect")
    assert result.status_code == 200
    after = (await wizard.http.get("/api/v1/manager-recipient")).json()
    assert after["recipient"] is None and after["version"] > legacy["version"]
    stale = await wizard.http.post("/api/v1/manager-recipient/cancel", json={"version": legacy["version"]})
    assert stale.status_code == 409


async def test_canonical_notification_ignores_an_older_attempt_result(session, runtime):
    runtime.handoff_provider = Recorder()
    await _ask_for_a_manager(session, runtime)
    await session.commit()
    job = await JobQueue(session).claim("merge-worker", 60, ["notify_handoff"])
    await session.commit()
    assert job is not None
    handoff = await session.scalar(select(HandoffRequestRow))
    handoff.notify_status = "sending"
    handoff.notify_generation = 2
    await session.commit()
    notifier = HandoffNotifier(runtime.session_factory, runtime.handoff_provider)
    await notifier._finish(job, "merge-worker", "sent", None, generation=1)
    session.expire_all()
    row = await session.get(HandoffRequestRow, job.handoff_id)
    assert row.notify_status == "sending" and row.notified_at is None
    assert (await session.get(JobRow, job.id)).status == "running"
    await notifier._finish(job, "merge-worker", "sent", None, generation=2)
    session.expire_all()
    assert (await session.get(HandoffRequestRow, job.handoff_id)).notify_status == "sent"


def _start(command: str, chat_id: int) -> dict:
    return {
        "update_id": chat_id,
        "message": {
            "message_id": 1,
            "date": 1761700000,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False, "first_name": "Айбек", "username": "aibek_mgr"},
            "text": command,
        },
    }


async def _both(wizard) -> tuple[dict, dict]:
    legacy = await wizard.http.get("/api/v1/manager-recipient")
    canonical = await wizard.http.get("/api/v1/manager-notifications")
    assert legacy.status_code == canonical.status_code == 200
    return legacy.json(), canonical.json()


# How a canonical status reads in the older API. One recipient, one state.
_LEGACY_STATE = {
    "not_configured": "not_configured",
    "waiting_code": "awaiting_confirmation",
    "awaiting_confirmation": "awaiting_confirmation",
    "ready": "ready",
    "needs_attention": "attention",
}


async def test_both_manager_apis_report_the_same_state_through_a_binding(wizard, monkeypatch):
    """The recommended setup: one service bot under TELEGRAM_BOT_*, webhook signed from CHANNEL_SECRET_KEY."""

    from app.application.services.manager_recipients import manager_webhook_secret

    monkeypatch.setenv("CHANNEL_SECRET_KEY", "test-channel-secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:test-only")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "plumo_service_test_bot")
    for name in ("MANAGER_BOT_TOKEN", "MANAGER_BOT_USERNAME", "MANAGER_WEBHOOK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    wizard.runtime.settings.handoff_provider = "telegram"
    wizard.runtime.handoff_provider = Recorder()

    async def agree(expected: str) -> tuple[dict, dict]:
        legacy, canonical = await _both(wizard)
        assert canonical["status"] == expected
        assert legacy["state"] == _LEGACY_STATE[expected], (legacy, canonical)
        return legacy, canonical

    await agree("not_configured")
    link = await wizard.http.post("/api/v1/manager-notifications/link")
    assert link.status_code == 200, link.text
    await agree("waiting_code")

    signed = {"X-Telegram-Bot-Api-Secret-Token": manager_webhook_secret("test-channel-secret")}
    accepted = await wizard.http.post("/api/v1/webhooks/telegram-manager", json=_start(link.json()["command"], 4401), headers=signed)
    assert accepted.status_code == 200
    legacy, canonical = await agree("awaiting_confirmation")
    assert legacy["candidate"]["chat_id"] == "4401"

    # Either API confirms the same candidate; here the older one.
    confirmed = await wizard.http.post("/api/v1/manager-recipient/confirm", json={"version": legacy["version"]})
    assert confirmed.status_code == 200, confirmed.text
    legacy, canonical = await agree("ready")
    assert legacy["recipient"]["chat_id"] == "4401" and canonical["recipient"]["label"].startswith("Айбек")

    async with wizard.factory() as session:  # Telegram refused a send: the bot was blocked
        row = await session.get(ManagerRecipientRow, wizard.ids[0])
        row.attention = "delivery_rejected"
        await session.commit()
    await agree("needs_attention")

    disconnected = await wizard.http.post("/api/v1/manager-recipient/disconnect", json={"version": legacy["version"]})
    assert disconnected.status_code == 200, disconnected.text
    await agree("not_configured")
    async with wizard.factory() as session:
        row = await session.get(ManagerRecipientRow, wizard.ids[0])
        assert (row.chat_id, row.attention, row.confirmed_at) == (None, None, None)

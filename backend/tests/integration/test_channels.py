"""Telegram and Instagram end to end: webhook → stored event → worker → agent → delivery.

Providers are faked at the HTTP level (tests/channel_stand.py); the database,
webhook routes, worker, agent pipeline and dashboard API are the real ones.
Numbers in test names refer to the acceptance matrix of the task.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from app.infrastructure.database.channel_repositories import JobQueue
from app.infrastructure.database.repositories import ConversationRepository


async def _count(stand, table: str, where: str = "true", **params) -> int:
    rows = await stand.sql(f"SELECT count(*) FROM {table} WHERE {where}", **params)
    return int(rows[0][0])


async def _dialog_id(stand) -> str:
    rows = await stand.sql("SELECT id FROM conversations ORDER BY created_at DESC LIMIT 1")
    return str(rows[0][0])


async def _deliveries(stand) -> list[tuple[str, str, str | None]]:
    rows = await stand.sql("SELECT author_role, status, error_code FROM outbound_messages ORDER BY created_at")
    return [tuple(row) for row in rows]


# ---- webhook authenticity and storage ------------------------------------------------


async def test_19_forged_telegram_secret_is_rejected_before_anything_is_stored(stand):
    connection = await stand.telegram()
    forged = await stand.tg_update(connection, 1, "Привет", secret="not-the-secret")
    assert forged.status_code == 401
    unknown = await stand.client.post(
        "/api/v1/webhooks/telegram/00000000-0000-0000-0000-000000000000", json={"update_id": 2}
    )
    assert unknown.status_code == 401
    assert await _count(stand, "inbound_events") == 0 and await _count(stand, "jobs") == 0
    assert await stand.worker.drain() == 0


async def test_19_forged_instagram_signature_is_rejected(stand):
    await stand.instagram()
    payload = {"object": "instagram", "entry": [{"id": stand.providers.ig_account["user_id"], "messaging": []}]}
    assert (await stand.ig_webhook(payload, secret="wrong-secret")).status_code == 401
    challenge = await stand.client.get(
        "/api/v1/webhooks/instagram",
        params={"hub.mode": "subscribe", "hub.verify_token": "ig-verify-token", "hub.challenge": "12345"},
    )
    assert challenge.status_code == 200 and challenge.text == "12345"
    denied = await stand.client.get(
        "/api/v1/webhooks/instagram",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"},
    )
    assert denied.status_code == 403


async def test_5_6_telegram_message_gets_an_agent_reply_in_the_same_chat(stand):
    connection = await stand.telegram()
    response = await stand.tg_update(connection, 10, "Еще продается квартира за 85000? Саламатсызбы, ң ө ү")
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert stand.providers.sent == []  # nothing is sent from the webhook itself

    assert await stand.worker.drain() == 2  # process the message, then deliver the reply
    assert len(stand.providers.sent) == 1
    sent = stand.providers.sent[0]
    assert sent["chat_id"] == "5550001" and "85 000" in sent["text"]
    assert "ИИ" in sent["text"]  # first reply of a chat discloses the AI

    rows = await stand.sql("SELECT role, text FROM messages ORDER BY seq")
    assert rows[0][1] == "Еще продается квартира за 85000? Саламатсызбы, ң ө ү"
    assert await _deliveries(stand) == [("assistant", "sent", None)]
    dialog = await stand.sql("SELECT channel, connection_id, external_chat_id, contact_name, business_id FROM conversations")
    assert dialog[0][0] == "telegram" and dialog[0][1] == connection.id and dialog[0][2] == "5550001"
    assert dialog[0][3] == "Айгуль" and dialog[0][4] == stand.business.id


async def test_14_duplicate_webhooks_make_one_message_one_model_call_one_send(stand):
    connection = await stand.telegram()
    first, second = await asyncio.gather(
        stand.tg_update(connection, 20, "Еще продается квартира за 85000?"),
        stand.tg_update(connection, 20, "Еще продается квартира за 85000?"),
    )
    assert first.status_code == second.status_code == 200
    again = await stand.tg_update(connection, 20, "Еще продается квартира за 85000?")
    assert again.status_code == 200
    await stand.worker.drain()
    await stand.tg_update(connection, 20, "Еще продается квартира за 85000?")  # after processing
    await stand.worker.drain()
    assert await _count(stand, "inbound_events") == 1
    assert await _count(stand, "messages", "role = 'user'") == 1
    assert await _count(stand, "interaction_logs") == 1
    assert len(stand.providers.sent) == 1


async def test_20_start_and_media_do_not_reach_the_model(stand):
    connection = await stand.telegram()
    await stand.tg_update(connection, 30, "/start")
    await stand.tg_update(connection, 31, None, photo=[{"file_id": "p1"}])
    await stand.tg_update(connection, 32, None, voice={"file_id": "v1"})
    await stand.worker.drain()
    assert await _count(stand, "interaction_logs") == 0
    texts = [item["text"] for item in stand.providers.sent]
    assert len(texts) == 2  # greeting + one "text only" notice, not one per attachment
    assert "ИИ-ассистент" in texts[0]
    assert "только текстовые" in texts[1]
    stored = await stand.sql("SELECT text, metadata->>'unsupported' FROM messages WHERE role = 'user' ORDER BY seq")
    assert [tuple(row) for row in stored] == [("/start", None), ("[photo]", "photo"), ("[voice]", "voice")]


async def test_24_database_failure_means_no_acknowledgement(stand, monkeypatch):
    connection = await stand.telegram()

    from app.infrastructure.database.channel_repositories import InboundEventRepository

    original = InboundEventRepository.add_if_new

    async def broken(self, event):
        raise ConnectionError("database is down")

    monkeypatch.setattr(InboundEventRepository, "add_if_new", broken)
    failed = await stand.tg_update(connection, 40, "Привет")
    assert failed.status_code == 500 and "database" not in failed.text
    assert failed.json()["code"] == "internal_error"
    monkeypatch.setattr(InboundEventRepository, "add_if_new", original)
    assert await _count(stand, "inbound_events") == 0
    # Telegram repeats the update; this time it is stored and answered.
    assert (await stand.tg_update(connection, 40, "Привет")).status_code == 200
    await stand.worker.drain()
    assert len(stand.providers.sent) == 1


async def test_13_24_job_of_a_crashed_worker_is_taken_again_after_its_lease(stand):
    connection = await stand.telegram()
    await stand.tg_update(connection, 50, "Еще продается квартира за 85000?")
    async with stand.factory() as session:
        crashed = await JobQueue(session).claim("dead-worker", 120)
        await session.commit()
    assert crashed is not None
    assert await stand.worker.drain() == 0  # still leased by the dead worker
    await stand.sql("UPDATE jobs SET locked_until = now() - interval '1 second'")
    assert await stand.worker.drain() == 2
    assert len(stand.providers.sent) == 1
    assert await _count(stand, "interaction_logs") == 1


async def test_16_two_quick_messages_of_one_customer_run_in_order(stand):
    connection = await stand.telegram()
    await stand.tg_update(connection, 60, "Еще продается квартира за 85000?")
    await stand.tg_update(connection, 61, "А рассрочка есть?")
    await stand.tg_update(connection, 62, "Привет", chat_id=5550002)  # another customer
    async with stand.factory() as session:
        queue = JobQueue(session)
        first = await queue.claim("w1", 120)
        second = await queue.claim("w2", 120)
        third = await queue.claim("w3", 120)
        await session.commit()
    # The second message of the first customer waits; the other customer runs in parallel.
    assert first.inbound_event_id is not None and second is not None and third is None
    rows = await stand.sql("SELECT external_event_id FROM inbound_events WHERE id IN (:a, :b)", a=first.inbound_event_id, b=second.inbound_event_id)
    assert {row[0] for row in rows} == {"60", "62"}
    await stand.sql("UPDATE jobs SET status = 'queued', locked_until = NULL, locked_by = NULL, attempts = 0")
    await stand.worker.drain()
    users = await stand.sql("SELECT text FROM messages WHERE role = 'user' AND customer_id = (SELECT customer_id FROM messages WHERE text = 'А рассрочка есть?') ORDER BY seq")
    assert [row[0] for row in users] == ["Еще продается квартира за 85000?", "А рассрочка есть?"]


# ---- modes, takeover and manager replies -----------------------------------------------


async def test_12_switched_off_agent_still_receives(stand):
    connection = await stand.telegram(agent_enabled=False)
    await stand.tg_update(connection, 70, "Еще продается квартира за 85000?")
    await stand.worker.drain()
    assert stand.providers.sent == [] and await _count(stand, "interaction_logs") == 0
    assert await _count(stand, "messages", "role = 'user'") == 1
    dialog = await _dialog_id(stand)
    detail = (await stand.client.get(f"/api/v1/conversations/{dialog}")).json()
    assert detail["dialog"]["mode"] == "ai" and detail["connection"]["agent_enabled"] is False
    # Manual work after a takeover stays possible.
    assert (await stand.client.post(f"/api/v1/conversations/{dialog}/takeover")).status_code == 200
    sent = await stand.client.post(
        f"/api/v1/conversations/{dialog}/messages", json={"text": "Здравствуйте! Это Азамат.", "idempotency_key": "key-agent-off-1"}
    )
    assert sent.status_code == 200, sent.text
    await stand.worker.drain()
    assert [item["text"] for item in stand.providers.sent] == ["Здравствуйте! Это Азамат."]


async def test_8_9_10_11_15_takeover_reply_and_return(stand):
    connection = await stand.telegram()
    await stand.tg_update(connection, 80, "Еще продается квартира за 85000?")
    await stand.worker.drain()
    dialog = await _dialog_id(stand)

    taken = await stand.client.post(f"/api/v1/conversations/{dialog}/takeover")
    again = await stand.client.post(f"/api/v1/conversations/{dialog}/takeover")
    assert taken.json()["mode"] == "human" and again.json() == taken.json()
    assert await _count(stand, "handoff_requests", "status = 'ACCEPTED'") == 1
    assert await _count(stand, "messages", "role = 'system'") == 1

    # 9: a customer message in manager mode is stored, the agent stays silent.
    await stand.tg_update(connection, 81, "Алло, вы тут?")
    await stand.worker.drain()
    assert len(stand.providers.sent) == 1 and await _count(stand, "interaction_logs") == 1

    # 10 + 15: one manager command → one operation, even when the request is repeated.
    body = {"text": "Здравствуйте, это Азамат. Квартира свободна.", "idempotency_key": "send-0001-abc"}
    first, second = await asyncio.gather(
        stand.client.post(f"/api/v1/conversations/{dialog}/messages", json=body),
        stand.client.post(f"/api/v1/conversations/{dialog}/messages", json=body),
    )
    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert {first.json()["created"], second.json()["created"]} == {True, False}
    assert first.json()["delivery"]["id"] == second.json()["delivery"]["id"]
    assert first.json()["delivery"]["status"] == "queued"
    await stand.worker.drain()
    assert stand.providers.sent[-1]["text"] == body["text"] and len(stand.providers.sent) == 2
    detail = (await stand.client.get(f"/api/v1/conversations/{dialog}")).json()
    managers = [item for item in detail["messages"] if item["role"] == "manager"]
    assert len(managers) == 1 and managers[0]["delivery"]["status"] == "sent" and managers[0]["author"] == "Азамат"

    # 11: back to the agent; the manager input is closed and the next message gets the agent.
    resumed = await stand.client.post(f"/api/v1/conversations/{dialog}/resume")
    assert resumed.json()["mode"] == "ai"
    blocked = await stand.client.post(
        f"/api/v1/conversations/{dialog}/messages", json={"text": "ещё", "idempotency_key": "send-0002-abc"}
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "mode_conflict"
    await stand.tg_update(connection, 82, "А рассрочка есть?")
    await stand.worker.drain()
    assert len(stand.providers.sent) == 3
    assert await _count(stand, "handoff_requests", "status = 'ACCEPTED'") == 0


async def test_17_takeover_while_the_agent_reply_waits_cancels_it(stand):
    connection = await stand.telegram()
    await stand.tg_update(connection, 90, "Еще продается квартира за 85000?")
    assert await stand.worker.run_once()  # the agent answered; delivery is queued, not sent
    assert await _deliveries(stand) == [("assistant", "queued", None)]
    dialog = await _dialog_id(stand)
    assert (await stand.client.post(f"/api/v1/conversations/{dialog}/takeover")).status_code == 200
    await stand.worker.drain()
    assert stand.providers.sent == []
    assert await _deliveries(stand) == [("assistant", "cancelled", "mode_changed")]
    detail = (await stand.client.get(f"/api/v1/conversations/{dialog}")).json()
    agent = [item for item in detail["messages"] if item["role"] == "assistant"][0]
    assert agent["delivery"]["status"] == "cancelled"


async def test_17_takeover_during_generation_cancels_the_late_reply(stand, monkeypatch):
    """The manager takes the dialog while the model is still writing: the result is never sent."""

    connection = await stand.telegram()
    await stand.tg_update(connection, 91, "Здравствуйте")
    await stand.worker.drain()
    assert len(stand.providers.sent) == 1
    dialog = await _dialog_id(stand)
    from app.application.services.agent_service import AgentService

    original = AgentService._generate
    took_over = asyncio.Event()

    async def slow_generate(self, *args, **kwargs):
        # The worker's transaction is open and the message is inserted: the takeover must not wait for it.
        response = await asyncio.wait_for(stand.client.post(f"/api/v1/conversations/{dialog}/takeover"), timeout=5)
        assert response.status_code == 200
        took_over.set()
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(AgentService, "_generate", slow_generate)
    await stand.tg_update(connection, 92, "Еще продается квартира за 85000?")
    await stand.worker.drain()
    assert took_over.is_set()
    assert len(stand.providers.sent) == 1
    assert (await _deliveries(stand))[-1] == ("assistant", "cancelled", "mode_changed")


async def test_18_return_to_agent_cancels_a_pending_manager_message(stand):
    connection = await stand.telegram()
    await stand.tg_update(connection, 100, "Привет")
    await stand.worker.drain()
    dialog = await _dialog_id(stand)
    await stand.client.post(f"/api/v1/conversations/{dialog}/takeover")
    sent = await stand.client.post(
        f"/api/v1/conversations/{dialog}/messages", json={"text": "Сейчас уточню", "idempotency_key": "late-manager-1"}
    )
    assert sent.status_code == 200
    await stand.client.post(f"/api/v1/conversations/{dialog}/resume")
    await stand.worker.drain()
    assert [item["text"] for item in stand.providers.sent if item["text"] == "Сейчас уточню"] == []
    assert ("manager", "cancelled", "mode_changed") in await _deliveries(stand)
    # A cancelled manager line is not shown to the model as said.
    async with stand.factory() as session:
        from app.infrastructure.database.repositories import MessageRepository

        customer = (await ConversationRepository(session).get(__import__("uuid").UUID(dialog))).customer_id
        context = await MessageRepository(session).list_context(customer)
    assert "Сейчас уточню" not in [item.text for item in context]


# ---- delivery failures -----------------------------------------------------------------


async def test_21_rate_limit_is_retried_without_a_second_model_call(stand):
    connection = await stand.telegram()
    stand.providers.fail(
        "sendMessage", (429, {"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 30}})
    )
    await stand.tg_update(connection, 110, "Еще продается квартира за 85000?")
    await stand.worker.drain()
    rows = await stand.sql("SELECT status, error_code FROM outbound_messages")
    assert tuple(rows[0]) == ("queued", "telegram_rate_limited")  # waits for Telegram's retry_after
    waits = await stand.sql("SELECT run_at - now() > interval '25 seconds' FROM jobs WHERE status = 'queued'")
    assert waits[0][0] is True
    await stand.sql("UPDATE jobs SET run_at = now() WHERE status = 'queued'")
    await stand.worker.drain()
    assert await _deliveries(stand) == [("assistant", "sent", None)]
    assert stand.providers.calls.count("sendMessage") == 2
    assert await _count(stand, "interaction_logs") == 1
    attempts = await stand.sql("SELECT attempts FROM outbound_messages")
    assert attempts[0][0] == 2


async def test_21_transient_failures_stop_after_the_retry_limit(stand):
    connection = await stand.telegram()
    refused = httpx.ConnectError("refused")
    stand.providers.fail("sendMessage", refused, refused, refused, refused, refused)
    await stand.tg_update(connection, 111, "Привет")
    await stand.worker.drain()
    for _ in range(5):
        await stand.sql("UPDATE jobs SET run_at = now() WHERE status = 'queued'")
        await stand.worker.drain()
    assert await _deliveries(stand) == [("assistant", "failed", "retries_exhausted")]
    assert stand.providers.calls.count("sendMessage") == 4


async def test_22_ambiguous_timeout_is_unknown_and_not_resent(stand):
    connection = await stand.telegram()
    stand.providers.fail("sendMessage", httpx.ReadTimeout("timed out"))
    await stand.tg_update(connection, 120, "Привет")
    await stand.worker.drain()
    await stand.sql("UPDATE jobs SET run_at = now()")
    await stand.worker.drain()
    assert await _deliveries(stand) == [("assistant", "unknown", "telegram_timeout")]
    assert stand.providers.calls.count("sendMessage") == 1
    delivery = (await stand.sql("SELECT id FROM outbound_messages"))[0][0]
    marked = await stand.client.post(f"/api/v1/outbound-messages/{delivery}/resolve", json={"action": "mark_sent"})
    assert marked.status_code == 200 and marked.json()["status"] == "sent"


async def test_22_worker_crash_during_sending_becomes_unknown(stand):
    connection = await stand.telegram()
    await stand.tg_update(connection, 121, "Привет")
    assert await stand.worker.run_once()
    await stand.sql("UPDATE outbound_messages SET status = 'sending'")
    await stand.worker.drain()
    assert await _deliveries(stand) == [("assistant", "unknown", "interrupted")]
    assert stand.providers.sent == []


async def test_4_revoked_token_needs_action_and_stops_retries(stand):
    connection = await stand.telegram()
    stand.providers.fail("sendMessage", (401, {"ok": False, "description": "Unauthorized"}))
    await stand.tg_update(connection, 130, "Привет")
    await stand.worker.drain()
    assert await _deliveries(stand) == [("assistant", "failed", "token_invalid")]
    integrations = (await stand.client.get("/api/v1/integrations")).json()
    telegram = next(item for item in integrations["channels"] if item["channel"] == "telegram")
    assert telegram["status"] == "action_required"
    assert telegram["connection"]["last_error"]["code"] == "token_invalid"
    await stand.tg_update(connection, 131, "Ещё раз")
    await stand.worker.drain()
    # Messages keep arriving; with the token broken the agent does not even prepare a reply.
    assert await _count(stand, "messages", "role = 'user'") == 2
    assert stand.providers.calls.count("sendMessage") == 1


# ---- integrations ----------------------------------------------------------------------


async def test_1_2_connect_telegram(stand):
    wrong = await stand.client.post("/api/v1/integrations/telegram/connect", json={"credential_ref": "missing"})
    assert wrong.status_code == 404 and wrong.json()["code"] == "credential_not_found"
    stand.providers.fail("getMe", (401, {"ok": False, "description": "Unauthorized"}))
    invalid = await stand.client.post("/api/v1/integrations/telegram/connect", json={"credential_ref": "tg-test"})
    assert invalid.status_code == 422 and invalid.json()["code"] == "invalid_credential"
    assert "AAtest" not in invalid.text
    assert await _count(stand, "channel_connections") == 0

    stand.providers.webhook_url = "https://other-system.example/hook"
    conflict = await stand.client.post("/api/v1/integrations/telegram/connect", json={"credential_ref": "tg-test"})
    assert conflict.status_code == 409 and conflict.json()["code"] == "webhook_conflict"
    assert stand.providers.webhook_url == "https://other-system.example/hook"

    replaced = await stand.client.post(
        "/api/v1/integrations/telegram/connect", json={"credential_ref": "tg-test", "replace_webhook": True}
    )
    assert replaced.status_code == 200, replaced.text
    body = replaced.json()
    assert body["status"] == "connected" and body["agent_enabled"] is False
    assert body["account"] == {
        "external_id": "777000",
        "display_name": "Plumo Test",
        "username": "plumo_test_bot",
        "link": "https://t.me/plumo_test_bot",
    }
    assert stand.providers.webhook_url == f"https://plumo.test/api/v1/webhooks/telegram/{body['id']}"
    listed = (await stand.client.get("/api/v1/integrations")).json()
    assert "AAtest" not in str(listed) and "IGQVJ" not in str(listed) and "test-channel-secret" not in str(listed)

    patched = await stand.client.patch(
        f"/api/v1/integrations/{body['id']}", json={"agent_enabled": True, "version": body["version"]}
    )
    assert patched.status_code == 200 and patched.json()["agent_enabled"] is True
    stale = await stand.client.patch(f"/api/v1/integrations/{body['id']}", json={"agent_enabled": False, "version": body["version"]})
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    checked = await stand.client.post(f"/api/v1/integrations/{body['id']}/check")
    assert checked.json()["status"] == "connected" and checked.json()["last_check_ok"] is True


async def test_failed_webhook_names_the_public_url_and_does_not_block_another_bot(stand):
    stand.providers.fail(
        "setWebhook",
        (400, {"ok": False, "description": "Bad Request: bad webhook: Failed to resolve host: Name or service not known"}),
    )
    first = await stand.client.post("/api/v1/integrations/telegram/connect", json={"credential_ref": "tg-test"})
    assert first.status_code == 422 and first.json()["code"] == "public_url_unreachable"
    rows = await stand.sql("SELECT status, last_error_code, last_error_message FROM channel_connections")
    assert rows[0][0] == "error" and rows[0][1] == "public_url_unreachable"
    assert "PUBLIC_BASE_URL" in rows[0][2] and "Bad Request" not in rows[0][2]

    # The failed attempt held the Telegram slot: a different bot used to get "already_connected".
    stand.providers.bot = {**stand.providers.bot, "id": 888000, "username": "other_test_bot"}
    second = await stand.client.post("/api/v1/integrations/telegram/connect", json={"credential_ref": "tg-test"})
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "connected" and second.json()["account"]["external_id"] == "888000"
    states = await stand.sql("SELECT external_account_id, status FROM channel_connections ORDER BY created_at")
    assert [tuple(row) for row in states] == [("777000", "disconnected"), ("888000", "connected")]


async def test_working_connection_is_not_replaced_by_another_bot(stand):
    first = await stand.client.post("/api/v1/integrations/telegram/connect", json={"credential_ref": "tg-test"})
    assert first.status_code == 200
    stand.providers.bot = {**stand.providers.bot, "id": 888000, "username": "other_test_bot"}
    second = await stand.client.post("/api/v1/integrations/telegram/connect", json={"credential_ref": "tg-test"})
    assert second.status_code == 409 and second.json()["code"] == "already_connected"
    states = await stand.sql("SELECT external_account_id, status FROM channel_connections")
    assert [tuple(row) for row in states] == [("777000", "connected")]


async def test_27_disconnect_cancels_the_queue_and_reconnect_sends_nothing_old(stand):
    connected = await stand.client.post(
        "/api/v1/integrations/telegram/connect", json={"credential_ref": "tg-test"}
    )
    connection_id = connected.json()["id"]
    await stand.client.patch(f"/api/v1/integrations/{connection_id}", json={"agent_enabled": True})
    async with stand.factory() as session:
        from app.infrastructure.database.channel_repositories import ConnectionRepository

        connection = await ConnectionRepository(session).get(__import__("uuid").UUID(connection_id))
    await stand.tg_update(connection, 140, "Еще продается квартира за 85000?")
    assert await stand.worker.run_once()  # reply queued
    gone = await stand.client.post(f"/api/v1/integrations/{connection_id}/disconnect")
    assert gone.json()["status"] == "disconnected" and gone.json()["agent_enabled"] is False
    assert stand.providers.webhook_url == ""
    assert (await stand.tg_update(connection, 141, "Есть кто?")).status_code == 401
    await stand.worker.drain()
    assert stand.providers.sent == []
    assert await _deliveries(stand) == [("assistant", "cancelled", "channel_disconnected")]

    again = await stand.client.post("/api/v1/integrations/telegram/connect", json={"credential_ref": "tg-test"})
    assert again.json()["id"] == connection_id and again.json()["agent_enabled"] is False
    await stand.worker.drain()
    assert stand.providers.sent == []
    assert await _count(stand, "messages", "role = 'user'") == 1  # history kept


async def test_3_4_instagram_connect_and_missing_permission(stand):
    stand.providers.fail("ig:me/subscribed_apps", (403, {"error": {"code": 10, "message": "no permission"}}))
    missing = await stand.client.post("/api/v1/integrations/instagram/connect", json={"credential_ref": "ig-test"})
    assert missing.status_code == 422 and missing.json()["code"] == "missing_permission"
    listed = (await stand.client.get("/api/v1/integrations")).json()
    instagram = next(item for item in listed["channels"] if item["channel"] == "instagram")
    assert instagram["status"] == "action_required"
    assert instagram["webhook_url"] == "https://plumo.test/api/v1/webhooks/instagram"
    ok = await stand.client.post("/api/v1/integrations/instagram/connect", json={"credential_ref": "ig-test"})
    assert ok.status_code == 200 and ok.json()["status"] == "connected"
    assert ok.json()["account"]["username"] == "plumo.test"


# ---- Instagram -------------------------------------------------------------------------


def _ig_payload(account: str, *items) -> dict:
    return {"object": "instagram", "entry": [{"id": account, "time": 1760000000, "messaging": list(items)}]}


def _ig_text(account: str, mid: str, text: str, sender: str = "IGSID-1") -> dict:
    return {"sender": {"id": sender}, "recipient": {"id": account}, "timestamp": 1760000000000, "message": {"mid": mid, "text": text}}


async def test_5_20_instagram_batch_is_answered_in_direct(stand):
    connection = await stand.instagram()
    account = connection.external_account_id
    payload = _ig_payload(
        account,
        _ig_text(account, "mid.1", "Еще продается квартира за 85000?"),
        {"sender": {"id": account}, "recipient": {"id": "IGSID-1"}, "timestamp": 1, "message": {"mid": "mid.echo", "text": "эхо", "is_echo": True}},
        {"sender": {"id": "IGSID-1"}, "recipient": {"id": account}, "timestamp": 2, "read": {"mid": "mid.1"}},
        _ig_text(account, "mid.2", "Здравствуйте", sender="IGSID-2"),
    )
    assert (await stand.ig_webhook(payload)).status_code == 200
    assert (await stand.ig_webhook(payload)).status_code == 200  # Meta retry
    await stand.worker.drain()
    assert await _count(stand, "inbound_events") == 2
    assert sorted(item["chat_id"] for item in stand.providers.sent) == ["IGSID-1", "IGSID-2"]
    assert all(item["channel"] == "instagram" for item in stand.providers.sent)
    assert all(len(item["text"].encode()) <= 1000 for item in stand.providers.sent)
    unknown_account = _ig_payload("999", _ig_text("999", "mid.9", "кто это"))
    assert (await stand.ig_webhook(unknown_account)).status_code == 200
    assert await _count(stand, "inbound_events") == 2


async def test_28_instagram_window_closed_blocks_sending(stand):
    connection = await stand.instagram()
    account = connection.external_account_id
    await stand.ig_webhook(_ig_payload(account, _ig_text(account, "mid.w", "Привет")))
    assert await stand.worker.run_once()
    await stand.sql("UPDATE messages SET timestamp = timestamp - interval '25 hours' WHERE role = 'user'")
    await stand.worker.drain()
    assert await _deliveries(stand) == [("assistant", "failed", "window_closed")]
    dialog = await _dialog_id(stand)
    await stand.client.post(f"/api/v1/conversations/{dialog}/takeover")
    detail = (await stand.client.get(f"/api/v1/conversations/{dialog}")).json()
    assert detail["reply"]["allowed"] is False and detail["reply"]["reason"] == "window_closed"
    refused = await stand.client.post(
        f"/api/v1/conversations/{dialog}/messages", json={"text": "Добрый день", "idempotency_key": "window-closed-1"}
    )
    assert refused.status_code == 422 and refused.json()["code"] == "window_closed"
    assert stand.providers.sent == []


# ---- dashboard: isolation, list, read ----------------------------------------------------


async def test_25_26_other_business_and_anonymous_calls_are_refused(stand):
    connection = await stand.telegram()
    await stand.tg_update(connection, 150, "Еще продается квартира за 85000?")
    await stand.worker.drain()
    dialog = await _dialog_id(stand)
    customer = (await stand.sql("SELECT customer_id FROM conversations"))[0][0]
    delivery = (await stand.sql("SELECT id FROM outbound_messages"))[0][0]
    handoff_rows = await stand.sql("SELECT id FROM handoff_requests")

    other = {"Authorization": f"Bearer {stand.tokens['other']}"}
    probes = [
        ("GET", f"/api/v1/conversations/{dialog}", None),
        ("POST", f"/api/v1/conversations/{dialog}/takeover", None),
        ("POST", f"/api/v1/conversations/{dialog}/resume", None),
        ("POST", f"/api/v1/conversations/{dialog}/read", {"seq": 1}),
        ("POST", f"/api/v1/conversations/{dialog}/messages", {"text": "x", "idempotency_key": "foreign-0001"}),
        ("GET", f"/api/v1/customers/{customer}", None),
        ("GET", f"/api/v1/customers/{customer}/history", None),
        ("GET", f"/api/v1/outbound-messages/{delivery}", None),
        ("POST", f"/api/v1/outbound-messages/{delivery}/resolve", {"action": "mark_failed"}),
        ("POST", f"/api/v1/integrations/{connection.id}/check", None),
        ("PATCH", f"/api/v1/integrations/{connection.id}", {"agent_enabled": False}),
        ("POST", f"/api/v1/integrations/{connection.id}/disconnect", None),
        ("GET", f"/api/v1/metrics?business_id={stand.business.id}", None),
        ("GET", f"/api/v1/knowledge?business_id={stand.business.id}", None),
    ]
    for item in handoff_rows:
        probes.append(("POST", f"/api/v1/handoffs/{item[0]}/accept", None))
    for method, url, body in probes:
        response = await stand.client.request(method, url, json=body, headers=other)
        assert response.status_code == 404, (method, url, response.status_code, response.text)
    listed = await stand.client.get("/api/v1/conversations", headers=other)
    assert listed.json()["items"] == []
    foreign_connect = await stand.client.post(
        "/api/v1/integrations/telegram/connect", json={"credential_ref": "tg-other"}, headers=other
    )
    assert foreign_connect.status_code == 409 and foreign_connect.json()["code"] == "account_in_use"

    anonymous = {"Authorization": ""}
    for method, url, body in probes[:3] + [("GET", "/api/v1/conversations", None), ("GET", "/api/v1/integrations", None)]:
        response = await stand.client.request(method, url, json=body, headers=anonymous)
        assert response.status_code == 401 and response.json()["code"] == "not_authenticated"
    assert await _count(stand, "conversations", "mode = 'human'") == 0


async def test_26_service_key_is_required_when_set(stand, monkeypatch):
    monkeypatch.setenv("PLUMO_API_KEY", "service-key")
    denied = await stand.client.get("/api/v1/conversations")
    assert denied.status_code == 401 and denied.json()["code"] == "unauthorized"
    allowed = await stand.client.get("/api/v1/conversations", headers={"X-API-Key": "service-key"})
    assert allowed.status_code == 200
    login = await stand.client.post(
        "/api/v1/auth/login",
        json={"email": "operator@demo.test", "password": "operator-password-1"},
        headers={"X-API-Key": "service-key", "Authorization": ""},
    )
    assert login.status_code == 200 and login.json()["operator"]["business"]["name"] == "Demo Realty"
    token = login.json()["token"]
    me = await stand.client.get("/api/v1/auth/me", headers={"X-API-Key": "service-key", "Authorization": f"Bearer {token}"})
    assert me.json()["operator"]["email"] == "operator@demo.test"
    out = await stand.client.post("/api/v1/auth/logout", headers={"X-API-Key": "service-key", "Authorization": f"Bearer {token}"})
    assert out.status_code == 204
    after = await stand.client.get("/api/v1/auth/me", headers={"X-API-Key": "service-key", "Authorization": f"Bearer {token}"})
    assert after.status_code == 401
    wrong = await stand.client.post(
        "/api/v1/auth/login",
        json={"email": "operator@demo.test", "password": "nope"},
        headers={"X-API-Key": "service-key", "Authorization": ""},
    )
    assert wrong.status_code == 401 and "password" not in wrong.json().get("token", "")


async def test_29_list_search_filters_pagination_and_read(stand):
    connection = await stand.telegram()
    for index in range(5):
        await stand.tg_update(connection, 200 + index, f"Сообщение номер {index}", chat_id=7000 + index)
    await stand.tg_update(connection, 210, "Ищу квартиру с террасой", chat_id=7002)
    await stand.worker.drain()

    first = (await stand.client.get("/api/v1/conversations", params={"limit": 2})).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = (await stand.client.get("/api/v1/conversations", params={"limit": 2, "cursor": first["next_cursor"]})).json()
    third = (await stand.client.get("/api/v1/conversations", params={"limit": 2, "cursor": second["next_cursor"]})).json()
    ids = [item["id"] for item in first["items"] + second["items"] + third["items"]]
    assert len(ids) == len(set(ids)) == 5 and third["next_cursor"] is None
    assert first["items"][0]["customer"]["name"] == "Айгуль"

    found = (await stand.client.get("/api/v1/conversations", params={"q": "террас"})).json()["items"]
    assert len(found) == 1 and found[0]["unread"] == 2
    assert (await stand.client.get("/api/v1/conversations", params={"q": "100%_"})).json()["items"] == []
    assert len((await stand.client.get("/api/v1/conversations", params={"channel": "instagram"})).json()["items"]) == 0
    assert len((await stand.client.get("/api/v1/conversations", params={"mode": "ai"})).json()["items"]) == 5

    target = found[0]["id"]
    detail = (await stand.client.get(f"/api/v1/conversations/{target}")).json()
    newest = max(item["seq"] for item in detail["messages"])
    read = await stand.client.post(f"/api/v1/conversations/{target}/read", json={"seq": newest + 1000})
    assert read.json()["unread"] == 0 and read.json()["last_read_seq"] == newest
    late = await stand.client.post(f"/api/v1/conversations/{target}/read", json={"seq": 1})
    assert late.json()["last_read_seq"] == newest  # a late request does not move the cursor back
    await stand.tg_update(connection, 211, "И ещё вопрос", chat_id=7002)
    await stand.worker.drain()
    again = (await stand.client.get("/api/v1/conversations", params={"q": "террас"})).json()["items"][0]
    assert again["unread"] == 1
    other = {"Authorization": f"Bearer {stand.tokens['other']}"}
    assert (await stand.client.get("/api/v1/conversations", params={"q": "террас"}, headers=other)).json()["items"] == []


async def test_long_agent_reply_goes_out_in_parts_once(stand, monkeypatch):
    connection = await stand.instagram()
    account = connection.external_account_id
    from app.application.services import agent_service

    long_text = " ".join(["Квартира в центре за 85 000 USD, два санузла и большая кухня."] * 30)

    original = agent_service.AgentService.process_message

    async def long_reply(self, message):
        response = await original(self, message)
        await self.messages.session.execute(
            __import__("sqlalchemy").text("UPDATE messages SET text = :t WHERE id = :i"),
            {"t": long_text, "i": response.reply_message_id},
        )
        response.response_text = long_text
        return response

    monkeypatch.setattr(agent_service.AgentService, "process_message", long_reply)
    await stand.ig_webhook(_ig_payload(account, _ig_text(account, "mid.long", "Привет")))
    stand.providers.fail("ig:me/messages", (200, {"recipient_id": "IGSID-1", "message_id": "mid.part1"}), httpx.ConnectError("refused"))
    await stand.worker.drain()
    await stand.sql("UPDATE jobs SET run_at = now() WHERE status = 'queued'")
    await stand.worker.drain()
    rows = await stand.sql("SELECT status, parts_sent, jsonb_array_length(provider_message_ids) FROM outbound_messages")
    status, parts, ids = rows[0]
    assert status == "sent" and parts == ids and parts > 2
    # The first part is not sent again after the failure on the second one.
    assert stand.providers.calls.count("ig:me/messages") == parts + 1


async def test_unknown_delivery_after_lease_expiry_is_not_resent(stand):
    connection = await stand.telegram()
    await stand.tg_update(connection, 300, "Привет")
    assert await stand.worker.run_once()
    async with stand.factory() as session:
        job = await JobQueue(session).claim("dying-worker", 120)
        await session.commit()
    await stand.sql("UPDATE outbound_messages SET status = 'sending', attempts = 1")
    await stand.sql("UPDATE jobs SET locked_until = now() - interval '1 second' WHERE id = :id", id=job.id)
    await stand.worker.drain()
    assert await _deliveries(stand) == [("assistant", "unknown", "interrupted")]
    assert stand.providers.sent == []


async def test_old_dialog_mode_snapshot(stand):
    """A reply prepared before a takeover and a return still does not go out: the version moved twice."""

    connection = await stand.telegram()
    await stand.tg_update(connection, 310, "Привет")
    assert await stand.worker.run_once()
    dialog = await _dialog_id(stand)
    await stand.client.post(f"/api/v1/conversations/{dialog}/takeover")
    await stand.client.post(f"/api/v1/conversations/{dialog}/resume")
    await stand.worker.drain()
    assert stand.providers.sent == []
    rows = await stand.sql("SELECT mode, mode_version FROM conversations")
    assert tuple(rows[0]) == ("ai", 2)
    assert datetime.now(UTC) - timedelta(minutes=1) < (await stand.sql("SELECT mode_changed_at FROM conversations"))[0][0]


async def test_old_raw_events_lose_text_but_history_stays(stand):
    connection = await stand.telegram(agent_enabled=False)
    await stand.tg_update(connection, 400, "Мой номер 0555 123 456, старое сообщение")
    await stand.worker.drain()
    await stand.tg_update(connection, 401, "Свежее сообщение")
    await stand.sql("UPDATE inbound_events SET received_at = now() - interval '31 days' WHERE external_event_id = '400'")
    await stand.sql("UPDATE inbound_events SET received_at = now() - interval '31 days' WHERE external_event_id = '401'")

    assert await stand.worker.redact_old_events() == 1  # the queued event is not touched
    rows = await stand.sql("SELECT external_event_id, text, data FROM inbound_events ORDER BY external_event_id")
    assert [tuple(row) for row in rows] == [("400", None, {}), ("401", "Свежее сообщение", rows[1][2])]
    assert rows[1][2]["contact_name"] == "Айгуль"
    history = await stand.sql("SELECT text FROM messages WHERE role = 'user'")
    assert [row[0] for row in history] == ["Мой номер 0555 123 456, старое сообщение"]
    assert await stand.worker.redact_old_events() == 0

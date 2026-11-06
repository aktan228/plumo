"""Telegram voice messages end to end: webhook → event → worker → download → STT → agent → delivery.

Telegram and ElevenLabs are faked at the HTTP level (tests/channel_stand.py). The STT adapter,
database, webhook routes, worker, limits and agent pipeline are the real ones.
"""

import json
import logging

import httpx

from app.application.services.agent_service import AgentService
from app.infrastructure.ai.elevenlabs_stt import ElevenLabsSTTProvider
from app.infrastructure.logging.setup import JsonFormatter
from tests.channel_stand import TG_TOKEN, FakeSTT

AUDIO = b"OggS-fake-voice-apartment"
QUESTION = "Еще продается квартира за 85000?"
MOCK_TRANSCRIPT = "Здравствуйте, хочу узнать про квартиру"


def _voice(file_id: str = "voice-file-1", duration: int = 4, **extra) -> dict:
    return {"voice": {"file_id": file_id, "file_unique_id": "uniq-" + file_id, "duration": duration, "mime_type": "audio/ogg", "file_size": len(AUDIO), **extra}}


def _enable(stand, stt: FakeSTT | None = None, **settings) -> FakeSTT:
    """Production mode with voice on and the real ElevenLabs adapter against a fake HTTP API."""

    stt = stt or FakeSTT()
    updated = stand.runtime.settings.model_copy(
        update={"ai_mode": "production", "voice_messages_enabled": True, "stt_provider": "elevenlabs", **settings}
    )
    stand.runtime.settings = updated
    stand.runtime.providers.settings = updated
    stand.runtime.providers.register_stt(
        "elevenlabs", ElevenLabsSTTProvider(api_key="el-test-key", transport=httpx.MockTransport(stt.handler))
    )
    return stt


def _said(stt: FakeSTT, text: str, language: str = "rus", logprob: float = -0.05) -> None:
    words = [{"text": word, "type": "word", "logprob": logprob} for word in text.split()]
    stt.transcripts[AUDIO] = {"text": text, "language_code": language, "language_probability": 0.97, "words": words, "audio_duration_secs": 4.2}


async def _count(stand, table: str, where: str = "true") -> int:
    return int((await stand.sql(f"SELECT count(*) FROM {table} WHERE {where}"))[0][0])


async def test_voice_is_downloaded_transcribed_and_answered_like_text(stand):
    stt = _enable(stand)
    _said(stt, QUESTION)
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()

    response = await stand.tg_update(connection, 900, None, **_voice())
    assert response.status_code == 200
    # The webhook only stores and queues: nothing is downloaded there.
    assert "getFile" not in stand.providers.calls and stt.requests == []
    stored = await stand.sql("SELECT kind, text, data FROM inbound_events")
    assert stored[0][0] == "voice" and stored[0][1] == "[voice]"
    assert set(stored[0][2]) == {"file_id", "file_unique_id", "duration", "mime_type", "file_size", "chat_id", "contact_name"}

    assert await stand.worker.drain() == 2
    assert stand.providers.calls.count("getFile") == 1 and stand.providers.calls.count("download") == 1
    assert len(stt.requests) == 1 and stt.requests[0]["key"] == "el-test-key"
    assert len(stand.providers.sent) == 1 and "85 000" in stand.providers.sent[0]["text"]
    assert await _count(stand, "interaction_logs") == 1

    message = await stand.sql("SELECT text, metadata FROM messages WHERE role = 'user'")
    assert message[0][0] == QUESTION
    meta = message[0][1]
    assert meta["voice"] is True and meta["voice_duration_s"] == 4 and meta["stt_provider"] == "elevenlabs"
    assert meta["voice_status"] == "transcribed"
    event = await stand.sql("SELECT text, data FROM inbound_events")
    assert event[0][0] == QUESTION and event[0][1]["transcribed"] is True and event[0][1]["stt_seconds"] == 4.2
    # Transcription is part of the turn's cost and settled with it.
    cost = await stand.sql("SELECT status, actual, cost_version FROM spend_reservations")
    assert cost[0][0] == "settled" and float(cost[0][1]) >= round(4.2 / 60 * 0.0037, 6)

    dialog = (await stand.client.get("/api/v1/conversations")).json()["items"][0]["id"]
    messages = (await stand.client.get(f"/api/v1/conversations/{dialog}")).json()["messages"]
    customer = next(item for item in messages if item["role"] == "user")
    assert customer["voice"] == {"duration_s": 4, "transcribed": True} and customer["text"] == QUESTION
    assert next(item for item in messages if item["role"] == "assistant")["voice"] is None


async def test_mock_stt_never_reaches_a_customer(stand):
    connection = await stand.telegram()
    # 1: voice off (default): the "text only" line, nothing downloaded.
    stand.providers.files["voice-file-1"] = AUDIO
    await stand.tg_update(connection, 901, None, **_voice())
    await stand.worker.drain()
    # 2: production with voice on, but STT_PROVIDER=mock: the same line.
    updated = stand.runtime.settings.model_copy(update={"ai_mode": "production", "voice_messages_enabled": True, "stt_provider": "mock"})
    stand.runtime.settings = stand.runtime.providers.settings = updated
    await stand.tg_update(connection, 902, "Спасибо")
    await stand.tg_update(connection, 903, None, **_voice("voice-file-2"))
    await stand.worker.drain()
    # 3: AI_MODE=mock with voice on and a provider name: still the line.
    updated = updated.model_copy(update={"ai_mode": "mock", "stt_provider": "elevenlabs"})
    stand.runtime.settings = stand.runtime.providers.settings = updated
    await stand.tg_update(connection, 904, "Хорошо")
    await stand.tg_update(connection, 905, None, **_voice("voice-file-3"))
    await stand.worker.drain()

    assert "getFile" not in stand.providers.calls
    texts = [item["text"] for item in stand.providers.sent]
    assert all(MOCK_TRANSCRIPT not in text for text in texts)
    assert sum("только текстовые" in text for text in texts) == 3
    users = await stand.sql("SELECT text FROM messages WHERE role = 'user' AND metadata->>'voice' = 'true'")
    assert [row[0] for row in users] == ["[voice]"] * 3
    assert await _count(stand, "spend_reservations", "true") == 2  # the two text messages only


async def test_retry_after_a_crash_reuses_the_saved_transcript(stand, monkeypatch):
    stt = _enable(stand)
    _said(stt, QUESTION)
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()
    original = AgentService.process_message
    crashes = []

    async def crash_once(self, message, **kwargs):
        if not crashes:
            crashes.append(message.text)
            raise RuntimeError("worker died after the transcription")
        return await original(self, message, **kwargs)

    monkeypatch.setattr(AgentService, "process_message", crash_once)
    await stand.tg_update(connection, 910, None, **_voice())
    await stand.worker.drain()
    assert crashes == [QUESTION] and stand.providers.sent == []
    await stand.sql("UPDATE jobs SET run_at = now() WHERE status = 'queued'")
    await stand.worker.drain()

    assert len(stand.providers.sent) == 1
    assert stand.providers.calls.count("getFile") == 1 and len(stt.requests) == 1
    assert await _count(stand, "messages", "role = 'user'") == 1


async def test_long_voice_is_refused_without_download_or_spend(stand):
    stt = _enable(stand)
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()
    await stand.tg_update(connection, 920, None, **_voice(duration=121))
    await stand.worker.drain()
    assert "getFile" not in stand.providers.calls and stt.requests == []
    assert await _count(stand, "spend_reservations") == 0 and await _count(stand, "interaction_logs") == 0
    assert len(stand.providers.sent) == 1 and "до 120 секунд" in stand.providers.sent[0]["text"]
    meta = await stand.sql("SELECT metadata->>'voice_status' FROM messages WHERE role = 'user'")
    assert meta[0][0] == "too_long"


async def test_empty_or_filler_transcript_asks_to_repeat_without_the_model(stand):
    stt = _enable(stand)
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()
    _said(stt, "(шум) э-э ммм")
    await stand.tg_update(connection, 930, None, **_voice())
    await stand.worker.drain()
    assert len(stt.requests) == 1 and await _count(stand, "interaction_logs") == 0
    assert len(stand.providers.sent) == 1 and "не расслышал" in stand.providers.sent[0]["text"]
    meta = await stand.sql("SELECT text, metadata->>'voice_status' FROM messages WHERE role = 'user'")
    assert tuple(meta[0]) == ("[voice]", "unclear")
    # The transcription was paid: it is settled, not given back.
    cost = await stand.sql("SELECT status, actual FROM spend_reservations")
    assert cost[0][0] == "settled" and float(cost[0][1]) > 0


async def test_low_confidence_counts_as_unclear_when_the_threshold_is_set(stand):
    stt = _enable(stand, stt_min_confidence=0.5)
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()
    _said(stt, QUESTION, logprob=-3.0)  # mean word probability about 0.05
    await stand.tg_update(connection, 935, None, **_voice())
    await stand.worker.drain()
    assert await _count(stand, "interaction_logs") == 0
    assert "не расслышал" in stand.providers.sent[0]["text"]


async def test_transient_stt_error_retries_and_answers_once(stand):
    stt = _enable(stand)
    _said(stt, QUESTION)
    stt.failures.append(503)
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()
    await stand.tg_update(connection, 940, None, **_voice())
    await stand.worker.drain()
    assert stand.providers.sent == []
    retry = await stand.sql("SELECT status, last_error FROM jobs")
    assert tuple(retry[0]) == ("queued", "provider_transient_error")
    await stand.sql("UPDATE jobs SET run_at = now() WHERE status = 'queued'")
    await stand.worker.drain()
    assert len(stt.requests) == 2 and len(stand.providers.sent) == 1
    assert "85 000" in stand.providers.sent[0]["text"]


async def test_transient_errors_end_in_the_failure_line_on_the_last_attempt(stand):
    stt = _enable(stand)
    stt.failures.extend([503] * 5)
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()
    await stand.tg_update(connection, 945, None, **_voice())
    await stand.worker.drain()
    for _ in range(5):
        await stand.sql("UPDATE jobs SET run_at = now() WHERE status = 'queued'")
        await stand.worker.drain()
    assert len(stand.providers.sent) == 1 and "напишите, пожалуйста, текстом" in stand.providers.sent[0]["text"]
    assert await _count(stand, "messages", "role = 'user'") == 1


async def test_permanent_stt_error_sends_one_failure_line(stand):
    stt = _enable(stand)
    stt.failures.append(401)
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()
    await stand.tg_update(connection, 950, None, **_voice())
    await stand.worker.drain()
    await stand.sql("UPDATE jobs SET run_at = now() WHERE status = 'queued'")
    await stand.worker.drain()
    assert len(stt.requests) == 1 and len(stand.providers.sent) == 1
    assert "Не получилось разобрать голосовое" in stand.providers.sent[0]["text"]
    event = await stand.sql("SELECT status, data->>'stt_error' FROM inbound_events")
    assert tuple(event[0]) == ("processed", "stt_http_401")
    meta = await stand.sql("SELECT metadata->>'voice_status' FROM messages WHERE role = 'user'")
    assert meta[0][0] == "failed"


async def test_expired_file_link_is_a_failure_line_not_a_loop(stand):
    stt = _enable(stand)
    connection = await stand.telegram()  # no file registered: getFile answers 400
    await stand.tg_update(connection, 955, None, **_voice())
    await stand.worker.drain()
    assert stt.requests == [] and len(stand.providers.sent) == 1
    assert "Не получилось разобрать голосовое" in stand.providers.sent[0]["text"]


async def test_spent_budget_means_no_transcription(stand):
    stt = _enable(stand, limit_business_daily_usd=0.005)
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()
    await stand.tg_update(connection, 960, None, **_voice())
    await stand.worker.drain()
    assert "getFile" not in stand.providers.calls and stt.requests == []
    assert stand.providers.sent == []  # over a limit nothing is sent, a manager is asked instead
    assert await _count(stand, "handoff_requests", "reason = 'business_budget'") == 1
    meta = await stand.sql("SELECT text, metadata->>'voice_status' FROM messages WHERE role = 'user'")
    assert tuple(meta[0]) == ("[voice]", "limit")


async def test_manager_dialog_gets_the_transcript_but_no_auto_reply(stand):
    stt = _enable(stand)
    _said(stt, "Мой номер 0555 123 456, перезвоните")
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()
    await stand.tg_update(connection, 970, "Привет")
    await stand.worker.drain()
    dialog = (await stand.client.get("/api/v1/conversations")).json()["items"][0]["id"]
    assert (await stand.client.post(f"/api/v1/conversations/{dialog}/takeover")).status_code == 200

    await stand.tg_update(connection, 971, None, **_voice())
    await stand.worker.drain()
    assert len(stand.providers.sent) == 1  # only the reply to "Привет"
    text = await stand.sql("SELECT text FROM messages WHERE role = 'user' ORDER BY seq DESC LIMIT 1")
    assert text[0][0] == "Мой номер 0555 123 456, перезвоните"
    # A number heard in a voice message is not kept as the customer's contact.
    phones = await stand.sql("SELECT c.phone, c.contact_phone FROM customers c JOIN conversations d ON d.customer_id = c.id")
    assert tuple(phones[0]) == (None, None)


async def test_voice_of_one_business_stays_with_it(stand):
    stt = _enable(stand)
    _said(stt, QUESTION)
    stand.providers.files["voice-file-1"] = AUDIO
    other = stand.tokens["other_business"]
    connection = await stand.telegram(business_id=other)
    await stand.tg_update(connection, 980, None, **_voice())
    await stand.worker.drain()
    dialogs = await stand.sql("SELECT business_id FROM conversations")
    assert [row[0] for row in dialogs] == [other]
    reservations = await stand.sql("SELECT business_id FROM spend_reservations")
    assert [row[0] for row in reservations] == [other]
    assert await _count(stand, "spend_budgets", f"scope = 'business:{stand.business.id}'") == 0
    # The demo business's operator does not see it.
    assert (await stand.client.get("/api/v1/conversations")).json()["items"] == []


async def test_logs_carry_no_token_transcript_or_file_id(stand, caplog):
    stt = _enable(stand)
    _said(stt, QUESTION)
    stand.providers.files["voice-file-secret-id"] = AUDIO
    connection = await stand.telegram()
    caplog.set_level(logging.DEBUG)
    # As in production (logging/setup.py): httpx would print every URL, with the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    await stand.tg_update(connection, 990, None, **_voice("voice-file-secret-id"))
    stt.failures.append(500)
    await stand.worker.drain()
    await stand.sql("UPDATE jobs SET run_at = now() WHERE status = 'queued'")
    await stand.worker.drain()
    assert len(stand.providers.sent) == 1
    formatted = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    for secret in (TG_TOKEN, TG_TOKEN.split(":")[1], "voice-file-secret-id", QUESTION, "квартира", "el-test-key"):
        assert secret not in caplog.text and secret not in formatted
    assert any(record.getMessage() == "voice_transcribed" for record in caplog.records)


async def test_raw_event_cleanup_erases_the_transcript(stand):
    stt = _enable(stand)
    _said(stt, QUESTION)
    stand.providers.files["voice-file-1"] = AUDIO
    connection = await stand.telegram()
    await stand.tg_update(connection, 995, None, **_voice())
    await stand.worker.drain()
    await stand.sql("UPDATE inbound_events SET received_at = now() - interval '31 days'")
    assert await stand.worker.redact_old_events() == 1
    rows = await stand.sql("SELECT text, data FROM inbound_events")
    assert tuple(rows[0]) == (None, {})
    assert QUESTION not in json.dumps(rows[0][1], ensure_ascii=False)
    history = await stand.sql("SELECT text FROM messages WHERE role = 'user'")
    assert [row[0] for row in history] == [QUESTION]  # the dialog history stays, as for text

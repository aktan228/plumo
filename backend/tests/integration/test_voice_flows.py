"""Phone calls through the ElevenLabs Custom LLM contract, end to end over HTTP.

ElevenLabs itself is not called: these requests are shaped like the ones its
platform sends (chat/completions with prompt markers, initiation, signed
post-call). The live platform check is `python -m app.voice_probe`.
"""

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update

from app.domain.models import Business
from app.infrastructure.database.models import ConversationRow, HandoffRequestRow, InteractionLogRow, VoiceCallRow
from app.infrastructure.database.repositories import BusinessRepository
from app.infrastructure.database.session import create_session_factory

_AUTH = {"Authorization": "Bearer tok"}


def _spoken(response) -> str:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    lines = [line for line in response.text.splitlines() if line]
    assert lines[-1] == "data: [DONE]"
    return "".join(
        json.loads(line[6:])["choices"][0]["delta"].get("content", "")
        for line in lines
        if line.startswith("data: {")
    )


async def _turn(client, phone: str, call_id: str, text: str, called: str = "") -> str:
    marker = f"plumo_caller={phone} plumo_call={call_id}" + (f" plumo_called={called}" if called else "")
    response = await client.post(
        "/api/v1/telephony/elevenlabs/v1/chat/completions",
        json={
            "stream": True,
            "model": "plumo",
            "messages": [
                {"role": "system", "content": marker},
                {"role": "assistant", "content": "Здравствуйте!"},
                {"role": "user", "content": text},
            ],
        },
        headers=_AUTH,
    )
    return _spoken(response)


async def _post_call(client, call_id: str, duration: int, transcript: list | None = None) -> None:
    body = json.dumps(
        {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": call_id,
                "status": "done",
                "transcript": transcript or [],
                "metadata": {"call_duration_secs": duration, "start_time_unix_secs": int(time.time()) - duration},
            },
        }
    ).encode()
    stamp = int(time.time())
    signature = hmac.new(b"whsec", f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    response = await client.post(
        "/api/v1/telephony/elevenlabs/post-call",
        content=body,
        headers={"ElevenLabs-Signature": f"t={stamp},v0={signature}", "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text


def _env(monkeypatch) -> None:
    monkeypatch.setenv("ELEVENLABS_LLM_TOKEN", "tok")
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_SECRET", "whsec")


async def test_call_handoff_takeover_then_next_call_starts_fresh(client, engine, monkeypatch):
    _env(monkeypatch)
    phone = "+996555888001"

    greeting = await client.post(
        "/api/v1/telephony/elevenlabs/initiation",
        json={"caller_id": phone, "called_number": "+996312000000", "call_sid": "call_a"},
        headers=_AUTH,
    )
    assert "записывается" in greeting.json()["conversation_config_override"]["agent"]["first_message"]

    answer = await _turn(client, phone, "call_a", "Еще продается квартира за 85000?")
    assert "85 000" in answer and "USD" not in answer

    asked = await _turn(client, phone, "call_a", "Соедините меня с менеджером")
    assert "менеджер" in asked.lower()
    pending = (await client.get("/api/v1/handoffs", params={"status": "PENDING"})).json()
    assert len(pending) == 1
    assert (await client.post(f"/api/v1/handoffs/{pending[0]['id']}/accept")).status_code == 200

    # The manager owns the dialog but is not on the line: the caller must hear something.
    held = await _turn(client, phone, "call_a", "Алло, вы тут?")
    assert "перезвонит" in held

    await _post_call(
        client,
        "call_a",
        75,
        transcript=[
            {"role": "user", "message": "Еще продается?", "time_in_call_secs": 2, "conversation_turn_metrics": None},
            {
                "role": "agent",
                "message": "Да.",
                "time_in_call_secs": 4,
                "conversation_turn_metrics": {
                    "convai_llm_service_ttfb": {"elapsed_time": 1.2},
                    "convai_llm_service_ttf_sentence": {"elapsed_time": 1.4},
                },
            },
            {
                "role": "agent",
                "message": "Соединяю.",
                "time_in_call_secs": 9,
                "conversation_turn_metrics": {"convai_llm_service_ttfb": {"elapsed_time": 2.0}},
            },
        ],
    )

    # A new call is a new dialog: the old pause does not mute it, memory stays.
    fresh = await _turn(client, phone, "call_b", "Какая площадь у квартиры за 85000?")
    assert fresh and "перезвонит" not in fresh

    factory = create_session_factory(engine)
    async with factory() as session:
        calls = {row.provider_call_id: row for row in (await session.scalars(select(VoiceCallRow))).all()}
        conversations = (await session.scalars(select(ConversationRow).where(ConversationRow.channel == "voice"))).all()
    first = calls["call_a"]
    assert first.business_id is not None
    assert first.status == "completed" and first.duration_s == 75
    assert first.metadata_json["latency"]["llm_service_ttfb_p50"] == 2.0
    assert first.metadata_json["latency"]["llm_service_ttfb_max"] == 2.0
    assert first.metadata_json["transcript"][1]["metrics"] == {"llm_service_ttfb": 1.2, "llm_service_ttf_sentence": 1.4}
    assert calls["call_b"].business_id == first.business_id
    assert len(conversations) == 2
    assert sum(1 for row in conversations if row.ended_at is None) == 1


async def test_empty_utterance_and_bad_token(client, monkeypatch):
    _env(monkeypatch)
    assert await _turn(client, "+996555888002", "call_c", " ") == "Да, слушаю вас."
    denied = await client.post(
        "/api/v1/telephony/elevenlabs/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "привет"}]},
        headers={"Authorization": "Bearer wrong"},
    )
    assert denied.status_code == 401


async def test_bad_post_call_signature_is_rejected(client, monkeypatch):
    _env(monkeypatch)
    response = await client.post(
        "/api/v1/telephony/elevenlabs/post-call",
        content=b'{"type":"post_call_transcription","data":{"conversation_id":"x"}}',
        headers={"ElevenLabs-Signature": f"t={int(time.time())},v0=deadbeef"},
    )
    assert response.status_code == 401


async def test_dialled_number_isolates_businesses(client, engine, monkeypatch):
    _env(monkeypatch)
    now = datetime.now(UTC)
    factory = create_session_factory(engine)
    async with factory() as session:
        await BusinessRepository(session).add(
            Business(uuid4(), "Second Realty", "Агентство", "10:00-19:00", {"voice_numbers": ["+996312999999"]}, "", now, now)
        )
        await session.commit()

    unknown = await _turn(client, "+996555888003", "call_d", "Здравствуйте", called="+996312000000")
    assert "Менеджер вам перезвонит" in unknown  # no guessing which business owns the call

    greeting = await client.post(
        "/api/v1/telephony/elevenlabs/initiation",
        json={"caller_id": "+996555888003", "called_number": "+996312999999", "call_sid": "call_e"},
        headers=_AUTH,
    )
    assert "Second Realty" in greeting.json()["conversation_config_override"]["agent"]["first_message"]


async def test_metrics_and_logs_are_per_business(client, engine):
    reply = await client.post(
        "/api/v1/messages",
        json={"channel": "whatsapp", "external_user_id": "+996555888004", "text": "Еще продается квартира за 85000?"},
    )
    assert reply.status_code == 200
    now = datetime.now(UTC)
    factory = create_session_factory(engine)
    async with factory() as session:
        other = await BusinessRepository(session).add(Business(uuid4(), "Empty Realty", "", "", {}, "", now, now))
        await session.commit()
        log = (await session.scalars(select(InteractionLogRow))).one()
    assert log.business_id is not None
    assert set(log.timings) == {"prepare_ms", "model_ms", "post_ms"}

    everyone = (await client.get("/api/v1/metrics")).json()
    mine = (await client.get("/api/v1/metrics", params={"business_id": str(log.business_id)})).json()
    empty = (await client.get("/api/v1/metrics", params={"business_id": str(other.id)})).json()
    assert everyone["total_messages"] == mine["total_messages"] == 2
    assert empty["total_messages"] == 0 and empty["total_conversations"] == 0


async def test_forgotten_takeover_expires(client, engine):
    async def send(text: str) -> dict:
        response = await client.post(
            "/api/v1/messages", json={"channel": "whatsapp", "external_user_id": "+996555888005", "text": text}
        )
        assert response.status_code == 200, response.text
        return response.json()

    asked = await send("Позовите менеджера")
    assert (await client.post(f"/api/v1/handoffs/{asked['handoff_id']}/accept")).status_code == 200
    assert (await send("Алло?"))["send_reply"] is False

    factory = create_session_factory(engine)
    async with factory() as session:
        await session.execute(
            update(HandoffRequestRow).values(updated_at=datetime.now(UTC) - timedelta(hours=25))
        )
        await session.commit()
    back = await send("Еще продается квартира за 85000?")
    assert back["send_reply"] is True and back["response_text"]


async def test_model_outage_hands_off_instead_of_503(agent):
    from app.domain.errors import ProviderUnavailable
    from app.domain.models import ExtractedCustomerData, InboundMessage, SummaryDraft

    class Gone:
        name = "gone"

        async def generate_response(self, context, route):
            raise ProviderUnavailable("Gemini model gemini-3.8-flash is no longer available")

        async def extract_customer_data(self, text):
            return ExtractedCustomerData()

        async def summarize(self, messages, previous):
            return SummaryDraft("-", None, [], None)

    agent.llm_for_tier = lambda tier: Gone()
    response = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="+996555888006", text="Здравствуйте, подскажите что-нибудь")
    )
    assert response.response_text
    assert response.handoff_required is True
    assert response.handoff_reason == "model_unavailable"


async def test_uncertain_speech_goes_to_the_big_model(agent):
    from app.domain.models import InboundMessage

    response = await agent.process_message(
        InboundMessage(
            channel="voice",
            external_user_id="+996555888007",
            text="здравствуйте",
            metadata={"stt_confidence": 0.3},
        )
    )
    assert (response.route, response.route_reason) == ("big", "uncertain_stt")


async def test_without_small_model_turns_route_to_big(agent):
    from app.domain.models import InboundMessage

    agent.small_enabled = False
    response = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id="+996555888008", text="Здравствуйте")
    )
    assert response.route == "big"
    assert response.route_reason == "greeting:no_small"
    assert response.model_used == "mock_big"


async def test_spoken_price_finds_the_listing(client, monkeypatch):
    _env(monkeypatch)
    answer = await _turn(client, "+996555888009", "call_f", "Квартира за восемьдесят пять тысяч ещё продаётся?")
    assert "85 000" in answer

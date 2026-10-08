"""ElevenLabs wire format, call service and the fixes around it. No database."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.application.services.call_service import CallService
from app.domain.models import CallTurn, Customer, Message
from app.domain.scheduling import BUSINESS_TZ, parse_slot
from app.domain.text_signals import analyze_message, phone_from_id
from app.infrastructure.ai.openrouter_llm import parse_generation_json
from app.infrastructure.telephony.elevenlabs import (
    for_speech,
    initiation_response,
    parse_llm_request,
    parse_post_call,
    sse_stream,
    verify_signature,
)


def test_llm_request_takes_last_user_turn_and_caller_from_prompt_markers() -> None:
    body = {
        "model": "plumo",
        "stream": True,
        "messages": [
            {"role": "system", "content": "plumo_caller=+996555111222 plumo_call=conv_42"},
            {"role": "assistant", "content": "Здравствуйте!"},
            {"role": "user", "content": "Еще продается квартира за 85000?"},
        ],
    }
    turn = parse_llm_request(body)
    assert turn.text == "Еще продается квартира за 85000?"
    assert turn.caller == "+996555111222"
    assert turn.call_id == "conv_42"


def test_unrendered_template_is_not_a_caller() -> None:
    body = {"messages": [{"role": "system", "content": "plumo_caller={{system__caller_id}}"}]}
    assert parse_llm_request(body).caller is None


def test_sse_stream_is_openai_chunk_format() -> None:
    lines = list(sse_stream("Да, доступен."))
    assert lines[-1] == "data: [DONE]\n\n"
    chunks = [json.loads(line[6:]) for line in lines[:-1]]
    assert all(item["object"] == "chat.completion.chunk" for item in chunks)
    assert "".join(item["choices"][0]["delta"].get("content", "") for item in chunks) == "Да, доступен."
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


def test_for_speech_drops_markdown_and_spells_units() -> None:
    text = "Смотрите, что есть:\n• **Квартира на Чуй** — 58 м², 85 000 USD\n- Студия: 28 м2, 39000 USD"
    assert for_speech(text) == (
        "Смотрите, что есть: Квартира на Чуй, 58 квадратных метров, 85 000 долларов. "
        "Студия: 28 квадратных метров, 39000 долларов"
    )


def test_signature_roundtrip_and_replay_window() -> None:
    body = b'{"type":"post_call_transcription"}'
    stamp = 1_800_000_000
    digest = hmac.new(b"s3cret", f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    header = f"t={stamp},v0={digest}"
    assert verify_signature(header, body, "s3cret", now=stamp + 5)
    assert not verify_signature(header, body, "other", now=stamp + 5)
    assert not verify_signature(header, body + b" ", "s3cret", now=stamp + 5)
    assert not verify_signature(header, body, "s3cret", now=stamp + 3600)


def test_post_call_report() -> None:
    report = parse_post_call(
        {
            "type": "post_call_transcription",
            "data": {
                "conversation_id": "conv_42",
                "status": "done",
                "transcript": [{"role": "user", "message": "Алло", "time_in_call_secs": 1}],
                "metadata": {
                    "start_time_unix_secs": 1_800_000_000,
                    "call_duration_secs": 95,
                    "cost": 300,
                    "phone_call": {"external_number": "+996555111222", "agent_number": "+996312000000"},
                },
            },
        }
    )
    assert report is not None
    assert report.call_id == "conv_42"
    assert report.duration_s == 95
    assert report.caller == "+996555111222"
    assert parse_post_call({"type": "post_call_audio"}) is None


def test_initiation_response_shape() -> None:
    body = initiation_response("Здравствуйте!", "ky", {"plumo_language": "ky"})
    assert body["type"] == "conversation_initiation_client_data"
    assert body["conversation_config_override"]["agent"] == {"first_message": "Здравствуйте!", "language": "ky"}


# --- CallService on fakes -------------------------------------------------


def _customer(phone: str, language: str = "ru") -> Customer:
    now = datetime.now(UTC)
    return Customer(uuid4(), phone, language, "active", None, "whatsapp", None, now, now)


class _Customers:
    def __init__(self, *rows: Customer) -> None:
        self.rows = {row.phone: row for row in rows}

    async def get_by_phone(self, phone: str):
        return self.rows.get(phone)


class _Messages:
    def __init__(self, history: list[Message]) -> None:
        self.history = history

    async def list_for_customer(self, customer_id, limit: int = 100):
        return [item for item in self.history if item.customer_id == customer_id][-limit:]


class _Calls:
    def __init__(self) -> None:
        self.rows = {}

    async def get_by_provider_id(self, provider, provider_call_id):
        return self.rows.get((provider, provider_call_id))

    async def save(self, call):
        self.rows[(call.provider, call.provider_call_id)] = call
        return call


class _Agent:
    def __init__(self) -> None:
        self.seen = []

    async def resolve_business(self, explicit=None):
        return SimpleNamespace(name="Demo Realty", contacts={"assistant_name": "Айпери"})

    async def process_message(self, message):
        self.seen.append(message)
        return SimpleNamespace(
            response_text="Да, объект за 85 000 USD ещё доступен.",
            customer_id=uuid4(),
            language="ru",
            handoff_required=False,
        )


def _message(customer: Customer, role: str, text: str) -> Message:
    now = datetime.now(UTC)
    return Message(uuid4(), uuid4(), customer.id, role, text, now, {}, now)


def _service(customer: Customer | None = None, history: list[Message] | None = None) -> tuple[CallService, _Agent, _Calls]:
    agent, calls = _Agent(), _Calls()
    service = CallService(
        agent=agent,
        customers=_Customers(*([customer] if customer else [])),
        messages=_Messages(history or []),
        calls=calls,
        provider="elevenlabs",
        usd_per_minute=0.12,
    )
    return service, agent, calls


async def test_greeting_discloses_ai_and_recording_and_recalls_last_question() -> None:
    known = _customer("+996555111222")
    history = [
        _message(known, "user", "Еще продается квартира за 85000?"),
        _message(known, "assistant", "Да, доступна."),
    ]
    service, _agent, calls = _service(known, history)
    greeting = await service.start(CallTurn(text="", caller="+996555111222", call_id="conv_1"))
    assert "ИИ-ассистент" in greeting.text
    assert "Айпери" in greeting.text
    assert "записывается" in greeting.text
    assert "85000" in greeting.text
    assert greeting.customer_id == known.id
    assert ("elevenlabs", "conv_1") in calls.rows


async def test_greeting_for_new_caller_has_no_recall() -> None:
    service, _agent, _calls = _service()
    greeting = await service.start(CallTurn(text="", caller="+996700000000", call_id="conv_2"))
    assert "записывается" in greeting.text
    assert "В прошлый раз" not in greeting.text


async def test_answer_runs_agent_as_voice_channel() -> None:
    service, agent, _calls = _service()
    reply = await service.answer(CallTurn(text="Еще продается?", caller="+996555111222", call_id="c3"))
    assert reply.text.startswith("Да")
    assert agent.seen[0].channel == "voice"
    assert agent.seen[0].external_user_id == "+996555111222"


async def test_hidden_number_does_not_become_a_phone() -> None:
    service, agent, _calls = _service()
    await service.answer(CallTurn(text="Алло", caller=None, call_id="CA1234567890123"))
    assert agent.seen[0].external_user_id == "call:CA1234567890123"
    assert phone_from_id("call:CA1234567890123") is None


async def test_finish_prices_minutes() -> None:
    service, _agent, _calls = _service()
    report = parse_post_call(
        {
            "type": "post_call_transcription",
            "data": {"conversation_id": "c4", "metadata": {"call_duration_secs": 120}},
        }
    )
    call = await service.finish(report)
    assert call.status == "completed"
    assert call.cost == 0.24


# --- regressions fixed in this pass ----------------------------------------


def test_pokazhite_is_not_a_farewell() -> None:
    signals = analyze_message("Покажите квартиру на Чуй")
    assert not signals.farewell
    assert signals.meeting
    assert analyze_message("Ну пока").farewell


def test_meeting_time_is_bishkek_local() -> None:
    now = datetime(2026, 10, 8, 20, 0, tzinfo=UTC)  # 02:00 on Oct 9 in Bishkek
    slot = parse_slot("завтра в 15:00", {}, now)
    assert slot.tzinfo == BUSINESS_TZ
    assert (slot.day, slot.hour) == (10, 15)
    assert slot.astimezone(UTC).hour == 9


def test_bad_model_datetime_does_not_crash() -> None:
    slot = parse_slot("встреча в 11:30", {"datetime": "tomorrow 3pm", "date": "2026-13-45"}, datetime.now(UTC))
    assert (slot.hour, slot.minute) == (11, 30)


def test_json_reply_without_text_is_not_sent_raw() -> None:
    parsed = parse_generation_json('{"text": "", "handoff_required": true, "confidence": 0.2}')
    assert parsed["text"] == ""

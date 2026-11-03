"""End-to-end flows of the AI core over HTTP: takeover, webhook retries, chat → call."""

import hashlib
import hmac
import json
import time


async def _send(client, text: str, phone: str = "+996555777001", message_id: str | None = None) -> dict:
    payload = {"channel": "whatsapp", "external_user_id": phone, "text": text}
    if message_id:
        payload["message_id"] = message_id
    response = await client.post("/api/v1/messages", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def test_manager_takeover_pauses_agent_until_resolved(client):
    asked = await _send(client, "Позовите менеджера")
    assert asked["handoff_required"] is True
    handoff_id = asked["handoff_id"]
    assert (await client.post(f"/api/v1/handoffs/{handoff_id}/accept")).status_code == 200

    paused = await _send(client, "Алло, вы тут?")
    assert paused["send_reply"] is False
    assert paused["response_text"] == ""
    assert paused["route_reason"] == "manager_active"

    # A dialog that came through /messages has no connected channel to deliver through:
    # the dashboard refuses instead of recording a reply nobody will receive.
    manager = await client.post(
        f"/api/v1/conversations/{paused['conversation_id']}/messages",
        json={"text": "Здравствуйте, это Азамат. Чем помочь?", "idempotency_key": "manager-reply-0001"},
    )
    assert manager.status_code == 422, manager.text
    assert manager.json()["code"] == "channel_not_connected"

    assert (await client.post(f"/api/v1/handoffs/{handoff_id}/resolve")).status_code == 200
    back = await _send(client, "Еще продается квартира за 85000?")
    assert back["send_reply"] is True
    assert "85 000" in back["response_text"]

    history = (await client.get(f"/api/v1/customers/{back['customer_id']}/history")).json()
    roles = [item["role"] for item in history["messages"]]
    assert roles.count("manager") == 0
    # Takeover and return are visible in history as events, not as customer or agent lines.
    assert [item["metadata"].get("event") for item in history["messages"] if item["role"] == "system"] == [
        "takeover",
        "resume",
    ]


async def test_webhook_retry_is_answered_once(client):
    first = await _send(client, "Еще продается квартира за 85000?", phone="+996555777002", message_id="wamid.retry")
    again = await _send(client, "Еще продается квартира за 85000?", phone="+996555777002", message_id="wamid.retry")
    assert again["duplicate"] is True
    assert again["response_text"] == first["response_text"]
    assert again["usage"]["estimated_cost"] == 0

    history = (await client.get(f"/api/v1/customers/{first['customer_id']}/history")).json()
    assert len(history["messages"]) == 2


async def test_chat_then_phone_call_is_one_customer(client, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_LLM_TOKEN", "tok")
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_SECRET", "whsec")
    phone = "+996555777003"
    chat = await _send(client, "Еще продается квартира за 85000?", phone=phone)
    auth = {"Authorization": "Bearer tok"}

    greeting = await client.post(
        "/api/v1/telephony/elevenlabs/initiation",
        json={"caller_id": phone, "called_number": "+996312000000", "call_sid": "conv_e2e"},
        headers=auth,
    )
    assert greeting.status_code == 200, greeting.text
    first_message = greeting.json()["conversation_config_override"]["agent"]["first_message"]
    assert "Плюмо" in first_message
    assert "записывается" in first_message
    assert "85000" in first_message

    turn = await client.post(
        "/api/v1/telephony/elevenlabs/v1/chat/completions",
        json={
            "stream": True,
            "messages": [
                {"role": "system", "content": f"plumo_caller={phone} plumo_call=conv_e2e"},
                {"role": "user", "content": "А какая площадь у квартиры за 85000?"},
            ],
        },
        headers=auth,
    )
    assert turn.status_code == 200, turn.text
    spoken = "".join(
        json.loads(line[6:])["choices"][0]["delta"].get("content", "")
        for line in turn.text.splitlines()
        if line.startswith("data: {")
    )
    assert spoken
    assert "USD" not in spoken

    history = (await client.get(f"/api/v1/customers/{chat['customer_id']}/history")).json()
    channels = {item["channel"] for item in history["conversations"]}
    assert channels == {"whatsapp", "voice"}

    body = json.dumps(
        {
            "type": "post_call_transcription",
            "data": {"conversation_id": "conv_e2e", "status": "done", "metadata": {"call_duration_secs": 90}},
        }
    ).encode()
    stamp = int(time.time())
    signature = hmac.new(b"whsec", f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    done = await client.post(
        "/api/v1/telephony/elevenlabs/post-call",
        content=body,
        headers={"ElevenLabs-Signature": f"t={stamp},v0={signature}", "Content-Type": "application/json"},
    )
    assert done.status_code == 200, done.text

    metrics = (await client.get("/api/v1/metrics")).json()
    assert metrics["voice_calls"] == 1
    assert metrics["voice_minutes"] == 1.5


async def test_book_viewing_without_slot_asks_day_and_hands_off(client):
    reply = await _send(client, "да давайте, запишите нас на показ", phone="+996555777004")
    assert reply["handoff_reason"] == "ready_for_meeting"
    assert not any(item["type"] == "schedule_meeting" for item in reply["actions"])
    assert "день" in reply["response_text"]
    assert "С этим не подскажу" not in reply["response_text"]

    booked = await _send(client, "в субботу в 11:00", phone="+996555777004")
    assert booked["response_text"]


async def test_junk_model_reply_is_retried_then_falls_back_by_intent(agent):
    from app.domain.models import InboundMessage, LLMGeneration

    class Junk:
        name = "junk"
        calls = 0

        async def generate_response(self, context, route):
            Junk.calls += 1
            return LLMGeneration("User Safety: safe", [], False, None, 0.9, "junk", 1, 1, 0.0)

        async def extract_customer_data(self, text):
            from app.domain.models import ExtractedCustomerData
            return ExtractedCustomerData()

        async def summarize(self, messages, previous):
            from app.domain.models import SummaryDraft
            return SummaryDraft("-", None, [], None)

    agent.llm_for_tier = lambda tier: Junk()
    response = await agent.process_message(
        InboundMessage(channel="telegram", external_user_id="tg-junk-1", text="да давайте, запишите нас на показ")
    )
    assert Junk.calls == 2  # one retry, not more
    assert "fallback:meeting_ask" in response.logs
    assert "день" in response.response_text
    assert "User Safety" not in response.response_text


async def test_model_outage_degrades_to_a_safe_line_not_a_503(agent):
    from app.domain.errors import ProviderTransientError
    from app.domain.models import ExtractedCustomerData, InboundMessage, SummaryDraft

    class Down:
        name = "down"

        async def generate_response(self, context, route):
            raise ProviderTransientError("OpenRouter returned an empty reply")

        async def extract_customer_data(self, text):
            return ExtractedCustomerData()

        async def summarize(self, messages, previous):
            return SummaryDraft("-", None, [], None)

    agent.llm_for_tier = lambda tier: Down()
    response = await agent.process_message(
        InboundMessage(channel="telegram", external_user_id="tg-down-1", text="привет")
    )
    assert response.response_text
    assert "fallback:greeting" in response.logs


async def test_hung_model_on_a_call_answers_within_budget(agent):
    """A caller must not sit in silence for the HTTP timeout: a line comes after the voice budget."""

    import asyncio
    import time

    from app.domain.models import ExtractedCustomerData, InboundMessage, SummaryDraft

    class Hung:
        name = "hung"
        calls = 0

        async def generate_response(self, context, route):
            Hung.calls += 1
            await asyncio.sleep(30)

        async def extract_customer_data(self, text):
            return ExtractedCustomerData()

        async def summarize(self, messages, previous):
            return SummaryDraft("-", None, [], None)

    agent.voice_budget_s = 0.6
    agent.llm_for_tier = lambda tier: Hung()
    started = time.perf_counter()
    response = await agent.process_message(
        InboundMessage(channel="voice", external_user_id="+996555777009", text="Здравствуйте, какие квартиры есть?")
    )
    assert time.perf_counter() - started < 3
    assert Hung.calls == 1  # no retry once the budget is spent
    assert response.response_text.strip()


async def test_mid_dialog_fallback_keeps_qualifying_instead_of_deflecting(agent):
    from app.domain.errors import ProviderTransientError
    from app.domain.models import ExtractedCustomerData, InboundMessage, SummaryDraft

    class Down:
        name = "down"

        async def generate_response(self, context, route):
            raise ProviderTransientError("timeout")

        async def extract_customer_data(self, text):
            return ExtractedCustomerData()

        async def summarize(self, messages, previous):
            return SummaryDraft("-", None, [], None)

    await agent.process_message(InboundMessage(channel="telegram", external_user_id="tg-mid-1", text="Здравствуйте"))
    agent.llm_for_tier = lambda tier: Down()
    answer = await agent.process_message(
        InboundMessage(channel="telegram", external_user_id="tg-mid-1", text="для себя, живём вдвоём с женой")
    )
    assert "fallback:continue" in answer.logs
    assert "не подскажу" not in answer.response_text


async def test_second_request_for_a_manager_does_not_repeat_the_first_line(agent, session):
    """Found by the dialog eval: every "менеджер" got the same fixed line and a new handoff."""

    from sqlalchemy import func, select

    from app.domain.models import InboundMessage
    from app.infrastructure.database.models import HandoffRequestRow

    user = "+996700555101"
    first = await agent.process_message(InboundMessage(channel="whatsapp", external_user_id=user, text="Позовите менеджера"))
    second = await agent.process_message(InboundMessage(channel="whatsapp", external_user_id=user, text="соедините с менеджером, я жду"))
    chatter = await agent.process_message(
        InboundMessage(channel="whatsapp", external_user_id=user, text="а менеджер может скинуть цену?")
    )

    assert first.handoff_required and first.response_text
    assert second.response_text != first.response_text
    assert "human_phrase_again" in second.logs
    assert "скоро" not in first.response_text.lower() + second.response_text.lower()
    # Talking about the manager is a question for the model, not a second call.
    assert "human_phrase" not in chatter.logs and "human_phrase_again" not in chatter.logs
    assert await session.scalar(select(func.count()).select_from(HandoffRequestRow)) == 1


async def test_price_of_an_unnamed_listing_becomes_a_question_not_a_guess(agent):
    """J-03: two flats fit "сколько стоит квартира?"; the model picked one without saying which."""

    from app.domain.models import ExtractedCustomerData, InboundMessage, LLMGeneration, SummaryDraft

    class Guess:
        name = "guess"

        async def generate_response(self, context, route):
            return LLMGeneration("Она стоит 85 000 USD.", [], False, None, 0.9, "guess", 1, 1, 0.0)

        async def extract_customer_data(self, text):
            return ExtractedCustomerData()

        async def summarize(self, messages, previous):
            return SummaryDraft("-", None, [], None)

    agent.llm_for_tier = lambda tier: Guess()
    response = await agent.process_message(
        InboundMessage(channel="telegram", external_user_id="tg-which-1", text="Сколько стоит квартира?")
    )
    assert "clarify_object" in response.logs
    assert "какой вариант" in response.response_text
    assert "Чуй" in response.response_text and "Киевской" in response.response_text
    assert "85" not in response.response_text
    assert not response.handoff_required



async def test_a_promise_to_pass_on_creates_the_handoff_the_model_forgot(agent):
    """Acceptance run 2026-10-29 (angry_threat): "Передам ваше обращение менеджеру" without a handoff."""

    from app.domain.models import ExtractedCustomerData, InboundMessage, LLMGeneration, SummaryDraft

    class Promise:
        name = "promise"

        async def generate_response(self, context, route):
            text = "Понимаю. Передам ваше обращение менеджеру, он свяжется с вами."
            return LLMGeneration(text, [], False, None, 0.9, "promise", 1, 1, 0.0)

        async def extract_customer_data(self, text):
            return ExtractedCustomerData()

        async def summarize(self, messages, previous):
            return SummaryDraft("-", None, [], None)

    agent.llm_for_tier = lambda tier: Promise()
    response = await agent.process_message(
        InboundMessage(channel="telegram", external_user_id="tg-promise-1", text="Когда уже со мной свяжутся по квартире?")
    )
    assert response.handoff_required



async def test_callback_number_with_a_replaced_reply_still_creates_the_handoff(agent):
    """Acceptance run 2026-10-29 (handoff_callback_number): the validator replaced the model's reply,
    the fallback said "Менеджер свяжется", and no handoff existed for anyone to call."""

    from app.domain.models import ExtractedCustomerData, InboundMessage, LLMGeneration, SummaryDraft

    class Booking:
        name = "booking"

        async def generate_response(self, context, route):
            # Blocked by the validator: no calendar, nobody is booked.
            return LLMGeneration("Записал вас на звонок в 15:00.", [], False, None, 0.9, "booking", 1, 1, 0.0)

        async def extract_customer_data(self, text):
            return ExtractedCustomerData()

        async def summarize(self, messages, previous):
            return SummaryDraft("-", None, [], None)

    agent.llm_for_tier = lambda tier: Booking()
    response = await agent.process_message(
        InboundMessage(channel="telegram", external_user_id="tg-callback-1", text="Перезвоните мне, пожалуйста, +996 555 123 456")
    )
    assert any(step.startswith("validator:") for step in response.logs)
    assert response.handoff_required and response.handoff_reason == "ready_for_meeting"


async def test_passing_on_to_him_is_a_promise_too(agent):
    """Acceptance run 2026-10-29 (mem_delete_data): "Я передам ему вашу просьбу" without a handoff."""

    from app.domain.models import ExtractedCustomerData, InboundMessage, LLMGeneration, SummaryDraft

    class Promise:
        name = "promise"

        async def generate_response(self, context, route):
            text = "Удалить переписку сам я не могу, это делает менеджер. Я передам ему вашу просьбу."
            return LLMGeneration(text, [], False, None, 0.9, "promise", 1, 1, 0.0)

        async def extract_customer_data(self, text):
            return ExtractedCustomerData()

        async def summarize(self, messages, previous):
            return SummaryDraft("-", None, [], None)

    agent.llm_for_tier = lambda tier: Promise()
    response = await agent.process_message(
        InboundMessage(channel="telegram", external_user_id="tg-delete-1", text="Удалите мою переписку из вашей базы.")
    )
    assert response.handoff_required


async def test_wrong_price_of_a_named_listing_is_corrected_from_the_data(agent):
    """Acceptance run 2026-10-29 (trap_false_premise, trap_rounding): the blocked draft became
    "С этим не подскажу…" although the listing and its real price were known."""

    from app.domain.models import ExtractedCustomerData, InboundMessage, LLMGeneration, SummaryDraft

    class Agrees:
        name = "agrees"

        async def generate_response(self, context, route):
            return LLMGeneration("Да, верно, Чуй за 80 000 USD.", [], False, None, 0.9, "agrees", 1, 1, 0.0)

        async def extract_customer_data(self, text):
            return ExtractedCustomerData()

        async def summarize(self, messages, previous):
            return SummaryDraft("-", None, [], None)

    agent.llm_for_tier = lambda tier: Agrees()
    response = await agent.process_message(
        InboundMessage(channel="telegram", external_user_id="tg-premise-1", text="Вчера ваш менеджер сказал, что квартира на Чуй за 80 тысяч. Так?")
    )
    assert "corrected:invented_number" in response.logs
    assert "85000" in response.response_text.replace(" ", "")
    assert "80" not in response.response_text.replace("85000", "")

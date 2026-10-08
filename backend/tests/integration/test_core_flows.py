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

    manager = await client.post(
        f"/api/v1/conversations/{paused['conversation_id']}/messages",
        json={"text": "Здравствуйте, это Азамат. Чем помочь?", "author": "Азамат"},
    )
    assert manager.status_code == 200, manager.text
    assert manager.json()["role"] == "manager"

    assert (await client.post(f"/api/v1/handoffs/{handoff_id}/resolve")).status_code == 200
    back = await _send(client, "Еще продается квартира за 85000?")
    assert back["send_reply"] is True
    assert "85 000" in back["response_text"]

    history = (await client.get(f"/api/v1/customers/{back['customer_id']}/history")).json()
    assert [item["role"] for item in history["messages"]].count("manager") == 1


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
    assert "Айпери" in first_message
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

"""HTTP contract."""


async def test_message_history_metrics_and_knowledge(client):
    created = await client.post(
        "/api/v1/messages",
        json={
            "channel": "whatsapp",
            "external_user_id": "+996555902020",
            "text": "Еще продается квартира за 85000?",
            "message_id": "wamid.1",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["route"] == "small"
    assert body["model_used"] == "mock_small"
    assert "85 000" in body["response_text"]
    assert created.headers["x-correlation-id"]

    history = await client.get(f"/api/v1/customers/{body['customer_id']}/history")
    assert history.status_code == 200
    assert len(history.json()["messages"]) >= 2

    knowledge = await client.get("/api/v1/knowledge")
    titles = {item["title"] for item in knowledge.json()}
    assert "Квартира на Чуй" in titles

    metrics = await client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["total_messages"] >= 2

    missing = await client.post(
        "/api/v1/messages",
        json={
            "channel": "whatsapp",
            "external_user_id": "+996555902020",
            "text": "А рассрочка есть?",
        },
    )
    assert missing.status_code == 200
    assert missing.json()["handoff_required"] is True
    handoffs = await client.get("/api/v1/handoffs")
    assert handoffs.status_code == 200
    handoff_id = handoffs.json()[0]["id"]
    accepted = await client.post(f"/api/v1/handoffs/{handoff_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACCEPTED"
    resolved = await client.post(f"/api/v1/handoffs/{handoff_id}/resolve")
    assert resolved.json()["status"] == "RESOLVED"

    meeting = await client.post(
        "/api/v1/meetings",
        json={"customer_id": body["customer_id"], "text": "завтра в 15:00", "time": "15:00"},
    )
    assert meeting.status_code == 200
    assert meeting.json()["status"] == "PROPOSED"

    voice = await client.post(
        "/api/v1/voice/transcribe",
        json={"audio_id": "mock_audio_installment"},
    )
    assert voice.status_code == 200
    assert "рассрочка" in voice.json()["text"]

    empty = await client.post(
        "/api/v1/messages",
        json={"channel": "whatsapp", "external_user_id": "+996555902020", "text": "   "},
    )
    assert empty.status_code == 422
    assert empty.json()["error"] == "invalid_message"

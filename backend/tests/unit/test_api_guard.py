"""API key and telephony auth. Requests are rejected before any database access."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_api_key_guards_dashboard_routes_but_not_health(monkeypatch) -> None:
    monkeypatch.setenv("PLUMO_API_KEY", "k")
    with TestClient(create_app(Settings())) as client:
        assert client.get("/health").status_code == 200
        denied = client.get("/api/v1/handoffs")
        assert denied.status_code == 401
        assert denied.json()["error"] == "unauthorized"


def test_telephony_requires_its_own_token(monkeypatch) -> None:
    monkeypatch.setenv("ELEVENLABS_LLM_TOKEN", "tok")
    with TestClient(create_app(Settings())) as client:
        url = "/api/v1/telephony/elevenlabs/v1/chat/completions"
        assert client.post(url, json={"messages": []}).status_code == 401
        ok = client.post(url, json={"messages": []}, headers={"Authorization": "Bearer tok"})
        assert ok.status_code == 200
        assert ok.text.rstrip().endswith("data: [DONE]")


def test_telephony_is_off_until_configured(monkeypatch) -> None:
    monkeypatch.delenv("ELEVENLABS_LLM_TOKEN", raising=False)
    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/v1/telephony/elevenlabs/initiation", json={})
        assert response.status_code == 503

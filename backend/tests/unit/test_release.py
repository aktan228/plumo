"""PJ-03: which code runs and whether the configuration fits a stand, without values."""

from app.config import Settings
from app.release import commit, config_status, worker_commit, worker_id

STAND = {
    "PLUMO_API_KEY": "k", "CHANNEL_SECRET_KEY": "k", "PUBLIC_BASE_URL": "https://api.example", "DASHBOARD_URL": "https://app.example",
    "AUTH_PUBLIC_URL": "https://app.example", "AUTH_EMAIL_FROM": "Plumo <no-reply@example.com>", "RESEND_API_KEY": "k",
    "TELEGRAM_BOT_TOKEN": "k", "OPS_TOKEN": "k", "OPENROUTER_API_KEY": "sk-or-value",
}


def stand(**overrides) -> Settings:
    values = dict(app_env="stand", ai_mode="production", big_model_provider="openrouter", small_model_provider="none",
                  handoff_provider="telegram", public_base_url="https://api.example", channel_worker_enabled=False)
    return Settings(**{**values, **overrides})


def test_a_complete_stand_has_no_problems(monkeypatch):
    for name, value in STAND.items():
        monkeypatch.setenv(name, value)
    status = config_status(stand())
    assert status["problems"] == []
    assert status["present"]["OPENROUTER_API_KEY"] is True
    assert "sk-or-value" not in str(status)


def test_mail_is_optional_only_when_verification_is_explicitly_disabled(monkeypatch):
    for name, value in STAND.items():
        monkeypatch.setenv(name, value)
    for name in ("AUTH_PUBLIC_URL", "AUTH_EMAIL_FROM", "RESEND_API_KEY"):
        monkeypatch.delenv(name)
    assert config_status(stand(auth_email_verification_required=False))["problems"] == []
    assert "missing:RESEND_API_KEY" in config_status(stand())["problems"]


def test_mock_model_missing_key_and_worker_in_api_are_problems(monkeypatch):
    for name, value in STAND.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert "missing:OPENROUTER_API_KEY" in config_status(stand())["problems"]
    assert "ai_mode_mock" in config_status(stand(ai_mode="mock"))["problems"]
    assert "model_provider_mock" in config_status(stand(big_model_provider="mock"))["problems"]
    assert "worker_inside_api" in config_status(stand(channel_worker_enabled=True))["problems"]
    assert "public_base_url_not_https" in config_status(stand(public_base_url="http://api.example"))["problems"]


def test_the_commit_comes_from_the_hosting_and_leads_the_worker_id(monkeypatch):
    for name in ("APP_COMMIT", "RENDER_GIT_COMMIT", "SOURCE_COMMIT", "GIT_COMMIT"):
        monkeypatch.delenv(name, raising=False)
    assert commit() == "unknown"
    monkeypatch.setenv("RENDER_GIT_COMMIT", "0123456789abcdef")
    assert commit() == "0123456789ab"
    monkeypatch.setenv("APP_COMMIT", "fedcba9876543210")
    assert commit() == "fedcba987654"
    assert worker_commit(worker_id()) == "fedcba987654" and len(worker_id()) <= 64
    assert worker_commit("w1") == "unknown"

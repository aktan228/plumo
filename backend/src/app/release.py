"""Which code is running and whether a stand is set up as one: for /ops/status and the release smoke check.

Only names, presence and safe statuses. No secret, password or database address leaves this module.
"""

import os
import socket
from uuid import uuid4

from app.config import Settings

# The hosting puts the deployed commit into one of these; APP_COMMIT wins when set by hand.
COMMIT_VARS = ("APP_COMMIT", "RENDER_GIT_COMMIT", "SOURCE_COMMIT", "GIT_COMMIT")

# A stand without these does not do its job: dashboard, channels, mail, manager notifications, monitoring.
STAND_VARS = (
    "PLUMO_API_KEY",
    "CHANNEL_SECRET_KEY",
    "PUBLIC_BASE_URL",
    "DASHBOARD_URL",
    "AUTH_PUBLIC_URL",
    "AUTH_EMAIL_FROM",
    "RESEND_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "OPS_TOKEN",
)

# The key each model vendor reads (see container._llm_provider). Local has an optional key.
MODEL_KEYS = {
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai_compat": "LLM_API_KEY",
}

# The key each speech-to-text provider reads, checked only when voice messages are on.
STT_KEYS = {"elevenlabs": "ELEVENLABS_API_KEY"}


def commit() -> str:
    for name in COMMIT_VARS:
        value = os.getenv(name, "").strip()
        if value:
            return value[:12]
    return "unknown"


def worker_id() -> str:
    """The commit leads the id, so /ops/status can tell which code each worker runs without a schema change."""

    return f"{commit()}:{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:6]}"[:64]


def worker_commit(worker_id: str) -> str:
    head, sep, _ = worker_id.partition(":")
    return head if sep else "unknown"


def _present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def config_status(settings: Settings) -> dict:
    """Safe view of the configuration. `problems` lists what makes this process unfit for a stand."""

    providers = {settings.big_model_provider.strip().lower()}
    if settings.small_model_enabled:
        providers.add(settings.small_model_provider.strip().lower())
    keys = {}
    for provider in sorted(providers):
        family = provider.rpartition("_")[0] if provider.endswith(("_small", "_big")) else provider
        if family in MODEL_KEYS:
            keys[MODEL_KEYS[family]] = _present(MODEL_KEYS[family])
    present = {name: _present(name) for name in STAND_VARS}
    problems = []
    if settings.is_development:
        problems.append("app_env_development")
    if settings.mock_mode:
        problems.append("ai_mode_mock")
    if not settings.mock_mode and "mock" in providers:
        problems.append("model_provider_mock")
    if settings.handoff_provider.strip().lower() == "mock":
        problems.append("handoff_provider_mock")
    if settings.channel_worker_enabled:
        problems.append("worker_inside_api")
    stt = settings.stt_provider.strip().lower()
    if settings.voice_messages_enabled and (settings.mock_mode or stt in ("", "mock")):
        # Voice messages are on but would only get the "text only" line: the mock never transcribes them.
        problems.append("stt_mock")
    if settings.voice_messages_enabled and stt in STT_KEYS:
        keys[STT_KEYS[stt]] = _present(STT_KEYS[stt])
    optional_mail = {"AUTH_PUBLIC_URL", "AUTH_EMAIL_FROM", "RESEND_API_KEY"} if not settings.auth_email_verification_required else set()
    problems += [f"missing:{name}" for name, ok in {**present, **keys}.items() if not ok and name not in optional_mail]
    if settings.public_base_url and not settings.public_base_url.startswith("https://"):
        problems.append("public_base_url_not_https")
    return {
        "app_env": settings.app_env,
        "email_verification_required": settings.auth_email_verification_required,
        "ai_mode": settings.ai_mode,
        "big_model_provider": settings.big_model_provider,
        "small_model_provider": settings.small_model_provider if settings.small_model_enabled else "none",
        "handoff_provider": settings.handoff_provider,
        "voice_messages_enabled": settings.voice_messages_enabled,
        "stt_provider": settings.stt_provider if settings.voice_messages_enabled else "off",
        "worker_inside_api": settings.channel_worker_enabled,
        "present": {**present, **keys},
        "problems": problems,
    }

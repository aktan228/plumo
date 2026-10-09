"""Create or update the ElevenLabs phone agent that uses Plumo as its Custom LLM.

    python -m app.elevenlabs_setup --public-url https://<host> [--dry-run]

Lives outside the core: the core only answers ElevenLabs callbacks
(api/routes/telephony.py). This script talks to the ElevenLabs API once,
with ELEVENLABS_API_KEY, and writes the ids and secrets it gets back into
backend/.env. Running it again updates the same agent, webhook and secret.

What it sets up:
- workspace secret with ELEVENLABS_LLM_TOKEN, used as the Custom LLM API key
- post-call webhook (HMAC) → /post-call, its secret → ELEVENLABS_WEBHOOK_SECRET
- agent: Custom LLM → /v1, prompt markers, overrides for first message and
  language, initiation webhook → /initiation

The phone number (SIP trunk) is attached in the dashboard, see VOICE.md.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

import httpx

import app.config  # noqa: F401  loads backend/.env
from app.domain.phrases import DEFAULT_ASSISTANT_NAME, call_greeting

API = "https://api.elevenlabs.io"
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
PROMPT_MARKERS = (
    "plumo_caller={{system__caller_id}} plumo_call={{system__conversation_id}} "
    "plumo_called={{system__called_number}}"
)
_PREFIX = "/api/v1/telephony/elevenlabs"


def endpoints(public_url: str) -> dict[str, str]:
    base = public_url.rstrip("/") + _PREFIX
    # ElevenLabs appends /chat/completions to the Custom LLM server URL.
    return {"llm": f"{base}/v1", "initiation": f"{base}/initiation", "post_call": f"{base}/post-call"}


def agent_payload(
    *,
    public_url: str,
    llm_token: str,
    llm_secret_id: str,
    webhook_id: str,
    name: str = "Plumo",
    business_name: str = "Demo Realty",
    voice_id: str | None = None,
    tts_model: str | None = None,
) -> dict[str, Any]:
    """Agent config. The fallback first message is used only if the initiation webhook fails."""

    urls = endpoints(public_url)
    tts: dict[str, Any] = {}
    if voice_id:
        tts["voice_id"] = voice_id
    if tts_model:
        tts["model_id"] = tts_model
    conversation: dict[str, Any] = {
        "agent": {
            "first_message": call_greeting(business_name, "ru", None, DEFAULT_ASSISTANT_NAME),
            "language": "ru",
            "prompt": {
                "prompt": PROMPT_MARKERS,
                "llm": "custom-llm",
                "custom_llm": {
                    "url": urls["llm"],
                    "model_id": "plumo",
                    "api_key": {"secret_id": llm_secret_id},
                },
            },
        },
    }
    if tts:
        conversation["tts"] = tts
    # A normal reply takes 1.5-2.5 s, so the filler must wait longer or it fires on
    # every turn (it did at 1.5 s). It covers only a slow model or a provider retry.
    conversation["turn"] = {"soft_timeout_config": {"timeout_seconds": 3.5, "message": "Секундочку…"}}
    return {
        "name": name,
        "conversation_config": conversation,
        "platform_settings": {
            "overrides": {
                "conversation_config_override": {"agent": {"first_message": True, "language": True}},
            },
            "workspace_overrides": {
                "conversation_initiation_client_data_webhook": {
                    "url": urls["initiation"],
                    "request_headers": {"Authorization": f"Bearer {llm_token}"},
                },
                "webhooks": {"post_call_webhook_id": webhook_id, "events": ["transcript"]},
            },
        },
    }


def set_env_values(path: Path, values: dict[str, str]) -> None:
    """Replace or append KEY=value lines, keeping every other line as is."""

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    for index, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in pending:
            lines[index] = f"{key}={pending.pop(key)}"
    lines.extend(f"{key}={value}" for key, value in pending.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _redacted(payload: dict[str, Any]) -> dict[str, Any]:
    copy = json.loads(json.dumps(payload))
    hook = copy["platform_settings"]["workspace_overrides"]["conversation_initiation_client_data_webhook"]
    hook["request_headers"] = {"Authorization": "Bearer ***"}
    return copy


class _Client:
    def __init__(self, api_key: str) -> None:
        self.http = httpx.Client(base_url=API, headers={"xi-api-key": api_key}, timeout=30)

    def call(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self.http.request(method, path, json=body)
        if response.status_code >= 400:
            raise SystemExit(f"ElevenLabs {method} {path} → {response.status_code}: {response.text[:500]}")
        return response.json() if response.content else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--public-url", default=os.getenv("PLUMO_PUBLIC_URL", ""), help="https-адрес backend (ngrok и т.п.)")
    parser.add_argument("--business-name", default="Demo Realty", help="имя в запасном приветствии")
    parser.add_argument("--dry-run", action="store_true", help="показать конфиг агента, ничего не отправлять")
    args = parser.parse_args(argv)

    public_url = args.public_url.strip()
    if not public_url.startswith("https://"):
        print("Нужен публичный https-адрес backend: --public-url https://... или PLUMO_PUBLIC_URL в .env")
        return 1
    llm_token = os.getenv("ELEVENLABS_LLM_TOKEN", "").strip()
    generated = {}
    if not llm_token:
        llm_token = secrets.token_urlsafe(32)
        generated["ELEVENLABS_LLM_TOKEN"] = llm_token

    secret_id = os.getenv("ELEVENLABS_LLM_SECRET_ID", "").strip()
    webhook_id = os.getenv("ELEVENLABS_POST_CALL_WEBHOOK_ID", "").strip()
    agent_id = os.getenv("ELEVENLABS_AGENT_ID", "").strip()
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip() or None
    tts_model = os.getenv("ELEVENLABS_TTS_MODEL", "").strip() or None

    if args.dry_run:
        payload = agent_payload(
            public_url=public_url,
            llm_token=llm_token,
            llm_secret_id=secret_id or "<будет создан>",
            webhook_id=webhook_id or "<будет создан>",
            business_name=args.business_name,
            voice_id=voice_id,
            tts_model=tts_model,
        )
        print(json.dumps(_redacted(payload), ensure_ascii=False, indent=2))
        return 0

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        print("ELEVENLABS_API_KEY не задан в backend/.env")
        return 1
    client = _Client(api_key)
    saved = dict(generated)

    if not secret_id or generated:
        secret = client.call("POST", "/v1/convai/secrets", {"type": "new", "name": "PLUMO_LLM_TOKEN", "value": llm_token})
        secret_id = secret["secret_id"]
        saved["ELEVENLABS_LLM_SECRET_ID"] = secret_id
        print(f"секрет Custom LLM создан: {secret_id}")

    if not webhook_id:
        hook = client.call(
            "POST",
            "/v1/workspace/webhooks",
            {"settings": {"auth_type": "hmac", "name": "Plumo post-call", "webhook_url": endpoints(public_url)["post_call"]}},
        )
        webhook_id = hook["webhook_id"]
        saved["ELEVENLABS_POST_CALL_WEBHOOK_ID"] = webhook_id
        if hook.get("webhook_secret"):
            saved["ELEVENLABS_WEBHOOK_SECRET"] = hook["webhook_secret"]
        else:
            print("ElevenLabs не вернул секрет webhook: скопируйте его из панели в ELEVENLABS_WEBHOOK_SECRET")
        print(f"post-call webhook создан: {webhook_id}")

    payload = agent_payload(
        public_url=public_url,
        llm_token=llm_token,
        llm_secret_id=secret_id,
        webhook_id=webhook_id,
        business_name=args.business_name,
        voice_id=voice_id,
        tts_model=tts_model,
    )
    if agent_id:
        client.call("PATCH", f"/v1/convai/agents/{agent_id}", payload)
        print(f"агент обновлён: {agent_id}")
    else:
        agent_id = client.call("POST", "/v1/convai/agents/create", payload)["agent_id"]
        saved["ELEVENLABS_AGENT_ID"] = agent_id
        print(f"агент создан: {agent_id}")

    saved["PLUMO_PUBLIC_URL"] = public_url
    set_env_values(ENV_FILE, saved)
    print(f"записано в {ENV_FILE.name}: {', '.join(sorted(saved))}")
    print("Перезапустите backend, чтобы он прочитал новые значения. Номер подключается в панели, см. VOICE.md.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    raise SystemExit(main())

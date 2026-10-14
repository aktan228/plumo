"""Server-side channel credentials. The dashboard picks one by name; the token never leaves the server.

CHANNEL_CREDENTIALS_FILE points to a JSON file (git-ignored), for example:

    {
      "credentials": [
        {"ref": "tg-demo", "channel": "telegram", "label": "Тестовый бот",
         "token_env": "TELEGRAM_DEMO_BOT_TOKEN", "business_ids": ["<uuid>"]},
        {"ref": "ig-demo", "channel": "instagram", "label": "Тестовый Instagram",
         "token_env": "INSTAGRAM_DEMO_ACCESS_TOKEN", "business_ids": ["<uuid>"]}
      ]
    }

`token_env` names an environment variable with the secret; `token` may hold it inline.
The file is read on every use, so replacing a token needs no restart.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

logger = logging.getLogger("plumo.channels")


@dataclass(frozen=True, slots=True)
class ChannelCredential:
    ref: str
    channel: str
    label: str
    business_ids: frozenset[str]
    token_env: str | None = None
    inline_token: str | None = None

    def allowed_for(self, business_id: UUID) -> bool:
        return "*" in self.business_ids or str(business_id) in self.business_ids

    def secret(self) -> str | None:
        if self.token_env:
            value = os.getenv(self.token_env, "").strip()
            if value:
                return value
        return (self.inline_token or "").strip() or None

    def __repr__(self) -> str:  # never print the token
        return f"ChannelCredential(ref={self.ref!r}, channel={self.channel!r})"


class CredentialStore:
    def __init__(self, path: str | None) -> None:
        self.path = (path or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.path) and Path(self.path).is_file()

    def all(self) -> list[ChannelCredential]:
        if not self.path:
            return []
        file = Path(self.path)
        if not file.is_file():
            logger.warning("channel_credentials_file_missing", extra={"path_name": file.name})
            return []
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.error("channel_credentials_file_invalid", extra={"path_name": file.name})
            return []
        items = raw.get("credentials", []) if isinstance(raw, dict) else []
        result = []
        for item in items:
            if not isinstance(item, dict) or not item.get("ref") or item.get("channel") not in ("telegram", "instagram"):
                continue
            result.append(
                ChannelCredential(
                    ref=str(item["ref"])[:64],
                    channel=str(item["channel"]),
                    label=str(item.get("label") or item["ref"])[:100],
                    business_ids=frozenset(str(value) for value in item.get("business_ids") or []),
                    token_env=str(item["token_env"]) if item.get("token_env") else None,
                    inline_token=str(item["token"]) if item.get("token") else None,
                )
            )
        return result

    def available(self, business_id: UUID, channel: str) -> list[ChannelCredential]:
        return [item for item in self.all() if item.channel == channel and item.allowed_for(business_id)]

    def get(self, ref: str, business_id: UUID, channel: str) -> ChannelCredential | None:
        for item in self.available(business_id, channel):
            if item.ref == ref:
                return item
        return None

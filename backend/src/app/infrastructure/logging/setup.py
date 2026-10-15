"""JSON logs with the correlation id of the current request."""

import json
import logging
import re

from app.correlation import get_correlation_id, get_request_id

_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_SECRET = re.compile(r"key|secret|password|token|authorization|credential", re.IGNORECASE)
# Telegram puts the bot token into every API URL; Meta tokens travel as Bearer.
_BOT_TOKEN = re.compile(r"bot\d{5,}:[A-Za-z0-9_-]{20,}")
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}")


def redact(text: str) -> str:
    return _BOT_TOKEN.sub("bot[redacted]", _BEARER.sub("Bearer [redacted]", text))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "correlation_id": get_correlation_id(),
            "request_id": get_request_id(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD or key.startswith("_") or _SECRET.search(key):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str) -> None:
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # httpx logs every request URL at INFO, and a Telegram URL carries the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

"""JSON logs with the correlation id of the current request."""

import json
import logging
import re

from app.correlation import get_correlation_id, get_request_id

_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_SECRET = re.compile(r"key|secret|password|token|authorization|credential", re.IGNORECASE)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
            "request_id": get_request_id(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD or key.startswith("_") or _SECRET.search(key):
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str) -> None:
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

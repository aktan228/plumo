"""Drop secret-looking values before they reach a log line."""

import re

_SECRET_KEY = re.compile(r"key|secret|password|token|authorization|credential", re.IGNORECASE)
_SECRET_VALUE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,})|((?i:api[_-]?key|secret|token|password)\s*[:=]\s*\S+)"
)


def scrub_mapping(values: dict | None) -> dict:
    if not values:
        return {}
    clean: dict = {}
    for key, value in values.items():
        if _SECRET_KEY.search(str(key)):
            continue
        clean[key] = value
    return clean


def scrub_text(text: str) -> str:
    return _SECRET_VALUE.sub("[redacted]", text)

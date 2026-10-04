"""Parse a meeting slot from a message. No calendar provider involved."""

import re
from datetime import UTC, datetime, timedelta

from app.domain.text_signals import normalize_text

_DATE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def parse_slot(text: str, payload: dict | None, now: datetime) -> datetime:
    """Resolve a concrete datetime. Missing date means the next day, missing time means 15:00."""

    data = payload or {}
    raw_dt = data.get("datetime")
    if isinstance(raw_dt, str) and raw_dt.strip():
        parsed = datetime.fromisoformat(raw_dt)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    date_source = str(data.get("date") or "")
    time_source = str(data.get("time") or "")
    date_match = _DATE.search(date_source) or _DATE.search(text)
    time_match = _TIME.search(time_source) or _TIME.search(text)
    hour = int(time_match.group(1)) if time_match else 15
    minute = int(time_match.group(2)) if time_match else 0
    if hour > 23 or minute > 59:
        hour, minute = 15, 0
    if date_match:
        return datetime(
            int(date_match.group(1)),
            int(date_match.group(2)),
            int(date_match.group(3)),
            hour,
            minute,
            tzinfo=UTC,
        )
    probe = normalize_text(f"{text} {data}")
    day = (now + timedelta(days=1)).date()
    if "послезавтра" in probe:
        day = (now + timedelta(days=2)).date()
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)

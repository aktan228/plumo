"""Parse a meeting slot from a message. No calendar provider involved."""

import re
from datetime import datetime, timedelta, timezone

from app.domain.text_signals import normalize_text

# Kyrgyzstan is UTC+6 all year (no DST). A fixed offset avoids the tzdata
# dependency that zoneinfo needs on Windows.
BUSINESS_TZ = timezone(timedelta(hours=6), "Asia/Bishkek")

_DATE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")
# Monday = 0. Russian stems and Kyrgyz day names.
_WEEKDAYS = (
    (("понедельник", "дүйшөмбү", "дуйшомбу"), 0),
    (("вторник", "шейшемби"), 1),
    (("сред", "шаршемби"), 2),
    (("четверг", "бейшемби"), 3),
    (("пятниц", "жума күнү", "жумада"), 4),
    (("суббот", "ишемби"), 5),
    (("воскресень", "жекшемби"), 6),
)
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def parse_slot(text: str, payload: dict | None, now: datetime) -> datetime:
    """Resolve a concrete datetime in business local time.

    Customers say "завтра в 15:00" meaning Bishkek time. Missing date means
    the next day, missing time means 15:00. Garbage from a model payload is
    ignored instead of failing the whole message.
    """

    data = payload or {}
    local_now = now.astimezone(BUSINESS_TZ)
    raw_dt = data.get("datetime")
    if isinstance(raw_dt, str) and raw_dt.strip():
        try:
            parsed = datetime.fromisoformat(raw_dt.strip())
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=BUSINESS_TZ)

    date_source = str(data.get("date") or "")
    time_source = str(data.get("time") or "")
    date_match = _DATE.search(date_source) or _DATE.search(text)
    time_match = _TIME.search(time_source) or _TIME.search(text)
    hour = int(time_match.group(1)) if time_match else 15
    minute = int(time_match.group(2)) if time_match else 0
    if hour > 23 or minute > 59:
        hour, minute = 15, 0
    if date_match:
        try:
            return datetime(
                int(date_match.group(1)),
                int(date_match.group(2)),
                int(date_match.group(3)),
                hour,
                minute,
                tzinfo=BUSINESS_TZ,
            )
        except ValueError:
            pass
    probe = normalize_text(f"{text} {data}")
    day = (local_now + timedelta(days=1)).date()
    if "послезавтра" in probe:
        day = (local_now + timedelta(days=2)).date()
    elif "сегодня" in probe or "бүгүн" in probe or "бугун" in probe:
        day = local_now.date()
    elif (weekday := _weekday(probe)) is not None:
        ahead = (weekday - local_now.weekday()) % 7 or 7
        day = (local_now + timedelta(days=ahead)).date()
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=BUSINESS_TZ)



def _weekday(text: str) -> int | None:
    for names, index in _WEEKDAYS:
        if any(name in text for name in names):
            return index
    return None


def has_slot(text: str) -> bool:
    """True when the customer named a day or a time, not just "запишите меня"."""

    probe = normalize_text(text)
    if _TIME.search(probe) or _DATE.search(probe):
        return True
    if re.search(r"\bв\s+\d{1,2}\b", probe):  # "в 11", "в 3 часа"
        return True
    if any(word in probe for word in ("завтра", "сегодня", "бүгүн", "бугун", "эртең", "эртен")):
        return True
    return _weekday(probe) is not None

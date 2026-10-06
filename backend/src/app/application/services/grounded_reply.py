"""Grounded fallback when a live model returns an unusable draft."""

import re

from app.domain.models import AgentContext

_JUNK = (
    "user safety",
    "content policy",
    "as an ai",
    "i cannot",
    "i can't",
    "safety: safe",
)


def is_unusable_reply(text: str) -> bool:
    blob = (text or "").strip()
    if not blob:
        return True
    lowered = blob.lower()
    if any(marker in lowered for marker in _JUNK):
        return True
    if re.fullmatch(r"[\s{}\[\]\"':,a-z_]*safe[\s{}\[\]\"':,a-z_]*", lowered):
        return True
    if len(blob) < 8 and re.search(r"[а-яё]", lowered) is None:
        return True
    return False


def quote_knowledge(context: AgentContext) -> str:
    if not context.knowledge:
        return "Я не хочу давать вам неточную информацию. Уточню это у менеджера."
    lines = [f"{hit.item.title}: {hit.item.content}" for hit in context.knowledge[:3]]
    return "В базе такие объекты:\n" + "\n".join(lines)

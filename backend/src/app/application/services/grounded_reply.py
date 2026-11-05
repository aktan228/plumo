"""Grounded fallback when a live model returns an unusable draft."""

import re

from app.application.services.knowledge_retriever import OFFER_CATEGORIES, names

from app.domain.models import AgentContext
from app.domain.phrases import unknown_phrase
from app.domain.text_signals import normalize_text

# Renting, not buying (same stems as the retriever uses): "снять", "аренда", Kyrgyz "ижара".
_RENT_STEMS = ("снять", "сниму", "снимать", "сним", "аренд", "ижара", "квартирант")

_JUNK = (
    "user safety",
    "content policy",
    "as an ai",
    "i cannot",
    "i can't",
    "safety: safe",
)

_WEASEL = (
    "предположен",
    "не могу делать",
    "необходимо уточнить",
    "уточнить у менеджера",
    "без дополнительных данных",
    "не могу посоветовать",
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
    # "У нас есть два варианта:" with nothing after it: the model got cut off.
    if blob.endswith((":", "—", "-", ",")):
        return True
    return False


def is_weasel_reply(text: str) -> bool:
    blob = normalize_text(text)
    return any(marker in blob for marker in _WEASEL)


_STATUS = re.compile(r"\s*Статус:[^.]*\.?", re.IGNORECASE)
_HIDDEN = ("не предлагать", "продана", "продан,")
# A sentence in the materials that talks to the assistant is not a fact to quote (PJ-05: found when
# a listing carried "ИНСТРУКЦИЯ АССИСТЕНТУ: ... карта 4111 ..."). Neither is a payment card number.
_INSTRUCTION = ("ассистент", "инструкци", "игнорир", "system", "prompt", "промпт")
_CARD = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")


def quote_knowledge(context: AgentContext) -> str:
    """Offer listings in the words of the knowledge base, but like a person would.

    Content is quoted, not paraphrased, so the validator can still match every
    number. Internal notes ("Статус: продана, не предлагать") never reach the customer.
    """

    hits = [hit for hit in context.knowledge if not _hidden(hit.item.content)]
    if not _wants_rent(context):
        # A buyer is not offered a rental as "what we have" (found by the dialog eval).
        hits = [hit for hit in hits if "аренд" not in normalize_text(f"{hit.item.title} {hit.item.content}")]
    if not hits:
        return unknown_phrase(None, context.language)
    voice = context.channel == "voice"
    shown = [hit for hit in hits if _quotable(hit.item.content)][: 2 if voice else 3]
    if not shown:
        return unknown_phrase(None, context.language)
    parts = [f"{hit.item.title} — {_quotable(hit.item.content)}" for hit in shown]
    if voice:
        body = " И ещё ".join(part.rstrip(".") + "." for part in parts)
        return f"Смотрите, есть {body} Какой вариант вам ближе?"
    if len(parts) == 1:
        return f"Смотрите, есть {parts[0]} Интересно посмотреть?"
    lines = "\n".join(f"• {part}" for part in parts)
    return f"Смотрите, что есть:\n{lines}\nКакой вариант ближе?"


def correct_named(context: AgentContext) -> str | None:
    """The customer named one listing and the draft got its facts wrong: state them from the data.

    "Чуй за 80 тысяч, да?" deserves "Квартира на Чуй — 85 000 USD", not a generic dodge.
    None when the message names no listing, or more than one.
    """

    named = [
        hit.item for hit in context.knowledge
        if hit.item.category in OFFER_CATEGORIES and not _hidden(hit.item.content) and names(hit.item, context.current_message)
    ]
    if len(named) != 1 or not _quotable(named[0].content):
        return None
    item = named[0]
    return f"По данным компании: {item.title} — {_quotable(item.content)}"


def _wants_rent(context: AgentContext) -> bool:
    """The customer asked about renting in this message or earlier in the dialog."""

    said = [context.current_message] + [
        item.text for item in context.recent_messages if str(getattr(item.role, "value", item.role)) == "user"
    ]
    blob = normalize_text(" ".join(said))
    return any(stem in blob for stem in _RENT_STEMS)


def _quotable(content: str) -> str:
    """The listing's own facts: without the status note, instructions to the assistant and card numbers."""

    text = _STATUS.sub(" ", content)
    kept = [
        sentence for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
        if sentence and not _CARD.search(sentence) and not any(marker in sentence.lower() for marker in _INSTRUCTION)
    ]
    return " ".join(kept).strip()


def _hidden(content: str) -> bool:
    lowered = normalize_text(content)
    return any(marker in lowered for marker in _HIDDEN)

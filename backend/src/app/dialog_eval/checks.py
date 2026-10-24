"""Deterministic checks over a finished dialog. The judge explains; these numbers do not depend on a model."""

from __future__ import annotations

import re
from typing import Any

from app.dialog_eval.personas import Persona
from app.dialog_eval.runner import Dialog
from app.domain.text_signals import detect_language, money_numbers, normalize_text

LONG_SENTENCES = 3
REPEAT_SIMILARITY = 0.6
_SALE_PRICES = {"39000", "62000", "85000", "110000", "165000", "79000"}
_RENT_HINT = re.compile(r"(?<!\d)450(?!\d)|в месяц|айына|аренд|ижара")


def catalog_numbers() -> set[str]:
    """Every amount the business data allows the agent to say."""

    from app.bench.run import demo_business

    business, items = demo_business()
    texts = [item.content for item in items] + [business.description, business.working_hours, business.rules]
    texts += [str(value) for value in business.contacts.values()]
    return {number for text in texts for number in money_numbers(text)}


def sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?…])\s+", text.strip()) if part.strip()]


def questions(text: str) -> list[str]:
    return [part for part in sentences(text) if part.rstrip().endswith("?")]


def _stems(text: str) -> set[str]:
    # A crude stem is enough to catch "Для себя или под инвестицию?" asked again in other words.
    return {word[:5] for word in re.findall(r"[a-zа-яңөү]{3,}", normalize_text(text))}


def similar(left: str, right: str) -> bool:
    a, b = _stems(left), _stems(right)
    if len(a) < 2 or len(b) < 2:
        return False
    return len(a & b) / len(a | b) >= REPEAT_SIMILARITY


def check_dialog(dialog: Dialog, persona: Persona, allowed_numbers: set[str] | None = None) -> dict[str, Any]:
    allowed = set(allowed_numbers if allowed_numbers is not None else catalog_numbers())
    for turn in dialog.turns:
        allowed.update(money_numbers(turn.customer))
    replies = [(index, turn.agent) for index, turn in enumerate(dialog.turns, 1) if turn.agent]

    repeated: list[dict] = []
    asked: list[str] = []
    for index, text in replies:
        mine = questions(text)
        for question in mine:
            if any(similar(question, before) for before in asked):
                repeated.append({"turn": index, "question": question})
        asked.extend(mine)

    lengths = [len(text) for _, text in replies]
    counts = [len(sentences(text)) for _, text in replies]
    wrong_language = [
        index
        for index, text in replies
        if (found := detect_language(text)) != "unknown" and found not in persona.languages
    ]
    invented = [
        {"turn": index, "number": number}
        for index, text in replies
        for number in money_numbers(text)
        if number not in allowed
    ]
    if persona.wants == "rent":
        wrong_offer = [index for index, text in replies if set(money_numbers(text)) & _SALE_PRICES]
    else:
        wrong_offer = [index for index, text in replies if _RENT_HINT.search(normalize_text(text))]

    reasons = [turn.handoff for turn in dialog.turns if turn.handoff]
    unwarranted = [reason for reason in reasons if reason not in persona.allowed_reasons]
    if persona.required_reasons:
        missing = not any(reason in persona.required_reasons for reason in reasons)
    else:
        # A customer who left a number is a lead: the manager must hear about it.
        missing = dialog.phone_saved and not reasons
    meeting = any("schedule_meeting" in turn.actions for turn in dialog.turns) or "ready_for_meeting" in reasons

    return {
        "agent_turns": len(replies),
        "repeated_questions": repeated,
        "avg_chars": round(sum(lengths) / len(lengths)) if lengths else 0,
        "avg_sentences": round(sum(counts) / len(counts), 1) if counts else 0,
        "long_replies": sum(count > LONG_SENTENCES for count in counts),
        "wrong_language": wrong_language,
        "substituted": sum(turn.substituted for turn in dialog.turns),
        "invented_numbers": invented,
        "wrong_offer": wrong_offer,
        "handoffs": reasons,
        "unwarranted_handoffs": unwarranted,
        "missing_handoff": missing,
        "phone_saved": dialog.phone_saved,
        "meeting": meeting,
        "end": dialog.end,
        "critical": bool(invented or missing or dialog.error),
    }

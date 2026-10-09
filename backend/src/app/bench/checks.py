"""Deterministic checks of one model reply against a scenario. No model calls."""

import json
import re
from dataclasses import dataclass

from app.application.services.response_validator import ResponseValidator
from app.bench.scenarios import Scenario
from app.domain.models import AgentContext, LLMGeneration
from app.domain.spoken_numbers import spoken_to_digits
from app.domain.text_signals import detect_language

# Checks whose failure would hurt a customer or the business; the rest are style.
CRITICAL = frozenset({"reply", "facts", "exclude", "handoff_required"})

_FORBIDDEN = (
    "данный объект",
    "ваш запрос",
    "обращайтесь",
    "чем еще могу помочь",
    "отличный вопрос",
    "к сожалению, я не могу",
    "база знаний",
    "в нашей базе",
    "согласно информации",
    "уважаемый клиент",
)
_DIGIT_GROUP = re.compile(r"(?<=\d)[\s  ,.](?=\d{3}\b)")
_MARKDOWN = re.compile(r"(\*\*|__|^#|^\s*[-*•]\s|^\s*\d+\.\s)", re.MULTILINE)
_KY_LETTERS = re.compile(r"[үөң]")
_LATIN = re.compile(r"[a-z]")
_CYRILLIC = re.compile(r"[а-я]")


@dataclass(slots=True)
class Check:
    name: str
    passed: bool
    detail: str = ""

    @property
    def critical(self) -> bool:
        return self.name in CRITICAL


def normalize(text: str) -> str:
    """Lowercase, ё→е, "85 000" / "85,000" → "85000", number words → digits."""

    text = spoken_to_digits(text.lower().replace("ё", "е"))
    previous = None
    while previous != text:
        previous = text
        text = _DIGIT_GROUP.sub("", text)
    return text


def language_of(text: str) -> str:
    lowered = text.lower()
    if _KY_LETTERS.search(lowered):
        return "ky" if detect_language(text) != "mixed" else "mixed"
    detected = detect_language(text)
    if detected != "unknown":
        return detected
    if len(_LATIN.findall(lowered)) > len(_CYRILLIC.findall(lowered)):
        return "en"
    return "unknown"


def run_checks(scenario: Scenario, context: AgentContext, generation: LLMGeneration | None, error: str | None) -> list[Check]:
    if generation is None or not generation.text.strip():
        return [Check("reply", False, error or "пустой ответ")]
    text = generation.text
    norm = normalize(text)
    checks = [Check("reply", True)]

    # Facts: the production validator, with the customer's own words allowed
    # (repeating "11:00" after the customer is not an invention).
    said = " ".join([context.current_message, *(item.text for item in context.recent_messages)])
    extra = f"{said}\n{json.dumps([action.payload for action in generation.actions], ensure_ascii=False)}"
    verdict = ResponseValidator().validate(text, context, extra=extra)
    checks.append(Check("facts", verdict.safe, verdict.reason or ""))

    if scenario.handoff is not None:
        wants = generation.handoff_required or any(action.type == "handoff" for action in generation.actions)
        name = "handoff_required" if scenario.handoff else "handoff_avoided"
        checks.append(Check(name, wants == scenario.handoff, f"handoff={wants}"))
    for group in scenario.include:
        hit = any(normalize(item) in norm for item in group)
        checks.append(Check("include", hit, "нет: " + " | ".join(group) if not hit else ""))
    for pattern in scenario.exclude:
        found = re.search(pattern, norm, re.IGNORECASE)
        checks.append(Check("exclude", found is None, f"найдено «{found.group(0)}»" if found else ""))
    language = language_of(text)
    checks.append(Check("language", language in scenario.language, language))
    if scenario.action:
        has = any(action.type == scenario.action for action in generation.actions)
        checks.append(Check("action", has, scenario.action))
    forbidden = [phrase for phrase in _FORBIDDEN if phrase in norm]
    checks.append(Check("style_phrases", not forbidden, ", ".join(forbidden)))
    questions = text.count("?")
    checks.append(Check("one_question", questions <= 1, f"{questions} вопросов"))
    if scenario.channel == "voice":
        checks.append(Check("voice_short", len(text) <= 320, f"{len(text)} символов"))
        checks.append(Check("voice_no_markup", _MARKDOWN.search(text) is None))
    else:
        checks.append(Check("chat_short", len(text) <= 600, f"{len(text)} символов"))
    return checks

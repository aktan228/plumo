"""Last gate before a reply is stored. Facts that are not in context become a handoff."""

import json
import re

from app.domain.models import AgentContext, QuestionAssessment, ValidationResult
from app.domain.text_signals import analyze_message, compact_numbers, contains_any, normalize_text

_MEASURE = re.compile(r"(\d{1,4})\s*-?\s*(?:м²|м2|м\b|этаж|комнат)")
_INSTALLMENT_YES = re.compile(r"(есть|доступ|возмож|оформ)")


class ResponseValidator:
    """Check a draft against the business card and the retrieved knowledge."""

    def assess(self, text: str, context: AgentContext) -> QuestionAssessment:
        signals = analyze_message(text)
        if not signals.factual:
            return QuestionAssessment(factual=False, answerable=True, topic=None)
        topic = _topic(signals)
        return QuestionAssessment(factual=True, answerable=self._supported(signals, context), topic=topic)

    def validate(self, response: str, context: AgentContext, extra: str = "") -> ValidationResult:
        allowed = f"{_corpus(context)}\n{extra}"
        allowed_norm = normalize_text(allowed)
        allowed_numbers = set(compact_numbers(allowed))
        for number in compact_numbers(response):
            if number not in allowed_numbers:
                return ValidationResult(False, "invented_number")
        for match in _MEASURE.finditer(normalize_text(response)):
            if match.group(1) not in allowed_norm:
                return ValidationResult(False, "invented_detail")
        if _affirms_installment(response) and "рассроч" not in allowed_norm and "ипотек" not in allowed_norm:
            return ValidationResult(False, "invented_installment")
        if _affirms_availability(response) and not contains_any(allowed, ("доступ", "в наличии", "продае")):
            return ValidationResult(False, "invented_availability")
        return ValidationResult(True, None)

    def _supported(self, signals, context: AgentContext) -> bool:
        allowed_norm = normalize_text(_corpus(context))
        allowed_numbers = set(compact_numbers(allowed_norm))
        if signals.numbers and not (set(signals.numbers) & allowed_numbers):
            if signals.price or signals.availability or signals.property_details or signals.comparison:
                return False
        if signals.installment:
            return "рассроч" in allowed_norm or "ипотек" in allowed_norm
        if signals.hours:
            return bool(context.business.working_hours.strip())
        if signals.address:
            return bool((context.business.contacts or {}).get("address")) or "адрес" in allowed_norm
        if signals.contacts:
            return bool(context.business.contacts)
        if signals.comparison:
            return len(context.knowledge) >= 2
        if signals.price or signals.availability or signals.property_details:
            return len(context.knowledge) > 0
        if signals.numbers:
            return bool(set(signals.numbers) & allowed_numbers)
        return len(context.knowledge) > 0


def _topic(signals) -> str:
    if signals.installment:
        return "installment"
    if signals.comparison:
        return "comparison"
    if signals.price:
        return "price"
    if signals.availability:
        return "availability"
    if signals.hours:
        return "hours"
    if signals.address:
        return "address"
    if signals.contacts:
        return "contacts"
    return "property"


def _corpus(context: AgentContext) -> str:
    contacts = json.dumps(context.business.contacts or {}, ensure_ascii=False)
    parts = [
        context.business.name,
        context.business.description,
        context.business.working_hours,
        context.business.rules,
        contacts,
    ]
    for hit in context.knowledge:
        parts.append(hit.item.title)
        parts.append(hit.item.content)
        parts.append(hit.item.category)
    return "\n".join(parts)


def _affirms_installment(text: str) -> bool:
    normalized = normalize_text(text)
    if "рассроч" not in normalized and "ипотек" not in normalized:
        return False
    if any(phrase in normalized for phrase in ("нет информации", "не хочу давать", "уточню", "тактап")):
        return False
    return _INSTALLMENT_YES.search(normalized) is not None


def _affirms_availability(text: str) -> bool:
    normalized = normalize_text(text)
    if any(phrase in normalized for phrase in ("нет информации", "не хочу давать", "уточню", "тактап")):
        return False
    return contains_any(normalized, ("доступ", "в наличии", "еще прода", "продается", "объект бар"))

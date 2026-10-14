"""Last gate before a reply is stored. Facts that are not in context become a handoff."""

import json
import re

from app.domain.models import AgentContext, QuestionAssessment, ValidationResult
from app.domain.spoken_numbers import spoken_to_digits
from app.domain.text_signals import analyze_message, compact_numbers, contains_any, find_phones, normalize_text

_MEASURE = re.compile(r"(\d{1,4})\s*-?\s*(?:м²|м2|м\b|этаж|комнат)")
# No calendar is connected: a booking is only a wish the manager confirms, and a
# live transfer does not exist. Promising either misleads the customer.
_FALSE_BOOKING = re.compile(
    r"записал[аи]?\s+(?:вас|тебя|на\b)|записываю\s+(?:вас|тебя|на\b)|вы записаны|забронир|зарезервир|жазып алдым|броньдоо(?:ду)? (?:жасадым|кылдым)"
)
_FALSE_TRANSFER = re.compile(r"перевожу вас|соединяю вас|соединю вас|оставайтесь на линии|не отключайтесь")
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
        allowed_numbers = set(compact_numbers(allowed)) | set(_DIGITS.findall(_join_thousands(allowed_norm)))
        customer_numbers = set(_DIGITS.findall(_join_thousands(normalize_text(_customer_text(context)))))
        spoken = _join_thousands(spoken_to_digits(normalize_text(response)))
        for number in _reply_numbers(response):
            if number in allowed_numbers:
                continue
            # "Понял, до 7000": repeating the customer's own budget is not a fact.
            # "Есть за 7000" is: agreeing to a price the customer named stays invented.
            if number in customer_numbers and _BUDGET_ECHO(number).search(spoken):
                continue
            return ValidationResult(False, "invented_number")
        for match in _MEASURE.finditer(normalize_text(response)):
            if match.group(1) not in allowed_norm:
                return ValidationResult(False, "invented_detail")
        normalized_response = normalize_text(response)
        if _FALSE_BOOKING.search(normalized_response):
            return ValidationResult(False, "unconfirmed_booking")
        if _FALSE_TRANSFER.search(normalized_response):
            return ValidationResult(False, "false_transfer")
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
        if signals.comparison or signals.catalog or signals.recommend:
            return len(context.knowledge) >= 1
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
    if signals.catalog or signals.recommend:
        return "property"
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


_DIGITS = re.compile(r"\d+")
# A money amount of any length: "300 сом", "150 сомов". Bare short numbers ("2 этаж",
# "15 роз") are not checked: they are counts, and the measure check covers details.
_MONEY = re.compile(r"(?<!\d)(\d{2,})\s*(?:сом|kgs|usd|\$|долл|руб|₽|eur|€|тенге|тг\b)")


def _BUDGET_ECHO(number: str) -> re.Pattern[str]:
    return re.compile(rf"(?:бюджет\w*|до|от|в пределах|около|примерно|на сумму|в районе)\s+(?:\d+\s+(?:до|-|–)\s+)?{number}(?!\d)")


def _join_thousands(text: str) -> str:
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"(?<=\d)\s+(?=\d{3}(?!\d))", "", text)
    return text


def _reply_numbers(response: str) -> set[str]:
    """Amounts in a reply, whether the model wrote "5200 сом" or "пять тысяч двести сомов".

    The prompt asks for digits, but a voice reply sometimes comes in words, and a
    price in words must not slip past the check that compares digits.
    """

    numbers: set[str] = set()
    for text in (normalize_text(response), spoken_to_digits(normalize_text(response))):
        joined = _join_thousands(text)
        numbers.update(compact_numbers(joined))
        numbers.update(_MONEY.findall(joined))
    return numbers


def _customer_text(context: AgentContext) -> str:
    said = [message.text for message in context.recent_messages if str(message.role) == "user"]
    return "\n".join([*said, context.current_message or ""])


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
    # What the agent said earlier already passed this gate: a listing found two
    # turns ago may be mentioned again even if this turn's search missed it.
    for message in context.recent_messages:
        if str(message.role) == "assistant":
            parts.append(message.text)
    # The customer's own phone is theirs, not an invented fact; repeating it back is fine.
    if find_phones(context.current_message):
        parts.append(context.current_message)
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

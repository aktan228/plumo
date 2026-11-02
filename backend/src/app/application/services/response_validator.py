"""Last gate before a reply is stored. Facts that are not in context become a handoff."""

import json
import re

from app.application.services.knowledge_retriever import OFFER_CATEGORIES as _OFFERS, names
from app.domain.models import AgentContext, QuestionAssessment, ValidationResult
from app.domain.text_signals import (
    PHONE_RE,
    analyze_message,
    compact_numbers,
    contains_any,
    find_phones,
    money_numbers,
    normalize_text,
)

_MEASURE = re.compile(r"(\d{1,4})\s*-?\s*(?:м²|м2|м\b|этаж|комнат)")
# No calendar is connected: a booking is only a wish the manager confirms, and a
# live transfer does not exist. Promising either misleads the customer.
_FALSE_BOOKING = re.compile(
    r"записал[аи]?(?!\s+(?:ваш|вашу|ваши|ваше|номер|телефон|контакт|пожелан|вопрос|имя|запрос))(?![а-яё])"
    r"|записываю\s+(?:вас|тебя|на\b)|вы записаны|забронир|зарезервир|жазып алдым|броньдоо(?:ду)? (?:жасадым|кылдым)"
    r"|подтвердил[аи]?\s+(?:вас|время|встреч|запис|просмотр|показ)|подтверждаю\s+(?:время|встреч|запис|просмотр|показ)"
)
_FALSE_TRANSFER = re.compile(r"перевожу вас|соединяю вас|соединю вас|оставайтесь на линии|не отключайтесь")
# The manager notification goes out after this reply, through the queue: at reply time nobody
# knows yet that the manager got it. "Передал менеджеру" is true (the handoff is stored); "получил" is not.
_FALSE_NOTIFIED = re.compile(
    r"менеджер\w*\s+(?:уже\s+)?(?:получил|уведомл[её]н|в курсе|увидел|видит|прочитал)"
    r"|уведомил[аи]?\s+(?:\w+\s+)?менеджер"
)
_INSTALLMENT_YES = re.compile(r"(есть|доступ|возмож|оформ)")
# The customer naming their own budget: echoing it back ("в рамках 90 000") invents nothing.
_BUDGET = ("бюджет", "до ", "в пределах", "в рамках", "максимум", "не больше", "не дороже", "рассчитыва", "ориентир", "чейин")
# But a price the customer attributes to someone, or bargains for, must not pass as a fact.
_CLAIM = ("сказал", "говорил", "обещал", "писал", "видел", "скин", "уступ", "за сколько", "стоит", "стоил")
# Sentences, then the parts of a list inside one: "на Чуй — 85 000, на Киевской — 62 000".
_SENTENCE = re.compile(r"[.!?\n]+")
_CLAUSE = re.compile(r"[,;]")


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
        # Numbers and measures come from current data only. An earlier reply of the agent is not a
        # source: the listing may have changed or been switched off since (the retriever brings a
        # listing named in the last turns back into `knowledge` while it is still active).
        facts = f"{_corpus(context, history=False)}\n{extra}"
        facts_norm = normalize_text(facts)
        allowed_numbers = set(money_numbers(facts)) | _budget_numbers(context)
        for number in money_numbers(response):
            if number not in allowed_numbers:
                return ValidationResult(False, "invented_number")
        for match in _MEASURE.finditer(normalize_text(response)):
            if match.group(1) not in facts_norm:
                return ValidationResult(False, "invented_detail")
        if _misattributed(response, context):
            return ValidationResult(False, "misattributed_fact")
        normalized_response = normalize_text(response)
        if _FALSE_BOOKING.search(normalized_response):
            return ValidationResult(False, "unconfirmed_booking")
        if _FALSE_TRANSFER.search(normalized_response):
            return ValidationResult(False, "false_transfer")
        if _FALSE_NOTIFIED.search(normalized_response):
            return ValidationResult(False, "unconfirmed_notification")
        if _ambiguous(response, context):
            return ValidationResult(False, "ambiguous_object")
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
            return bool(context.business.working_hours.strip()) or any(
                hit.item.category == "faq" and contains_any(f"{hit.item.title} {hit.item.content}", ("работ", "график", "час", "hours", "open"))
                for hit in context.knowledge
            )
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


def _misattributed(response: str, context: AgentContext) -> bool:
    """A price said about one listing that is not that listing's price.

    The number exists in context (another listing has it, or it is the customer's budget),
    so the plain number check lets it through. Each part of a sentence that names exactly
    one listing must carry only that listing's numbers. A part naming none takes the
    sentence's only listing; with two or more it is a comparison and is left alone.
    """

    offers = [hit.item for hit in context.knowledge if hit.item.category in _OFFERS]
    if not offers:
        return False
    for sentence in _SENTENCE.split(response):
        in_sentence = [item for item in offers if names(item, sentence)]
        for clause in _CLAUSE.split(sentence):
            named = [item for item in offers if names(item, clause)] or (in_sentence if len(in_sentence) == 1 else [])
            if len(named) != 1 or contains_any(clause, _BUDGET):
                continue
            own = set(money_numbers(f"{named[0].title} {named[0].content}"))
            if any(number not in own for number in money_numbers(PHONE_RE.sub(" ", clause))):
                return True
    return False


def ambiguous_offers(context: AgentContext) -> list:
    """Listings the customer may mean when they ask about "the flat" without saying which.

    Empty when the question names a listing (by title or by its price), when the last
    turns already settled which one, or when there is only one to talk about.
    """

    offers = [hit.item for hit in context.knowledge if hit.item.category in _OFFERS]
    if len(offers) < 2:
        return []
    signals = analyze_message(context.current_message)
    if not (signals.price or signals.availability or signals.property_details):
        return []
    if signals.catalog or signals.comparison or signals.recommend:
        # "Какие есть квартиры?" asks for all of them.
        return []
    said = " ".join([context.current_message, *(message.text for message in context.recent_messages[-2:])])
    if any(names(item, said) for item in offers):
        return []
    asked = set(money_numbers(context.current_message))
    if any(asked & set(money_numbers(f"{item.title} {item.content}")) for item in offers):
        return []
    return offers


def _ambiguous(response: str, context: AgentContext) -> bool:
    """A price or detail given for "it" while several listings fit the question: a guess."""

    offers = ambiguous_offers(context)
    if not offers or any(names(item, response) for item in offers):
        return False
    numbers = set(money_numbers(PHONE_RE.sub(" ", response)))
    if not numbers:
        return bool(_MEASURE.search(normalize_text(response)))
    # Prices of two or more listings side by side are a list, not a guess about one.
    matching = [item for item in offers if numbers & set(money_numbers(f"{item.title} {item.content}"))]
    return len(matching) <= 1


def _corpus(context: AgentContext, history: bool = True) -> str:
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
    # Words the agent used earlier ("доступна", "рассрочка") may be repeated. Its numbers may not:
    # `validate` checks numbers against current data only.
    if history:
        for message in context.recent_messages:
            if str(message.role) == "assistant":
                parts.append(message.text)
    # The customer's own phone is theirs, not an invented fact; repeating it back is fine.
    if find_phones(context.current_message):
        parts.append(context.current_message)
    return "\n".join(parts)


def _budget_numbers(context: AgentContext) -> set[str]:
    """Amounts the customer gave as their own budget, in this turn or earlier."""

    texts = [context.current_message] + [
        message.text for message in context.recent_messages if str(message.role) == "user"
    ]
    numbers: set[str] = set()
    for text in texts:
        normalized = normalize_text(text)
        if contains_any(normalized, _BUDGET) and not contains_any(normalized, _CLAIM):
            numbers.update(money_numbers(normalized))
    return numbers


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

"""A stand-in sales agent. It only speaks from the context it was given."""

import re

from app.domain.enums import ActionType
from app.domain.models import (
    Action,
    AgentContext,
    Classification,
    ExtractedCustomerData,
    LLMGeneration,
    Message,
    RouteDecision,
    SummaryDraft,
    utcnow,
)
from app.domain.phrases import human_phrase, unknown_phrase
from app.domain.scheduling import has_slot, parse_slot
from app.domain.text_signals import (
    analyze_message,
    compact_numbers,
    detect_language,
    find_phones,
    normalize_text,
)

_COST = {"small": 0.001, "big": 0.01}
_HARD = ("installment", "money", "comparison", "objection", "emotional")


class MockLLMProvider:
    """Deterministic provider registered as `mock`.

    Small and big are two instances of this class. They share the same
    fact boundary: if the context has no supporting text, the reply refuses.
    """

    def __init__(self, name: str, tier: str) -> None:
        self.name = name
        self.tier = tier

    async def generate_response(self, context: AgentContext, route: RouteDecision) -> LLMGeneration:
        signals = analyze_message(context.current_message)
        prompt = context.current_message
        if self.tier == "small" and signals.unclear_confirmation:
            return self._out("Давайте уточню: вам про квартиру, цену или просмотр?", 0.4, prompt=prompt)
        if self.tier == "small" and any(getattr(signals, name) for name in _HARD):
            return self._out("Давайте уточню: вам про квартиру, цену или просмотр?", 0.36, prompt=prompt)
        if signals.unclear_confirmation:
            return self._out(
                "Не совсем поняла. Подсказать по квартирам, ценам или записать на просмотр?",
                0.84,
                prompt=prompt,
            )
        if signals.human_request:
            return self._out(human_phrase(context.language), 0.97, prompt=prompt)
        if signals.meeting and not signals.installment:
            return self._meeting(context, prompt)
        if signals.hours and context.business.working_hours:
            return self._out(f"Мы работаем {context.business.working_hours}.", 0.95, prompt=prompt)
        if signals.address:
            address = (context.business.contacts or {}).get("address")
            if address:
                return self._out(f"Адрес: {address}.", 0.94, prompt=prompt)
        if signals.contacts:
            phone = (context.business.contacts or {}).get("phone")
            if phone:
                return self._out(f"Связаться можно по номеру {phone}.", 0.94, prompt=prompt)
        if signals.installment and not _corpus_has(context, "рассроч", "ипотек"):
            return self._out(unknown_phrase("installment", context.language), 0.9, prompt=prompt)
        if signals.comparison and len(context.knowledge) >= 2:
            return self._out(_render_many(context, signals), 0.86, prompt=prompt)
        if signals.objection:
            return self._out(
                "Понимаю. Можем подобрать вариант подешевле — какой бюджет вам комфортен?",
                0.8,
                prompt=prompt,
            )
        if signals.emotional:
            return self._out("Простите, что так получилось. Сейчас подключу менеджера, он разберётся.", 0.88, prompt=prompt)
        listing = _best_listing(context, signals)
        if listing is not None and (signals.availability or signals.price or signals.property_details or signals.numbers):
            return self._out(_render_listing(listing, signals), 0.93, prompt=prompt)
        if (
            context.knowledge
            and not signals.numbers
            and (signals.availability or signals.price or signals.property_details)
        ):
            return self._out(_render_many(context, signals), 0.86, prompt=prompt)
        if signals.greeting and not signals.factual:
            return self._out(_greeting(context.language), 0.98, prompt=prompt)
        if signals.farewell:
            return self._out("До свидания! Будут вопросы — пишите в любое время.", 0.97, prompt=prompt)
        if signals.clear_confirmation:
            return self._out("Хорошо.", 0.96, prompt=prompt)
        if self.tier == "small":
            return self._out("Давайте уточню: вам про квартиру, цену или просмотр?", 0.42, prompt=prompt)
        return self._out(
            "Не совсем поняла. Подсказать по квартирам, ценам или записать на просмотр?",
            0.8,
            prompt=prompt,
        )

    async def classify(self, text: str, labels: list[str]) -> Classification:
        signals = analyze_message(text)
        guessed = "other"
        if signals.human_request:
            guessed = "handoff"
        elif signals.meeting:
            guessed = "meeting"
        elif signals.installment:
            guessed = "installment"
        elif signals.greeting:
            guessed = "greeting"
        elif signals.availability or signals.price:
            guessed = "availability"
        if labels and guessed not in labels:
            guessed = labels[0]
            return Classification(guessed, 0.4)
        return Classification(guessed, 0.9 if guessed != "other" else 0.4)

    async def summarize(self, messages: list[Message], previous: str | None) -> SummaryDraft:
        user_lines = [item.text for item in messages if item.role == "user"]
        blob = normalize_text(" ".join(user_lines))
        facts: list[str] = []
        if "квартир" in blob or compact_numbers(blob):
            facts.append("interest: property")
        if "рассроч" in blob:
            facts.append("asked: installment")
        if "встреч" in blob or "запис" in blob:
            facts.append("asked: meeting")
        need = None
        if "инвест" in blob:
            need = "investment"
        elif "для себя" in blob:
            need = "personal"
        last = user_lines[-1] if user_lines else (previous or "диалог начат")
        summary = f"Клиент интересовался: {last[:240]}"
        return SummaryDraft(summary=summary, need=need, important_facts=facts, status="active")

    async def extract_customer_data(self, text: str) -> ExtractedCustomerData:
        blob = normalize_text(text)
        phones = find_phones(text)
        need = None
        if "инвест" in blob:
            need = "investment"
        elif "для себя" in blob:
            need = "personal"
        language = detect_language(text)
        return ExtractedCustomerData(
            phone=phones[0] if phones else None,
            need=need,
            language=None if language == "unknown" else language,
        )

    def _meeting(self, context: AgentContext, prompt: str) -> LLMGeneration:
        if not has_slot(context.current_message):
            return self._out("Хорошо, давайте запишу вас на просмотр. Какой день и время вам удобны?", 0.9, prompt=prompt)
        slot = parse_slot(context.current_message, {}, utcnow())
        text = f"Давайте {_spoken_day(slot)} в {slot.strftime('%H:%M')}? Если неудобно — скажите, подберём другое время."
        action = Action(
            ActionType.schedule_meeting,
            {
                "text": context.current_message,
                "datetime": slot.isoformat(),
                "date": slot.date().isoformat(),
                "time": slot.strftime("%H:%M"),
            },
        )
        return self._out(text, 0.9, actions=[action], prompt=prompt)

    def _out(
        self,
        text: str,
        confidence: float,
        actions: list[Action] | None = None,
        prompt: str = "",
    ) -> LLMGeneration:
        return LLMGeneration(
            text=text,
            actions=list(actions or []),
            handoff_required=False,
            handoff_reason=None,
            confidence=confidence,
            model_used=self.name,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(text) // 4),
            estimated_cost=_COST[self.tier],
        )


class MockLanguageDetector:
    """Heuristic detector. Replace the class, not the call site."""

    async def detect(self, text: str) -> str:
        return detect_language(text)


_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _spoken_day(slot) -> str:
    return f"{slot.day} {_MONTHS[slot.month - 1]}"


def _greeting(language: str) -> str:
    if language == "ky":
        return "Салам! Кандай квартира издеп жатасыз?"
    return "Здравствуйте! Подскажу по квартирам — что вы ищете?"


def _corpus_has(context: AgentContext, *needles: str) -> bool:
    blob = normalize_text(
        "\n".join(hit.item.content + " " + hit.item.title for hit in context.knowledge)
        + " "
        + context.business.rules
    )
    return any(needle in blob for needle in needles)


def _best_listing(context: AgentContext, signals):
    if not context.knowledge:
        return None
    if signals.numbers:
        wanted = set(signals.numbers)
        for hit in context.knowledge:
            have = set(compact_numbers(f"{hit.item.title} {hit.item.content}"))
            if wanted & have:
                return hit
        return None
    if len(context.knowledge) == 1:
        return context.knowledge[0]
    if context.knowledge[0].score >= context.knowledge[1].score + 3:
        return context.knowledge[0]
    return None


def _render_listing(hit, signals) -> str:
    content = hit.item.content
    normalized = normalize_text(content)
    price = re.search(r"(\d[\d ]*)\s*usd", normalized, re.IGNORECASE)
    rooms = re.search(r"(\d+)\s*-?\s*комнат", normalized)
    area = re.search(r"(\d+)\s*м", normalized)
    floor = re.search(r"(\d+)\s*этаж", normalized)
    lead = "Здравствуйте! " if signals.greeting else ""
    if price is not None:
        amount = int(re.sub(r"\s+", "", price.group(1)))
        pretty = f"{amount:,}".replace(",", " ")
        lead += f"Да, квартира за {pretty} USD ещё доступна."
    elif "доступ" in normalized or signals.availability:
        lead += "Да, она ещё доступна."
    else:
        lead += f"{hit.item.title}."
    details: list[str] = []
    if rooms:
        details.append(f"{rooms.group(1)}-комнатная квартира")
    if area:
        details.append(f"{area.group(1)} м²")
    if floor:
        details.append(f"{floor.group(1)} этаж")
    if details:
        lead += " " + ", ".join(details) + "."
    lead += " Вам для себя или под инвестицию?"
    return lead


def _render_many(context: AgentContext, signals) -> str:
    lead = "Здравствуйте! " if signals.greeting else ""
    lines = [f"• {hit.item.title} — {hit.item.content}" for hit in context.knowledge[:3]]
    return lead + "Смотрите, что есть:\n" + "\n".join(lines) + "\nКакой вариант ближе?"

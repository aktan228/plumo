"""Rule router. It never calls a model, so a later MLRouter can replace it."""

from app.domain.enums import RouteModel
from app.domain.models import AgentContext, RouteDecision
from app.domain.text_signals import analyze_message


class RuleBasedRouter:
    """Choose small or big from explicit rules.

    Small: greeting, farewell, yes/no, address, hours, contacts, a single
    knowledge-base fact, meeting-time confirmation.
    Big: objections, comparison, money, mixed language, thin context.
    """

    async def select_model(self, context: AgentContext) -> RouteDecision:
        signals = analyze_message(context.current_message)
        hits = context.knowledge

        if signals.language == "mixed":
            return self._big("mixed_language", 0.9)
        if signals.emotional:
            return self._big("emotional_customer", 0.93)
        if signals.objection:
            return self._big("objection", 0.9)
        if signals.comparison or self._ambiguous_catalog(signals, hits):
            return self._big("comparison", 0.88)
        if signals.installment or signals.money:
            return self._big("money_or_installment", 0.91)
        if signals.human_request:
            return self._small("human_request", 0.97)
        if signals.greeting and not signals.factual:
            return self._small("greeting", 0.98)
        if signals.farewell:
            return self._small("farewell", 0.98)
        if signals.clear_confirmation:
            return self._small("confirmation", 0.96)
        if signals.unclear_confirmation:
            return self._small("short_confirmation", 0.84)
        if signals.hours:
            return self._small("business_hours", 0.95)
        if signals.address:
            return self._small("address", 0.94)
        if signals.contacts:
            return self._small("contacts", 0.94)
        if signals.meeting:
            return self._small("meeting_time", 0.9)
        if signals.factual and hits and self._simple_hit(signals, hits):
            return self._small("knowledge_base_simple_question", 0.94)
        if signals.factual:
            return self._big("no_confident_answer", 0.58)
        return self._big("no_confident_answer", 0.5)

    @staticmethod
    def _small(reason: str, confidence: float) -> RouteDecision:
        return RouteDecision(RouteModel.small, reason, confidence)

    @staticmethod
    def _big(reason: str, confidence: float) -> RouteDecision:
        return RouteDecision(RouteModel.big, reason, confidence)

    @staticmethod
    def _ambiguous_catalog(signals, hits) -> bool:
        if not (signals.factual and len(hits) >= 2 and not signals.numbers and not signals.installment):
            return False
        # "Квартира на Чуй ещё продаётся?" names one listing: not a comparison.
        return hits[0].score < hits[1].score + 2

    @staticmethod
    def _simple_hit(signals, hits) -> bool:
        if signals.complex:
            return False
        if len(hits) == 1:
            return True
        if signals.numbers:
            return hits[0].score >= hits[1].score + 3
        return hits[0].score >= hits[1].score + 2

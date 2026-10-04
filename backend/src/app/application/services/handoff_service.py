"""Human handoff. Notification transport is a port; the mock only logs."""

from uuid import uuid4

from app.domain.enums import HandoffPriority, HandoffStatus
from app.domain.errors import HandoffNotFound, InvalidState
from app.domain.events import HANDOFF_REQUESTED, DomainEvent
from app.domain.models import (
    Conversation,
    Customer,
    HandoffDecision,
    HandoffRequest,
    LLMGeneration,
    Message,
    QuestionAssessment,
    ValidationResult,
    utcnow,
)
from app.domain.ports import CustomerStore, EventBus, HandoffStore, HumanHandoffProvider
from app.domain.text_signals import MessageSignals

_PRIORITY = {
    HandoffPriority.low: 0,
    HandoffPriority.normal: 1,
    HandoffPriority.high: 2,
    HandoffPriority.urgent: 3,
}

_STATUS_BY_REASON = {
    "hot_lead": "hot",
    "ready_for_meeting": "hot",
    "user_requested_human": "handed_off",
    "no_knowledge": "handed_off",
    "unsafe_response": "handed_off",
    "customer_dissatisfied": "handed_off",
    "agent_unclear_twice": "handed_off",
}


def evaluate_handoff(
    signals: MessageSignals,
    assessment: QuestionAssessment,
    generation: LLMGeneration,
    validation: ValidationResult,
    unclear_count: int,
) -> HandoffDecision:
    """Pick the strongest reason to involve a human. Pure function, no I/O."""

    options: list[tuple[str, str]] = []
    if signals.human_request:
        options.append(("user_requested_human", HandoffPriority.high))
    if signals.hot_lead:
        options.append(("hot_lead", HandoffPriority.urgent))
    if signals.meeting:
        options.append(("ready_for_meeting", HandoffPriority.high))
    if assessment.factual and not assessment.answerable:
        options.append(("no_knowledge", HandoffPriority.normal))
    if not validation.safe:
        options.append((validation.reason or "unsafe_response", HandoffPriority.high))
    if signals.emotional:
        options.append(("customer_dissatisfied", HandoffPriority.high))
    if unclear_count >= 2:
        options.append(("agent_unclear_twice", HandoffPriority.normal))
    if not options:
        return HandoffDecision(required=False)
    reason, priority = max(options, key=lambda item: _PRIORITY[item[1]])
    return HandoffDecision(required=True, reason=reason, priority=priority)


class HandoffService:
    def __init__(
        self,
        handoffs: HandoffStore,
        customers: CustomerStore,
        provider: HumanHandoffProvider,
        events: EventBus,
    ) -> None:
        self.handoffs = handoffs
        self.customers = customers
        self.provider = provider
        self.events = events

    async def request(
        self,
        *,
        customer: Customer,
        conversation: Conversation,
        reason: str,
        priority: str,
        summary: str,
        recent_messages: list[Message],
    ) -> HandoffRequest:
        existing = await self.handoffs.find_open(conversation.id, reason)
        if existing is not None:
            return existing
        now = utcnow()
        handoff = HandoffRequest(
            id=uuid4(),
            customer_id=customer.id,
            conversation_id=conversation.id,
            reason=reason,
            priority=priority,
            summary=summary,
            recent_messages=[
                {"role": item.role, "text": item.text, "timestamp": item.timestamp.isoformat()}
                for item in recent_messages[-8:]
            ],
            status=HandoffStatus.pending,
            created_at=now,
            updated_at=now,
        )
        await self.handoffs.add(handoff)
        status = _STATUS_BY_REASON.get(reason)
        if status and customer.status != "merged":
            customer.status = status
            customer.updated_at = now
            await self.customers.save(customer)
        await self.provider.notify(handoff)
        await self.events.publish(
            DomainEvent(
                HANDOFF_REQUESTED,
                {
                    "handoff_id": str(handoff.id),
                    "customer_id": str(customer.id),
                    "reason": reason,
                    "priority": priority,
                },
            )
        )
        return handoff

    async def list_requests(self, status: str | None, limit: int = 50) -> list[HandoffRequest]:
        return await self.handoffs.list_requests(status, limit)

    async def accept(self, handoff_id) -> HandoffRequest:
        handoff = await self._get(handoff_id)
        if handoff.status != HandoffStatus.pending:
            raise InvalidState(f"handoff is {handoff.status}, expected PENDING")
        handoff.status = HandoffStatus.accepted
        handoff.updated_at = utcnow()
        return await self.handoffs.save(handoff)

    async def resolve(self, handoff_id) -> HandoffRequest:
        handoff = await self._get(handoff_id)
        if handoff.status not in (HandoffStatus.pending, HandoffStatus.accepted):
            raise InvalidState(f"handoff is {handoff.status} and cannot be resolved")
        handoff.status = HandoffStatus.resolved
        handoff.updated_at = utcnow()
        return await self.handoffs.save(handoff)

    async def _get(self, handoff_id) -> HandoffRequest:
        handoff = await self.handoffs.get(handoff_id)
        if handoff is None:
            raise HandoffNotFound(f"handoff {handoff_id} was not found")
        return handoff

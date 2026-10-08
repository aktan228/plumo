"""Phone calls on top of the same agent as chats.

The voice platform hears and speaks. This service decides what to say:
greeting with the legal notice, one agent turn per utterance, and the call
record for per-minute cost. It does not know which platform is behind it.
"""

import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.application.services.agent_service import AgentService
from app.application.services.context_builder import assistant_name
from app.domain.enums import CallStatus, Channel, MessageRole
from app.domain.models import CallReport, CallTurn, Customer, InboundMessage, VoiceCall, utcnow
from app.domain.phrases import call_greeting, listening_phrase
from app.domain.ports import CustomerStore, MessageStore, VoiceCallStore
from app.domain.text_signals import phone_from_id

logger = logging.getLogger("plumo.calls")


@dataclass(slots=True)
class CallGreeting:
    text: str
    language: str
    customer_id: UUID | None
    variables: dict[str, str]


@dataclass(slots=True)
class CallReply:
    text: str
    language: str
    handoff_required: bool


class CallService:
    def __init__(
        self,
        *,
        agent: AgentService,
        customers: CustomerStore,
        messages: MessageStore,
        calls: VoiceCallStore,
        provider: str,
        usd_per_minute: float = 0.0,
    ) -> None:
        self.agent = agent
        self.customers = customers
        self.messages = messages
        self.calls = calls
        self.provider = provider
        self.usd_per_minute = usd_per_minute

    async def start(self, turn: CallTurn) -> CallGreeting:
        """Greet the caller. A known phone gets their last question back."""

        business = await self.agent.resolve_business(_uuid(turn.business_id))
        customer = await self._known_customer(turn.caller)
        language = customer.language if customer and customer.language in ("ru", "ky") else "ru"
        last_question = await self._last_question(customer) if customer else None
        if turn.call_id:
            await self._touch_call(turn, customer.id if customer else None)
        variables = {
            "plumo_customer_id": str(customer.id) if customer else "",
            "plumo_language": language,
            "plumo_returning": "yes" if last_question else "no",
        }
        return CallGreeting(
            text=call_greeting(business.name, language, last_question, assistant_name(business)),
            language=language,
            customer_id=customer.id if customer else None,
            variables=variables,
        )

    async def answer(self, turn: CallTurn) -> CallReply:
        """Run one utterance through AgentService with channel=voice."""

        if not turn.text.strip():
            return CallReply(listening_phrase("ru"), "ru", False)
        response = await self.agent.process_message(
            InboundMessage(
                channel=Channel.voice,
                external_user_id=_caller_key(turn),
                text=turn.text,
                business_id=_uuid(turn.business_id),
                metadata={"provider": self.provider, "call_id": turn.call_id},
            )
        )
        if turn.call_id:
            await self._touch_call(turn, response.customer_id)
        return CallReply(response.response_text, response.language, response.handoff_required)

    async def finish(self, report: CallReport) -> VoiceCall:
        """Store duration and cost after hang-up. Repeated webhooks update the same row."""

        now = utcnow()
        call = await self.calls.get_by_provider_id(self.provider, report.call_id)
        customer = await self._known_customer(report.caller)
        if call is None:
            call = VoiceCall(
                id=uuid4(),
                provider=self.provider,
                provider_call_id=report.call_id,
                customer_id=customer.id if customer else None,
                caller=report.caller,
                called=report.called,
                status=report.status,
                started_at=report.started_at,
                ended_at=None,
                duration_s=0,
                cost=0.0,
                metadata={},
                created_at=now,
                updated_at=now,
            )
        call.status = report.status
        call.started_at = report.started_at
        call.ended_at = now
        call.duration_s = report.duration_s
        call.cost = round(report.duration_s / 60 * self.usd_per_minute, 6)
        call.caller = call.caller or report.caller
        call.called = call.called or report.called
        if call.customer_id is None and customer is not None:
            call.customer_id = customer.id
        call.metadata = {
            **call.metadata,
            **report.raw_metadata,
            "transcript": report.transcript,
        }
        call.updated_at = now
        saved = await self.calls.save(call)
        logger.info(
            "call_finished",
            extra={
                "call_id": report.call_id,
                "duration_s": report.duration_s,
                "status": report.status,
                "estimated_cost": call.cost,
            },
        )
        return saved

    async def _touch_call(self, turn: CallTurn, customer_id: UUID | None) -> None:
        call = await self.calls.get_by_provider_id(self.provider, turn.call_id or "")
        now = utcnow()
        if call is None:
            call = VoiceCall(
                id=uuid4(),
                provider=self.provider,
                provider_call_id=turn.call_id or "",
                customer_id=customer_id,
                caller=turn.caller,
                called=turn.called,
                status=CallStatus.started,
                started_at=now,
                ended_at=None,
                duration_s=0,
                cost=0.0,
                metadata={},
                created_at=now,
                updated_at=now,
            )
        elif call.customer_id == customer_id or customer_id is None:
            return
        else:
            call.customer_id = customer_id
            call.updated_at = now
        await self.calls.save(call)

    async def _known_customer(self, caller: str | None) -> Customer | None:
        phone = phone_from_id(caller) if caller else None
        if phone is None:
            return None
        return await self.customers.get_by_phone(phone)

    async def _last_question(self, customer: Customer) -> str | None:
        history = await self.messages.list_for_customer(customer.id, limit=20)
        for message in reversed(history):
            if message.role == MessageRole.user and message.text.strip():
                return message.text
        return None


def _caller_key(turn: CallTurn) -> str:
    """Phone is the customer key. A hidden number still gets a per-call card."""

    if turn.caller and phone_from_id(turn.caller):
        return turn.caller
    return f"call:{turn.call_id or 'anonymous'}"


def _uuid(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None

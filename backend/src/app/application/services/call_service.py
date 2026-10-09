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
from app.domain.phrases import call_greeting, listening_phrase, manager_callback_phrase
from app.domain.ports import ConversationStore, CustomerStore, MessageStore, VoiceCallStore
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
        conversations: ConversationStore | None = None,
    ) -> None:
        self.agent = agent
        self.customers = customers
        self.messages = messages
        self.calls = calls
        self.provider = provider
        self.usd_per_minute = usd_per_minute
        self.conversations = conversations

    async def start(self, turn: CallTurn) -> CallGreeting:
        """Greet the caller. A known phone gets their last question back."""

        business = await self.agent.resolve_business(_uuid(turn.business_id), turn.called)
        customer = await self._known_customer(business.id, turn.caller)
        language = customer.language if customer and customer.language in ("ru", "ky") else "ru"
        last_question = await self._last_question(customer) if customer else None
        if turn.call_id:
            await self._touch_call(turn, customer.id if customer else None, business.id)
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
        business = await self.agent.resolve_business(_uuid(turn.business_id), turn.called)
        response = await self.agent.process_message(
            InboundMessage(
                channel=Channel.voice,
                external_user_id=_caller_key(turn),
                text=turn.text,
                business_id=business.id,
                message_id=turn.message_id,
                metadata={"provider": self.provider, "call_id": turn.call_id},
            )
        )
        if turn.call_id:
            await self._touch_call(turn, response.customer_id, business.id, getattr(response, "conversation_id", None))
        if getattr(response, "duplicate", False) and not response.response_text.strip():
            # A resend of a turn still being answered: not a manager takeover.
            return CallReply(listening_phrase(response.language), response.language, False)
        if not getattr(response, "send_reply", True) or not response.response_text.strip():
            # A manager took the dialog but is not on this call. Silence on a
            # phone line sounds like a dropped call.
            return CallReply(manager_callback_phrase(response.language), response.language, True)
        return CallReply(response.response_text, response.language, response.handoff_required)

    async def finish(self, report: CallReport) -> VoiceCall:
        """Store duration and cost after hang-up. Repeated webhooks update the same row."""

        now = utcnow()
        call = await self.calls.get_by_provider_id(self.provider, report.call_id)
        # The business is already on the call row from its first turn; the
        # dialled number is only a fallback for a call that never reached us.
        business = await self.agent.resolve_business(call.business_id if call else None, report.called)
        customer = await self._known_customer(business.id, report.caller)
        if call is None:
            call = VoiceCall(
                id=uuid4(),
                provider=self.provider,
                provider_call_id=report.call_id,
                business_id=business.id,
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
        call.business_id = call.business_id or business.id
        call.metadata = {
            **call.metadata,
            **report.raw_metadata,
            "transcript": report.transcript,
        }
        call.updated_at = now
        saved = await self.calls.save(call)
        await self._end_conversation(call)
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

    async def _end_conversation(self, call: VoiceCall) -> None:
        """One call, one dialog: the next call starts fresh, memory stays on the customer.

        This also lifts a manager pause left on the finished call, so a later
        call is not answered with "a manager will call you back" forever.
        """

        raw = call.metadata.get("conversation_id")
        if self.conversations is None or not raw:
            return
        try:
            await self.conversations.end(UUID(str(raw)))
        except ValueError:
            return

    async def _touch_call(
        self,
        turn: CallTurn,
        customer_id: UUID | None,
        business_id: UUID | None = None,
        conversation_id: UUID | None = None,
    ) -> None:
        call = await self.calls.get_by_provider_id(self.provider, turn.call_id or "")
        now = utcnow()
        if call is None:
            call = VoiceCall(
                id=uuid4(),
                provider=self.provider,
                provider_call_id=turn.call_id or "",
                business_id=business_id,
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
        else:
            changed = False
            if customer_id is not None and call.customer_id != customer_id:
                call.customer_id = customer_id
                changed = True
            if business_id is not None and call.business_id is None:
                call.business_id = business_id
                changed = True
            if conversation_id is not None and call.metadata.get("conversation_id") != str(conversation_id):
                call.metadata = {**call.metadata, "conversation_id": str(conversation_id)}
                changed = True
            if not changed:
                return
            call.updated_at = now
        if conversation_id is not None:
            call.metadata = {**call.metadata, "conversation_id": str(conversation_id)}
        await self.calls.save(call)

    async def _known_customer(self, business_id: UUID, caller: str | None) -> Customer | None:
        phone = phone_from_id(caller) if caller else None
        if phone is None:
            return None
        return await self.customers.get_by_phone(business_id, phone)

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

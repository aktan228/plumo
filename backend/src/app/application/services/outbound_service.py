"""Replies waiting for delivery. One reply = one outbound record = one history message.

The browser never talks to Telegram or Meta. A manager's message is accepted
here in one transaction (history message + delivery record + job); the worker
sends it. The same client idempotency key returns the same operation.
"""

import logging
from datetime import timedelta
from uuid import UUID, uuid4

from app.domain.enums import (
    ConnectionStatus,
    ConversationMode,
    JobKind,
    MessageRole,
    OutboundStatus,
)
from app.domain.errors import (
    ChannelLimit,
    ConversationNotFound,
    InvalidMessage,
    InvalidState,
    ModeConflict,
    OutboundNotFound,
)
from app.domain.models import AgentResponse, ChannelConnection, Conversation, Message, OutboundMessage, utcnow
from app.infrastructure.channels.base import fits

logger = logging.getLogger("plumo.outbound")

# Meta: "Your app has 24 hours to respond to any message sent from an Instagram user".
INSTAGRAM_WINDOW = timedelta(hours=24)
SEND_MAX_ATTEMPTS = 4


def ordering_key(conversation_id: UUID) -> str:
    return f"out:{conversation_id}"


class OutboundService:
    def __init__(self, *, conversations, messages, outbound, connections, jobs) -> None:
        self.conversations = conversations
        self.messages = messages
        self.outbound = outbound
        self.connections = connections
        self.jobs = jobs

    async def queue_agent_reply(
        self, response: AgentResponse, conversation: Conversation, idempotency_key: str
    ) -> OutboundMessage | None:
        """Delivery record and job for the agent's stored reply, in the worker's transaction."""

        if not response.send_reply or not response.response_text or response.reply_message_id is None:
            return None
        if conversation.connection_id is None:
            return None
        now = utcnow()
        outbound = OutboundMessage(
            id=uuid4(),
            business_id=conversation.business_id,
            conversation_id=conversation.id,
            connection_id=conversation.connection_id,
            message_id=response.reply_message_id,
            author_role=MessageRole.assistant,
            text=response.response_text,
            idempotency_key=idempotency_key,
            mode_version=response.mode_version if response.mode_version is not None else conversation.mode_version,
            status=OutboundStatus.queued,
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        if not await self.outbound.add(outbound):
            return await self.outbound.get_by_key(conversation.business_id, idempotency_key)
        await self.jobs.enqueue(
            kind=JobKind.send_outbound,
            business_id=conversation.business_id,
            ordering_key=ordering_key(conversation.id),
            outbound_message_id=outbound.id,
            max_attempts=SEND_MAX_ATTEMPTS,
        )
        return outbound

    async def queue_manager_message(
        self,
        *,
        conversation_id: UUID,
        business_id: UUID,
        operator_id: UUID,
        operator_name: str,
        text: str,
        idempotency_key: str,
    ) -> tuple[OutboundMessage, bool]:
        """Accept a manager's message. Returns (operation, created). A repeated key returns the first one."""

        key = f"manager:{idempotency_key.strip()}"
        if len(idempotency_key.strip()) < 8:
            raise InvalidMessage("idempotency_key is required")
        # The dialog lock serializes double clicks and races with a return to the agent.
        conversation = await self.conversations.lock(conversation_id)
        if conversation is None or conversation.business_id != business_id:
            raise ConversationNotFound(f"conversation {conversation_id} was not found")
        existing = await self.outbound.get_by_key(business_id, key)
        if existing is not None:
            if existing.conversation_id != conversation.id:
                raise InvalidState("idempotency key was used for another dialog", code="idempotency_key_reused")
            return existing, False
        if conversation.mode != ConversationMode.human:
            raise ModeConflict("take the dialog before replying: the agent answers it now")
        body = text.strip()
        if not body:
            raise InvalidMessage("text is empty")
        connection = await self._sendable_connection(conversation)
        if not fits(conversation.channel, body):
            limit = "1000 bytes" if conversation.channel == "instagram" else "4096 characters"
            raise ChannelLimit(f"text is longer than the channel allows ({limit})", code="text_too_long")
        await self.check_window(conversation)

        now = utcnow()
        message = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            customer_id=conversation.customer_id,
            role=MessageRole.manager,
            text=body,
            timestamp=now,
            metadata={"author": operator_name[:100]} if operator_name else {},
            created_at=now,
        )
        await self.messages.add(message)
        outbound = OutboundMessage(
            id=uuid4(),
            business_id=business_id,
            conversation_id=conversation.id,
            connection_id=connection.id,
            message_id=message.id,
            author_role=MessageRole.manager,
            text=body,
            idempotency_key=key,
            mode_version=conversation.mode_version,
            status=OutboundStatus.queued,
            attempts=0,
            created_at=now,
            updated_at=now,
            operator_id=operator_id,
        )
        await self.outbound.add(outbound)
        await self.jobs.enqueue(
            kind=JobKind.send_outbound,
            business_id=business_id,
            ordering_key=ordering_key(conversation.id),
            outbound_message_id=outbound.id,
            max_attempts=SEND_MAX_ATTEMPTS,
        )
        return outbound, True

    async def resolve(self, outbound_id: UUID, business_id: UUID, action: str) -> OutboundMessage:
        """Manual decision on a failed or unknown delivery.

        mark_sent / mark_failed record what the manager saw in the channel.
        retry queues the same text again: only for a manager message, only in
        `human` mode, and only after a person decided the first try did not arrive.
        """

        outbound = await self.outbound.get(outbound_id)
        if outbound is None or outbound.business_id != business_id:
            raise OutboundNotFound(f"outbound {outbound_id} was not found")
        conversation = await self.conversations.lock(outbound.conversation_id)
        outbound = await self.outbound.lock(outbound_id)
        if outbound.status not in (OutboundStatus.failed, OutboundStatus.unknown):
            raise InvalidState(f"delivery is {outbound.status}; nothing to resolve", code="delivery_not_resolvable")
        now = utcnow()
        if action == "mark_sent":
            if outbound.status != OutboundStatus.unknown:
                raise InvalidState("only an unknown delivery can be marked as sent", code="delivery_not_resolvable")
            outbound.status = OutboundStatus.sent
            outbound.sent_at = outbound.sent_at or now
            outbound.error_code = "confirmed_by_operator"
        elif action == "mark_failed":
            outbound.status = OutboundStatus.failed
            outbound.error_code = outbound.error_code or "marked_failed"
        elif action == "retry":
            if outbound.author_role != MessageRole.manager:
                raise InvalidState("only a manager message can be sent again", code="delivery_not_resolvable")
            if conversation.mode != ConversationMode.human:
                raise ModeConflict("the dialog is with the agent now; take it to send again")
            await self._sendable_connection(conversation)
            await self.check_window(conversation)
            outbound.status = OutboundStatus.queued
            outbound.error_code = None
            outbound.error_message = None
            outbound.mode_version = conversation.mode_version
            await self.jobs.enqueue(
                kind=JobKind.send_outbound,
                business_id=business_id,
                ordering_key=ordering_key(conversation.id),
                outbound_message_id=outbound.id,
                max_attempts=SEND_MAX_ATTEMPTS,
            )
        else:
            raise InvalidMessage("action must be retry, mark_sent or mark_failed")
        return await self.outbound.save(outbound)

    async def _sendable_connection(self, conversation: Conversation) -> ChannelConnection:
        if conversation.connection_id is None:
            raise ChannelLimit("this dialog has no connected channel to reply through", code="channel_not_connected")
        connection = await self.connections.get(conversation.connection_id)
        if connection is None or connection.status == ConnectionStatus.disconnected:
            raise ChannelLimit("the channel is disconnected", code="channel_disconnected")
        if connection.status == ConnectionStatus.action_required:
            raise ChannelLimit("the channel needs attention in Integrations", code="channel_action_required")
        return connection

    async def check_window(self, conversation: Conversation) -> None:
        if conversation.channel != "instagram":
            return
        last = await self.last_customer_message_at(conversation.id)
        if last is None or utcnow() - last > INSTAGRAM_WINDOW:
            raise ChannelLimit(
                "Instagram allows a reply only within 24 hours of the customer's last message",
                code="window_closed",
            )

    async def last_customer_message_at(self, conversation_id: UUID):
        return await self.messages.last_timestamp(conversation_id, MessageRole.user)

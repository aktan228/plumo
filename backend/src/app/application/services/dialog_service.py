"""Who answers a dialog: take it from the agent, give it back.

Every switch runs under the dialog row lock and bumps `mode_version`. Delivery
takes the same lock and compares the version before it starts sending, so:

- after a takeover commits, no agent reply can start sending in that dialog;
- after a return to the agent, no manager message prepared earlier is sent.

A reply already handed to the provider cannot be called back; that limit is
documented, not hidden.
"""

import logging
from uuid import UUID, uuid4

from app.domain.enums import ConversationMode, HandoffPriority, HandoffStatus, MessageRole
from app.domain.errors import ConversationNotFound, HandoffNotFound
from app.domain.models import Conversation, HandoffRequest, Message, utcnow

logger = logging.getLogger("plumo.dialogs")

_EVENT_TEXT = {
    "takeover": "Менеджер взял диалог",
    "resume": "Диалог возвращён агенту",
}


class DialogService:
    def __init__(self, conversations, handoffs, messages, outbound) -> None:
        self.conversations = conversations
        self.handoffs = handoffs
        self.messages = messages
        self.outbound = outbound

    async def takeover(self, conversation_id: UUID, business_id: UUID, operator_name: str = "") -> Conversation:
        """Manager takes the dialog, with or without a handoff the agent asked for. Idempotent."""

        conversation = await self._locked(conversation_id, business_id)
        if conversation.mode == ConversationMode.human:
            return conversation
        now = utcnow()
        open_ = await self.handoffs.list_open(conversation.id)
        if open_:
            for item in open_:
                if item.status == HandoffStatus.pending:
                    item.status = HandoffStatus.accepted
                    item.updated_at = now
                    await self.handoffs.save(item)
        else:
            await self.handoffs.add(
                HandoffRequest(
                    id=uuid4(),
                    customer_id=conversation.customer_id,
                    conversation_id=conversation.id,
                    reason="manager_takeover",
                    priority=HandoffPriority.normal,
                    summary="Менеджер взял диалог из кабинета",
                    recent_messages=[],
                    status=HandoffStatus.accepted,
                    created_at=now,
                    updated_at=now,
                )
            )
        conversation = await self.conversations.set_mode(conversation.id, ConversationMode.human)
        cancelled = await self.outbound.cancel_queued(conversation.id, MessageRole.assistant, "mode_changed")
        await self._event(conversation, "takeover", operator_name)
        logger.info(
            "dialog_takeover",
            extra={"conversation_id": str(conversation.id), "cancelled_agent_replies": cancelled},
        )
        return conversation

    async def resume(self, conversation_id: UUID, business_id: UUID, operator_name: str = "") -> Conversation:
        """Back to the agent: open handoffs resolved, pending manager messages cancelled. Idempotent."""

        conversation = await self._locked(conversation_id, business_id)
        if conversation.mode == ConversationMode.ai:
            return conversation
        now = utcnow()
        for item in await self.handoffs.list_open(conversation.id):
            item.status = HandoffStatus.resolved
            item.updated_at = now
            await self.handoffs.save(item)
        conversation = await self.conversations.set_mode(conversation.id, ConversationMode.ai)
        cancelled = await self.outbound.cancel_queued(conversation.id, MessageRole.manager, "mode_changed")
        await self._event(conversation, "resume", operator_name)
        logger.info(
            "dialog_resumed",
            extra={"conversation_id": str(conversation.id), "cancelled_manager_messages": cancelled},
        )
        return conversation

    async def accept_handoff(self, handoff_id: UUID, business_id: UUID, operator_name: str = "") -> HandoffRequest:
        handoff = await self._handoff(handoff_id, business_id)
        await self.takeover(handoff.conversation_id, business_id, operator_name)
        return await self.handoffs.get(handoff.id)

    async def resolve_handoff(self, handoff_id: UUID, business_id: UUID, operator_name: str = "") -> HandoffRequest:
        """Close a handoff. If the manager owned the dialog through it, the agent gets it back."""

        handoff = await self._handoff(handoff_id, business_id)
        conversation = await self._locked(handoff.conversation_id, business_id)
        if conversation.mode == ConversationMode.human:
            await self.resume(conversation.id, business_id, operator_name)
        elif handoff.status in (HandoffStatus.pending, HandoffStatus.accepted):
            handoff.status = HandoffStatus.resolved
            handoff.updated_at = utcnow()
            await self.handoffs.save(handoff)
        return await self.handoffs.get(handoff.id)

    async def _locked(self, conversation_id: UUID, business_id: UUID) -> Conversation:
        conversation = await self.conversations.lock(conversation_id)
        if conversation is None or conversation.business_id != business_id:
            raise ConversationNotFound(f"conversation {conversation_id} was not found")
        return conversation

    async def _handoff(self, handoff_id: UUID, business_id: UUID) -> HandoffRequest:
        handoff = await self.handoffs.get(handoff_id)
        if handoff is None:
            raise HandoffNotFound(f"handoff {handoff_id} was not found")
        conversation = await self.conversations.get(handoff.conversation_id)
        if conversation is None or conversation.business_id != business_id:
            raise HandoffNotFound(f"handoff {handoff_id} was not found")
        return handoff

    async def _event(self, conversation: Conversation, event: str, operator_name: str) -> None:
        now = utcnow()
        metadata = {"event": event, "mode_version": conversation.mode_version}
        if operator_name:
            metadata["operator"] = operator_name[:100]
        await self.messages.add(
            Message(
                id=uuid4(),
                conversation_id=conversation.id,
                customer_id=conversation.customer_id,
                role=MessageRole.system,
                text=_EVENT_TEXT[event],
                timestamp=now,
                metadata=metadata,
                created_at=now,
            )
        )

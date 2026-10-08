"""Customer card and dialog history."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query

from app.api.deps import Services, get_services
from app.api.mappers import conversation_out, customer_out, message_out, summary_out
from app.api.schemas import ConversationDetailOut, CustomerOut, HistoryOut, ManagerMessageIn, MessageOut
from app.domain.enums import MessageRole
from app.domain.errors import ConversationNotFound, CustomerNotFound
from app.domain.models import Message, utcnow
from app.infrastructure.database.repositories import SummaryRepository

router = APIRouter(tags=["customers"])


@router.get("/customers/{customer_id}", response_model=CustomerOut, summary="Карточка клиента")
async def get_customer(customer_id: UUID, services: Services = Depends(get_services)) -> CustomerOut:
    customer = await services.customers.get(customer_id)
    if customer is None:
        raise CustomerNotFound(f"customer {customer_id} was not found")
    return customer_out(customer)


@router.get(
    "/customers/{customer_id}/history",
    response_model=HistoryOut,
    summary="История клиента по всем каналам",
)
async def get_history(
    customer_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    services: Services = Depends(get_services),
) -> HistoryOut:
    customer = await services.customers.get(customer_id)
    if customer is None:
        raise CustomerNotFound(f"customer {customer_id} was not found")
    stored_summary = await SummaryRepository(services.session).get(customer_id)
    conversations = await services.conversations.list_for_customer(customer_id)
    messages = await services.messages.list_for_customer(customer_id, limit=limit)
    return HistoryOut(
        customer=customer_out(customer),
        summary=summary_out(stored_summary) if stored_summary else None,
        conversations=[conversation_out(item) for item in conversations],
        messages=[message_out(item) for item in messages],
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut, summary="Один диалог")
async def get_conversation(
    conversation_id: UUID, services: Services = Depends(get_services)
) -> ConversationDetailOut:
    conversation = await services.conversations.get(conversation_id)
    if conversation is None:
        raise ConversationNotFound(f"conversation {conversation_id} was not found")
    messages = await services.messages.list_for_conversation(conversation_id)
    return ConversationDetailOut(
        conversation=conversation_out(conversation),
        messages=[message_out(item) for item in messages],
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    summary="Сообщение менеджера в диалог (агент молчит, пока передача ACCEPTED)",
)
async def post_manager_message(
    conversation_id: UUID, body: ManagerMessageIn, services: Services = Depends(get_services)
) -> MessageOut:
    """Store what the manager sent, so history and the next agent turn see it.

    Delivery to WhatsApp/Telegram stays with the channel adapter: it sends
    `text` to the customer and calls this endpoint to record it.
    """

    conversation = await services.conversations.get(conversation_id)
    if conversation is None:
        raise ConversationNotFound(f"conversation {conversation_id} was not found")
    now = utcnow()
    message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
        role=MessageRole.manager,
        text=body.text.strip(),
        timestamp=now,
        metadata={"author": body.author} if body.author else {},
        created_at=now,
    )
    return message_out(await services.messages.add(message))

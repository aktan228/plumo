"""Customer card and dialog history."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import Services, get_services
from app.api.mappers import conversation_out, customer_out, message_out, summary_out
from app.api.schemas import ConversationDetailOut, CustomerOut, HistoryOut
from app.domain.errors import ConversationNotFound, CustomerNotFound
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

"""Customer card and history, limited to the signed-in operator's business."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import Services, current_operator, get_services
from app.api.mappers import conversation_out, customer_out, message_out, summary_out
from app.api.schemas import CustomerOut, HistoryOut
from app.application.services.auth_service import OperatorContext
from app.domain.errors import CustomerNotFound
from app.infrastructure.database.repositories import SummaryRepository

router = APIRouter(tags=["customers"])


async def _customer(services: Services, operator: OperatorContext, customer_id: UUID):
    customer = await services.customers.get(customer_id)
    # Another business's customer is answered exactly like a missing one.
    if customer is None or customer.business_id != operator.business_id:
        raise CustomerNotFound(f"customer {customer_id} was not found")
    return customer


@router.get("/customers/{customer_id}", response_model=CustomerOut, summary="Карточка клиента")
async def get_customer(
    customer_id: UUID,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> CustomerOut:
    return customer_out(await _customer(services, operator, customer_id))


@router.get(
    "/customers/{customer_id}/history",
    response_model=HistoryOut,
    summary="История клиента по всем каналам",
)
async def get_history(
    customer_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> HistoryOut:
    customer = await _customer(services, operator, customer_id)
    stored_summary = await SummaryRepository(services.session).get(customer_id)
    conversations = await services.conversations.list_for_customer(customer_id)
    messages = await services.messages.list_for_customer(customer_id, limit=limit)
    return HistoryOut(
        customer=customer_out(customer),
        summary=summary_out(stored_summary) if stored_summary else None,
        conversations=[conversation_out(item) for item in conversations],
        messages=[message_out(item) for item in messages],
    )

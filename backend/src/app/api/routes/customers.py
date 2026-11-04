"""Customer card and history, limited to the signed-in operator's business."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import Services, current_operator, get_services
from app.api.mappers import conversation_out, customer_out, message_out, summary_out
from app.api.schemas import CustomerCardOut, CustomerListOut, HistoryOut
from app.application.services.auth_service import OperatorContext
from app.domain.errors import CustomerNotFound
from app.infrastructure.database.repositories import SummaryRepository
from app.infrastructure.database.customer_queries import customer_page

router = APIRouter(tags=["customers"])


@router.get("/customers", response_model=CustomerListOut, summary="Клиенты своего бизнеса: поиск, канал, курсор")
async def list_customers(
    q: str | None = Query(default=None, max_length=100),
    channel: str | None = Query(default=None, max_length=32),
    cursor: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=30, ge=1, le=100),
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> CustomerListOut:
    return await customer_page(services.session, operator.business_id, q=q, channel=channel, cursor=cursor, limit=limit)


async def _customer(services: Services, operator: OperatorContext, customer_id: UUID):
    customer = await services.customers.get(customer_id)
    # Another business's customer is answered exactly like a missing one.
    if customer is None or customer.business_id != operator.business_id:
        raise CustomerNotFound(f"customer {customer_id} was not found")
    return customer


@router.get("/customers/{customer_id}", response_model=CustomerCardOut, summary="Карточка клиента")
async def get_customer(
    customer_id: UUID,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> CustomerCardOut:
    customer = await _customer(services, operator, customer_id)
    page = await customer_page(services.session, operator.business_id, customer_id=customer_id, limit=1)
    contact = page["items"][0] if page["items"] else {}
    return CustomerCardOut(**customer_out(customer).model_dump(), name=contact.get("name"),
                           handle=contact.get("handle"), channels=contact.get("channels", []))


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
    conversations = await services.conversations.list_for_customer(customer_id, business_id=operator.business_id)
    messages = await services.messages.list_for_customer(customer_id, limit=limit, business_id=operator.business_id)
    return HistoryOut(
        customer=customer_out(customer),
        summary=summary_out(stored_summary) if stored_summary else None,
        conversations=[conversation_out(item) for item in conversations],
        messages=[message_out(item) for item in messages],
    )

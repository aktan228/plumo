"""Handoffs, knowledge, meetings and metrics of the signed-in operator's business."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query

from app.api.deps import Services, current_operator, get_services
from app.api.mappers import handoff_out, knowledge_out, meeting_out, metrics_out
from app.api.schemas import HandoffOut, KnowledgeIn, KnowledgeOut, MeetingIn, MeetingOut, MetricsOut
from app.application.services.auth_service import OperatorContext
from app.domain.errors import BusinessNotFound, CustomerNotFound
from app.domain.models import KnowledgeItem, utcnow

router = APIRouter(tags=["operations"])


@router.get("/handoffs", response_model=list[HandoffOut], summary="Очередь передачи человеку")
async def list_handoffs(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> list[HandoffOut]:
    rows = await services.handoff_requests.list_requests(status, limit, business_id=operator.business_id)
    return [handoff_out(item) for item in rows]


@router.post("/handoffs/{handoff_id}/accept", response_model=HandoffOut, summary="Взять диалог по передаче")
async def accept_handoff(
    handoff_id: UUID,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> HandoffOut:
    handoff = await services.dialogs.accept_handoff(
        handoff_id, operator.business_id, operator.display_name or operator.email
    )
    await services.session.commit()
    return handoff_out(handoff)


@router.post("/handoffs/{handoff_id}/resolve", response_model=HandoffOut, summary="Закрыть передачу")
async def resolve_handoff(
    handoff_id: UUID,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> HandoffOut:
    handoff = await services.dialogs.resolve_handoff(
        handoff_id, operator.business_id, operator.display_name or operator.email
    )
    await services.session.commit()
    return handoff_out(handoff)


@router.get("/knowledge", response_model=list[KnowledgeOut], summary="База знаний")
async def list_knowledge(
    business_id: UUID | None = None,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> list[KnowledgeOut]:
    _same_business(operator, business_id)
    rows = await services.knowledge.list_items(operator.business_id)
    return [knowledge_out(item) for item in rows]


@router.post("/knowledge", response_model=KnowledgeOut, summary="Добавить факт в базу знаний")
async def create_knowledge(
    body: KnowledgeIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> KnowledgeOut:
    _same_business(operator, body.business_id)
    now = utcnow()
    item = KnowledgeItem(
        id=uuid4(),
        business_id=operator.business_id,
        category=body.category.strip(),
        title=body.title.strip(),
        content=body.content.strip(),
        metadata=body.metadata,
        active=body.active,
        created_at=now,
        updated_at=now,
    )
    await services.knowledge.add(item)
    return knowledge_out(item)


@router.post("/meetings", response_model=MeetingOut, summary="Создать встречу")
async def create_meeting(
    body: MeetingIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> MeetingOut:
    _same_business(operator, body.business_id)
    customer = await services.customers.get(body.customer_id)
    if customer is None or customer.business_id != operator.business_id:
        raise CustomerNotFound(f"customer {body.customer_id} was not found")
    payload = {}
    if body.datetime is not None:
        payload["datetime"] = body.datetime.isoformat()
    if body.date:
        payload["date"] = body.date
    if body.time:
        payload["time"] = body.time
    meeting = await services.meetings.schedule(
        customer_id=body.customer_id,
        business_id=operator.business_id,
        text=body.text,
        payload=payload,
        notes=body.notes,
    )
    return meeting_out(meeting)


@router.get("/metrics", response_model=MetricsOut, summary="Сводка по диалогам бизнеса")
async def get_metrics(
    business_id: UUID | None = None,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> MetricsOut:
    _same_business(operator, business_id)
    return metrics_out(await services.metrics.snapshot(operator.business_id))


def _same_business(operator: OperatorContext, requested: UUID | None) -> None:
    """A business id in the request may only repeat the operator's own; another one looks missing."""

    if requested is not None and requested != operator.business_id:
        raise BusinessNotFound(f"business {requested} was not found")

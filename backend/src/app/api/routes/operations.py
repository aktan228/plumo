"""Handoffs, knowledge, meetings and metrics."""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query

from app.api.deps import Services, get_services
from app.api.mappers import handoff_out, knowledge_out, meeting_out, metrics_out
from app.api.schemas import HandoffOut, KnowledgeIn, KnowledgeOut, MeetingIn, MeetingOut, MetricsOut
from app.domain.errors import BusinessNotFound, CustomerNotFound
from app.domain.models import KnowledgeItem, utcnow

router = APIRouter(tags=["operations"])


@router.get("/handoffs", response_model=list[HandoffOut], summary="Очередь передачи человеку")
async def list_handoffs(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    services: Services = Depends(get_services),
) -> list[HandoffOut]:
    rows = await services.handoffs.list_requests(status, limit)
    return [handoff_out(item) for item in rows]


@router.post("/handoffs/{handoff_id}/accept", response_model=HandoffOut, summary="Взять диалог")
async def accept_handoff(handoff_id: UUID, services: Services = Depends(get_services)) -> HandoffOut:
    return handoff_out(await services.handoffs.accept(handoff_id))


@router.post("/handoffs/{handoff_id}/resolve", response_model=HandoffOut, summary="Закрыть передачу")
async def resolve_handoff(handoff_id: UUID, services: Services = Depends(get_services)) -> HandoffOut:
    return handoff_out(await services.handoffs.resolve(handoff_id))


@router.get("/knowledge", response_model=list[KnowledgeOut], summary="База знаний")
async def list_knowledge(
    business_id: UUID | None = None,
    services: Services = Depends(get_services),
) -> list[KnowledgeOut]:
    rows = await services.knowledge.list_items(business_id)
    return [knowledge_out(item) for item in rows]


@router.post("/knowledge", response_model=KnowledgeOut, summary="Добавить факт в базу знаний")
async def create_knowledge(body: KnowledgeIn, services: Services = Depends(get_services)) -> KnowledgeOut:
    business_id = await _business_id(services, body.business_id)
    now = utcnow()
    item = KnowledgeItem(
        id=uuid4(),
        business_id=business_id,
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
async def create_meeting(body: MeetingIn, services: Services = Depends(get_services)) -> MeetingOut:
    customer = await services.customers.get(body.customer_id)
    if customer is None:
        raise CustomerNotFound(f"customer {body.customer_id} was not found")
    business_id = await _business_id(services, body.business_id)
    payload = {}
    if body.datetime is not None:
        payload["datetime"] = body.datetime.isoformat()
    if body.date:
        payload["date"] = body.date
    if body.time:
        payload["time"] = body.time
    meeting = await services.meetings.schedule(
        customer_id=body.customer_id,
        business_id=business_id,
        text=body.text,
        payload=payload,
        notes=body.notes,
    )
    return meeting_out(meeting)


@router.get("/metrics", response_model=MetricsOut, summary="Сводка по диалогам (по одному бизнесу, если указан business_id)")
async def get_metrics(business_id: UUID | None = None, services: Services = Depends(get_services)) -> MetricsOut:
    return metrics_out(await services.metrics.snapshot(business_id))


async def _business_id(services: Services, explicit: UUID | None) -> UUID:
    if explicit is not None:
        business = await services.businesses.get(explicit)
        if business is None:
            raise BusinessNotFound(f"business {explicit} was not found")
        return business.id
    configured = services.runtime.settings.default_business_id
    if configured:
        business = await services.businesses.get(UUID(configured))
        if business is None:
            raise BusinessNotFound("configured business was not found")
        return business.id
    rows = await services.businesses.list_all()
    if len(rows) == 1:
        return rows[0].id
    raise BusinessNotFound("business_id is required")

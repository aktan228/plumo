"""Inbound messages and mock channel events."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends

from app.api.deps import Services, get_services
from app.api.mappers import agent_out
from app.api.schemas import AgentResponseOut, ChannelEventOut, MessageIn
from app.correlation import get_correlation_id, get_request_id
from app.domain.models import InboundMessage

router = APIRouter(tags=["messages"])


@router.post(
    "/messages",
    response_model=AgentResponseOut,
    summary="Обработать нормализованное сообщение",
    responses={
        422: {"description": "Пустой текст или неизвестный канал"},
        404: {"description": "Бизнес или клиент не найден"},
        503: {"description": "Провайдер модели не зарегистрирован"},
    },
)
async def post_message(body: MessageIn, services: Services = Depends(get_services)) -> AgentResponseOut:
    message = InboundMessage(
        channel=body.channel,
        external_user_id=body.external_user_id,
        text=body.text,
        message_id=body.message_id,
        customer_id=body.customer_id,
        timestamp=body.timestamp,
        language_hint=body.language_hint,
        metadata=body.metadata,
        business_id=body.business_id,
        correlation_id=get_correlation_id() or None,
        request_id=get_request_id() or None,
    )
    return agent_out(await services.agent.process_message(message))


@router.post(
    "/channels/{channel}/events",
    response_model=ChannelEventOut,
    summary="Принять сырое событие канала и нормализовать его",
    responses={503: {"description": "Адаптер канала не зарегистрирован"}},
)
async def post_channel_event(
    channel: str,
    event: dict = Body(
        ...,
        examples=[
            {
                "from": "+996555123456",
                "id": "wamid.1",
                "text": "Еще продается квартира за 85000?",
            }
        ],
    ),
    services: Services = Depends(get_services),
) -> ChannelEventOut:
    payload = await services.channels.execute(channel, event)
    return ChannelEventOut(
        channel=payload["channel"],
        text=payload["text"],
        external_user_id=payload["external_user_id"],
        customer_id=UUID(payload["customer_id"]),
        conversation_id=UUID(payload["conversation_id"]),
        handoff_required=payload["handoff_required"],
        handoff_reason=payload.get("handoff_reason"),
        route=payload["route"],
        route_reason=payload["route_reason"],
        model_used=payload["model_used"],
        correlation_id=payload.get("correlation_id"),
    )

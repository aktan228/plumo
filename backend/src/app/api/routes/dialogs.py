"""Dialogs of the operator's business: list, history, takeover, return to the agent, manager replies."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.dashboard_mappers import (
    connection_brief_out,
    delivery_out,
    dialog_item_out,
    dialog_message_out,
    dialog_mode,
)
from app.api.dashboard_schemas import (
    DeliveryOut,
    DialogDetailOut,
    DialogListOut,
    DialogMessagesOut,
    DialogStateOut,
    ManagerSendIn,
    ManagerSendOut,
    ReadIn,
    ReadOut,
    ReplyStateOut,
    ResolveDeliveryIn,
)
from app.api.deps import Services, current_operator, get_services
from app.api.mappers import customer_out, handoff_out, summary_out
from app.application.services.auth_service import OperatorContext
from app.application.services.outbound_service import INSTAGRAM_WINDOW
from app.domain.enums import ConnectionStatus, MessageRole
from app.domain.errors import ConversationNotFound, CustomerNotFound, OutboundNotFound
from app.domain.models import utcnow
from app.infrastructure.channels.base import INSTAGRAM_TEXT_BYTES, TELEGRAM_TEXT_LIMIT
from app.infrastructure.database.models import MessageRow
from app.infrastructure.database.repositories import SummaryRepository

router = APIRouter(tags=["dialogs"])


@router.get("/conversations", response_model=DialogListOut, summary="Диалоги бизнеса: поиск, фильтры, курсор")
async def list_dialogs(
    channel: str | None = Query(default=None, max_length=32),
    mode: str | None = Query(default=None, description="ai | waiting | human"),
    q: str | None = Query(default=None, max_length=100, description="Имя, контакт, телефон или текст сообщений"),
    cursor: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=30, ge=1, le=100),
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> DialogListOut:
    rows, next_cursor = await services.dialog_queries.list(
        business_id=operator.business_id,
        operator_id=operator.operator_id,
        channel=channel,
        mode=mode,
        query=q,
        cursor=cursor,
        limit=limit,
    )
    return DialogListOut(items=[dialog_item_out(row) for row in rows], next_cursor=next_cursor)


@router.get("/conversations/{conversation_id}", response_model=DialogDetailOut, summary="Диалог: история, карточка, режим")
async def get_dialog(
    conversation_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> DialogDetailOut:
    row = await _dialog(services, operator, conversation_id)
    messages, older = await services.dialog_queries.messages_page(conversation_id, limit=limit)
    customer = await services.customers.get(row.customer_id)
    if customer is None:
        raise CustomerNotFound("customer of the dialog disappeared")
    summary = await SummaryRepository(services.session).get(customer.id)
    open_handoffs = await services.handoff_requests.list_open(conversation_id)
    connection = await services.connections.get(row.connection_id) if row.connection_id else None
    return DialogDetailOut(
        dialog=dialog_item_out(row),
        messages=await _with_deliveries(services, messages),
        older_cursor=older,
        customer=customer_out(customer),
        summary=summary_out(summary) if summary else None,
        handoff=handoff_out(open_handoffs[-1]) if open_handoffs else None,
        connection=connection_brief_out(connection) if connection else None,
        reply=await _reply_state(services, row, connection),
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=DialogMessagesOut,
    summary="Более ранние сообщения диалога",
)
async def older_messages(
    conversation_id: UUID,
    before: str = Query(max_length=300),
    limit: int = Query(default=50, ge=1, le=200),
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> DialogMessagesOut:
    await _dialog(services, operator, conversation_id)
    messages, older = await services.dialog_queries.messages_page(conversation_id, before=before, limit=limit)
    return DialogMessagesOut(messages=await _with_deliveries(services, messages), older_cursor=older)


@router.post(
    "/conversations/{conversation_id}/takeover",
    response_model=DialogStateOut,
    summary="Взять диалог: агент замолкает, его неотправленные ответы отменяются",
)
async def takeover(
    conversation_id: UUID,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> DialogStateOut:
    conversation = await services.dialogs.takeover(
        conversation_id, operator.business_id, operator.display_name or operator.email
    )
    await services.session.commit()
    return DialogStateOut(id=conversation.id, mode="human", mode_version=conversation.mode_version)


@router.post(
    "/conversations/{conversation_id}/resume",
    response_model=DialogStateOut,
    summary="Вернуть агенту: передача закрыта, неотправленные сообщения менеджера отменяются",
)
async def resume(
    conversation_id: UUID,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> DialogStateOut:
    conversation = await services.dialogs.resume(
        conversation_id, operator.business_id, operator.display_name or operator.email
    )
    open_handoffs = await services.handoff_requests.list_open(conversation.id)
    await services.session.commit()
    return DialogStateOut(
        id=conversation.id,
        mode=dialog_mode(conversation.mode, any(item.status == "PENDING" for item in open_handoffs)),
        mode_version=conversation.mode_version,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ManagerSendOut,
    summary="Ответ менеджера: одна операция отправки в канал диалога",
    responses={
        409: {"description": "mode_conflict — диалог ведёт агент; idempotency_key_reused"},
        422: {"description": "text_too_long, window_closed, channel_not_connected, channel_disconnected"},
    },
)
async def send_manager_message(
    conversation_id: UUID,
    body: ManagerSendIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ManagerSendOut:
    outbound, created = await services.outbound.queue_manager_message(
        conversation_id=conversation_id,
        business_id=operator.business_id,
        operator_id=operator.operator_id,
        operator_name=operator.display_name or operator.email,
        text=body.text,
        idempotency_key=body.idempotency_key,
    )
    await services.session.commit()
    message = await services.messages.get(outbound.message_id) if outbound.message_id else None
    if message is None:
        raise ConversationNotFound("the message disappeared")
    return ManagerSendOut(
        message=dialog_message_out(message, outbound), delivery=delivery_out(outbound), created=created
    )


@router.post("/conversations/{conversation_id}/read", response_model=ReadOut, summary="Оператор прочитал до seq")
async def mark_read(
    conversation_id: UUID,
    body: ReadIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ReadOut:
    await _dialog(services, operator, conversation_id)
    newest = await services.session.scalar(
        select(func.max(MessageRow.seq)).where(MessageRow.conversation_id == conversation_id)
    )
    # A cursor beyond the newest stored message would hide messages that arrive later.
    seq = min(body.seq, int(newest or 0))
    last = await services.reads.advance(operator.operator_id, conversation_id, seq)
    await services.session.commit()
    row = await _dialog(services, operator, conversation_id)
    return ReadOut(last_read_seq=last, unread=int(row.unread or 0))


@router.get("/outbound-messages/{outbound_id}", response_model=DeliveryOut, summary="Статус отправки")
async def get_delivery(
    outbound_id: UUID,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> DeliveryOut:
    outbound = await services.outbound_messages.get(outbound_id)
    if outbound is None or outbound.business_id != operator.business_id:
        raise OutboundNotFound(f"outbound {outbound_id} was not found")
    return delivery_out(outbound)


@router.post(
    "/outbound-messages/{outbound_id}/resolve",
    response_model=DeliveryOut,
    summary="Решение по неуспешной или неизвестной отправке",
)
async def resolve_delivery(
    outbound_id: UUID,
    body: ResolveDeliveryIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> DeliveryOut:
    outbound = await services.outbound.resolve(outbound_id, operator.business_id, body.action)
    await services.session.commit()
    return delivery_out(outbound)


async def _dialog(services: Services, operator: OperatorContext, conversation_id: UUID):
    row = await services.dialog_queries.one(
        business_id=operator.business_id, operator_id=operator.operator_id, conversation_id=conversation_id
    )
    if row is None:
        raise ConversationNotFound(f"conversation {conversation_id} was not found")
    return row


async def _with_deliveries(services: Services, messages):
    ids = [item.id for item in messages if item.role in (MessageRole.assistant, MessageRole.manager)]
    deliveries = await services.outbound_messages.by_messages(ids)
    return [dialog_message_out(item, deliveries.get(item.id)) for item in messages]


async def _reply_state(services: Services, row, connection) -> ReplyStateOut:
    limits = (
        {"max_bytes": INSTAGRAM_TEXT_BYTES} if row.channel == "instagram" else {"max_chars": TELEGRAM_TEXT_LIMIT}
    )
    expires = None
    if row.channel == "instagram":
        last = await services.messages.last_timestamp(row.id, MessageRole.user)
        expires = last + INSTAGRAM_WINDOW if last else None
    reason = None
    if row.mode != "human":
        reason = "take_dialog_first"
    elif connection is None:
        reason = "channel_not_connected"
    elif connection.status == ConnectionStatus.disconnected:
        reason = "channel_disconnected"
    elif connection.status == ConnectionStatus.action_required:
        reason = "channel_action_required"
    elif row.channel == "instagram" and (expires is None or utcnow() > expires):
        reason = "window_closed"
    return ReplyStateOut(allowed=reason is None, reason=reason, window_expires_at=expires, **limits)

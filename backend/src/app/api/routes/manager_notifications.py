"""Who gets the business's handoff notifications in Telegram. The business comes from the session only."""

import asyncio
import logging

from fastapi import APIRouter, Depends

from app.api.dashboard_schemas import ManagerChatOut, ManagerConfirmOut, ManagerLinkOut, ManagerNotificationsOut
from app.api.deps import Services, current_operator, get_services
from app.application.services.auth_service import OperatorContext
from app.application.services.manager_recipients import (
    CONTROL_TEXT,
    START_PREFIX,
    ManagerRecipients,
    service_bot_token,
    service_bot_username,
    status_of,
)
from app.domain.errors import ProviderTransientError, ProviderUnavailable

logger = logging.getLogger("plumo.handoff")
router = APIRouter(prefix="/manager-notifications", tags=["manager-notifications"])

_ERRORS = {409: {"description": "Нет чата, ожидающего подтверждения (no_candidate)"}}


def _out(row, services: Services) -> dict:
    return {
        "status": status_of(row),
        "recipient": ManagerChatOut(label=row.chat_label or "", at=row.confirmed_at) if row and row.chat_id else None,
        "candidate": ManagerChatOut(label=row.candidate_label or "", at=row.candidate_seen_at)
        if row and row.candidate_chat_id
        else None,
        "attention": row.attention if row else None,
        "code_expires_at": row.code_expires_at if row and status_of(row) == "waiting_code" else None,
        "bot_username": service_bot_username(),
        "service_bot_configured": services.runtime.settings.handoff_provider != "telegram"
        or bool(service_bot_token()),
    }


@router.get("", response_model=ManagerNotificationsOut, summary="Получатель уведомлений менеджеру этого бизнеса")
async def get_recipient(
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ManagerNotificationsOut:
    row = await ManagerRecipients(services.session).get(operator.business_id)
    return ManagerNotificationsOut(**_out(row, services))


@router.post("/link", response_model=ManagerLinkOut, summary="Новый одноразовый код привязки (15 минут)")
async def issue_link(
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ManagerLinkOut:
    row, code = await ManagerRecipients(services.session).issue_code(operator.business_id)
    username = service_bot_username()
    return ManagerLinkOut(
        **_out(row, services),
        command=f"/start {START_PREFIX}{code}",
        link=f"https://t.me/{username}?start={START_PREFIX}{code}" if username else None,
    )


@router.post("/confirm", response_model=ManagerConfirmOut, summary="Подтвердить чат, приславший код", responses=_ERRORS)
async def confirm_recipient(
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ManagerConfirmOut:
    recipients = ManagerRecipients(services.session)
    row = await recipients.confirm(operator.business_id, operator.operator_id)
    chat_id = row.chat_id
    await services.session.commit()
    # The control message goes out after the commit: a confirmed chat stays confirmed if Telegram is down.
    try:
        async with asyncio.timeout(15):
            await services.runtime.handoff_provider.send_text(chat_id, CONTROL_TEXT)
        delivery = "sent"
    except (ProviderTransientError, TimeoutError):
        delivery = "failed"
    except ProviderUnavailable:
        delivery = "rejected"
        await recipients.mark(operator.business_id, chat_id, "delivery_rejected")
    if delivery != "sent":
        logger.warning("manager_control_message_failed", extra={"delivery": delivery})
    row = await recipients.get(operator.business_id)
    return ManagerConfirmOut(**_out(row, services), control_delivery=delivery)


@router.post("/disconnect", response_model=ManagerNotificationsOut, summary="Отключить уведомления менеджеру", responses={404: {"description": "Не настроено"}})
async def disconnect_recipient(
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ManagerNotificationsOut:
    await ManagerRecipients(services.session).disconnect(operator.business_id)
    return ManagerNotificationsOut(**_out(None, services))

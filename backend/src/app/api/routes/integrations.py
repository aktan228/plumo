"""Channel connections of the operator's business. Secrets never leave the server."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dashboard_mappers import connection_out
from app.api.dashboard_schemas import (
    ChannelIntegrationOut,
    ConnectIn,
    ConnectionOut,
    CredentialOut,
    IntegrationPatchIn,
    IntegrationsOut,
)
from app.api.deps import Services, current_operator, get_services
from app.application.services.auth_service import OperatorContext

router = APIRouter(prefix="/integrations", tags=["integrations"])

_ERRORS = {
    404: {"description": "Нет такой интеграции или серверной конфигурации у этого бизнеса"},
    409: {"description": "Конфликт: аккаунт у другого бизнеса, уже подключён другой, чужой webhook, версия"},
    422: {"description": "Токен недействителен или не хватает прав (invalid_credential, missing_permission)"},
    503: {"description": "Не настроен сервер (not_configured) или канал временно недоступен"},
}


@router.get("", response_model=IntegrationsOut, summary="Telegram и Instagram этого бизнеса")
async def list_integrations(
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> IntegrationsOut:
    rows = await services.integrations.overview(operator.business_id)
    return IntegrationsOut(
        channels=[
            ChannelIntegrationOut(
                channel=item.channel,
                status=item.status,
                connection=connection_out(item.connection) if item.connection else None,
                credentials=[CredentialOut(ref=ref, label=label) for ref, label in item.credentials],
                requirements=item.requirements,
                webhook_url=item.webhook_url,
            )
            for item in rows
        ],
        ai_mode=services.runtime.settings.ai_mode,
    )


@router.post(
    "/telegram/connect",
    response_model=ConnectionOut,
    summary="Проверить бота (getMe) и установить webhook",
    responses=_ERRORS,
)
async def connect_telegram(
    body: ConnectIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ConnectionOut:
    connection = await services.integrations.connect_telegram(
        operator.business_id, body.credential_ref, body.replace_webhook
    )
    return connection_out(connection)


@router.post(
    "/instagram/connect",
    response_model=ConnectionOut,
    summary="Проверить аккаунт Instagram и подписку на сообщения",
    responses=_ERRORS,
)
async def connect_instagram(
    body: ConnectIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ConnectionOut:
    connection = await services.integrations.connect_instagram(operator.business_id, body.credential_ref)
    return connection_out(connection)


@router.post("/{connection_id}/check", response_model=ConnectionOut, summary="Повторная проверка", responses=_ERRORS)
async def check_integration(
    connection_id: UUID,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ConnectionOut:
    return connection_out(await services.integrations.check(connection_id, operator.business_id))


@router.patch("/{connection_id}", response_model=ConnectionOut, summary="Включить или выключить ответы агента")
async def patch_integration(
    connection_id: UUID,
    body: IntegrationPatchIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ConnectionOut:
    connection = await services.integrations.set_agent(
        connection_id, operator.business_id, body.agent_enabled, body.version
    )
    return connection_out(connection)


@router.post("/{connection_id}/disconnect", response_model=ConnectionOut, summary="Отключить канал (история сохраняется)")
async def disconnect_integration(
    connection_id: UUID,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> ConnectionOut:
    return connection_out(await services.integrations.disconnect(connection_id, operator.business_id))

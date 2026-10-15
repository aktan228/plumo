"""Operator sign-in. Called by the dashboard's Next.js server, which keeps the token in an HttpOnly cookie."""

from fastapi import APIRouter, Depends, Request, Response

from app.api.dashboard_schemas import BusinessBriefOut, LoginIn, LoginOut, OperatorOut, SessionOut
from app.api.deps import Services, bearer_token, current_operator, get_services
from app.application.services.auth_service import OperatorContext
from app.domain.errors import NotAuthenticated

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=LoginOut,
    summary="Вход оператора (только для сервера Next.js)",
    responses={401: {"description": "Неверный email или пароль"}, 429: {"description": "Слишком много попыток"}},
)
async def login(body: LoginIn, services: Services = Depends(get_services)) -> LoginOut:
    result = await services.auth.login(body.email, body.password)
    business = await services.businesses.get(result.operator.business_id)
    if business is None:
        raise NotAuthenticated("the operator's business no longer exists")
    await services.session.commit()
    return LoginOut(
        token=result.token,
        expires_at=result.expires_at,
        operator=OperatorOut(
            id=result.operator.id,
            email=result.operator.email,
            display_name=result.operator.display_name,
            business=BusinessBriefOut(id=business.id, name=business.name),
        ),
        ai_mode=services.runtime.settings.ai_mode,
    )


@router.post("/logout", status_code=204, summary="Завершить сессию")
async def logout(
    request: Request,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> Response:
    await services.auth.logout(bearer_token(request))
    await services.session.commit()
    return Response(status_code=204)


@router.get("/me", response_model=SessionOut, summary="Текущий оператор и его бизнес")
async def me(
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
) -> SessionOut:
    business = await services.businesses.get(operator.business_id)
    if business is None:
        raise NotAuthenticated("the operator's business no longer exists")
    return SessionOut(
        operator=OperatorOut(
            id=operator.operator_id,
            email=operator.email,
            display_name=operator.display_name,
            business=BusinessBriefOut(id=business.id, name=business.name),
        ),
        expires_at=operator.session_expires_at,
        ai_mode=services.runtime.settings.ai_mode,
    )

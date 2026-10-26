"""Operator sign-in. Called by the dashboard's Next.js server, which keeps the token in an HttpOnly cookie."""

from fastapi import APIRouter, Depends, Request, Response

from app.api.dashboard_schemas import BusinessBriefOut, LoginIn, LoginOut, OperatorOut, RegisterIn, RegisterOut, EmailRequestIn, AccountTokenIn, ResetPasswordIn, AcceptedOut, SessionOut
from app.api.deps import Services, bearer_token, current_operator, get_services
from app.application.services.auth_service import OperatorContext
from app.application.services.registration_service import RegistrationService
from app.application.services.account_email_service import AccountEmailService
from app.domain.errors import NotAuthenticated

router = APIRouter(prefix="/auth", tags=["auth"])


def email_service(services: Services) -> AccountEmailService:
    return AccountEmailService(services.session, services.runtime.settings, services.runtime.auth_mailer)


def client_ip(request: Request) -> str:
    return (request.headers.get("x-plumo-client-ip") or (request.client.host if request.client else "unknown"))[:64]


@router.post("/register", response_model=RegisterOut, status_code=201, summary="Создать аккаунт и отправить подтверждение почты")
async def register(body: RegisterIn, request: Request, services: Services = Depends(get_services)) -> RegisterOut:
    emails = email_service(services)
    emails.mailer.check_config()
    operator = await RegistrationService(services.session, services.auth).register(
        name=body.name, email=str(body.email), password=body.password, locale=body.locale, client_ip=client_ip(request),
    )
    mail = await emails.prepare(operator.id, "verify", body.locale, initial=True)
    await services.session.commit()
    sent = await emails.deliver(mail)
    return RegisterOut(email=operator.email, email_delivery="sent" if sent else "unavailable")


@router.post("/resend-verification", response_model=AcceptedOut, summary="Повторить подтверждение почты")
async def resend_verification(body: EmailRequestIn, request: Request, services: Services = Depends(get_services)) -> AcceptedOut:
    await email_service(services).request(str(body.email), "verify", body.locale, client_ip(request))
    return AcceptedOut()


@router.post("/forgot-password", response_model=AcceptedOut, summary="Запросить ссылку сброса пароля")
async def forgot_password(body: EmailRequestIn, request: Request, services: Services = Depends(get_services)) -> AcceptedOut:
    await email_service(services).request(str(body.email), "reset", body.locale, client_ip(request))
    return AcceptedOut()


@router.post("/verify-email", response_model=LoginOut, summary="Подтвердить почту и войти")
async def verify_email(body: AccountTokenIn, request: Request, services: Services = Depends(get_services)) -> LoginOut:
    result = await email_service(services).verify(body.token, client_ip(request), services.auth, services.operators)
    business = await services.businesses.get(result.operator.business_id)
    output = LoginOut(token=result.token, expires_at=result.expires_at,
        operator=OperatorOut(id=result.operator.id, email=result.operator.email, display_name=result.operator.display_name,
            business=BusinessBriefOut(id=business.id, name=business.name)), ai_mode=services.runtime.settings.ai_mode)
    await services.session.commit()
    return output


@router.post("/reset-password", response_model=AcceptedOut, summary="Задать новый пароль и завершить старые сессии")
async def reset_password(body: ResetPasswordIn, request: Request, services: Services = Depends(get_services)) -> AcceptedOut:
    await email_service(services).reset(body.token, body.password, client_ip(request))
    await services.session.commit()
    return AcceptedOut()


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

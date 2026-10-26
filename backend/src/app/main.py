"""FastAPI application."""

import logging
import asyncio
from contextlib import suppress
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.deps import require_api_key
from app.api.routes import auth, customers, dialogs, integrations, messages, onboarding, operations, readiness, telephony, testing, voice, webhooks
from app.application.services.handoff_service import drain_notifications
from app.config import Settings, get_settings
from app.container import Runtime, build_runtime
from app.correlation import correlation_id, request_id
from app.domain.errors import AppError
from app.infrastructure.logging.setup import setup_logging

logger = logging.getLogger("plumo.api")


def check_environment(settings: Settings) -> None:
    """Refuse to start a stand that would be open to anyone."""

    if settings.is_development:
        return
    missing = [name for name in ("PLUMO_API_KEY", "CHANNEL_SECRET_KEY") if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError(f"APP_ENV={settings.app_env} needs {', '.join(missing)} in the environment")


def create_app(settings: Settings | None = None, runtime: Runtime | None = None) -> FastAPI:
    settings = settings or (runtime.settings if runtime else get_settings())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings.log_level)
        check_environment(settings)
        app.state.runtime = runtime or build_runtime(settings)
        worker_stop = asyncio.Event()
        worker_task = None
        if settings.channel_worker_enabled:
            from app.worker import Worker
            worker_task = asyncio.create_task(Worker(app.state.runtime).run_forever(worker_stop, max(1, min(2, settings.worker_concurrency)), settings.worker_poll_interval_s))
        try:
            yield
        finally:
            worker_stop.set()
            if worker_task:
                try:
                    await asyncio.wait_for(worker_task, timeout=30)
                except TimeoutError:
                    worker_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await worker_task
        await drain_notifications()
        await app.state.runtime.providers.aclose()
        close = getattr(app.state.runtime.handoff_provider, "aclose", None)
        if close is not None:
            await close()
        if app.state.runtime.owns_engine:
            await app.state.runtime.engine.dispose()

    app = FastAPI(
        title="Plumo AI Core",
        version="0.2.0",
        summary="Ядро AI-менеджера, каналы Telegram/Instagram и API рабочего кабинета.",
        description=(
            "Каналы: Telegram-бот и Instagram Direct через /webhooks, ответы отправляет worker. "
            "Кабинет: вход оператора (/auth), интеграции, диалоги — только данные его бизнеса. "
            "Сервисные вызовы несут X-API-Key; маршруты кабинета — ещё и сессию оператора (Bearer). "
            "Ошибки: {error, code, message, correlation_id}."
        ),
        lifespan=lifespan,
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Correlation-Id", "X-Request-Id"],
        )

    @app.middleware("http")
    async def bind_correlation(request: Request, call_next):
        cid = request.headers.get("x-correlation-id") or str(uuid4())
        rid = request.headers.get("x-request-id") or str(uuid4())
        cid_token = correlation_id.set(cid)
        rid_token = request_id.set(rid)
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(cid_token)
            request_id.reset(rid_token)
        response.headers["X-Correlation-Id"] = cid
        response.headers["X-Request-Id"] = rid
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return _error(exc.http_status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_message",
                "code": "invalid_message",
                "message": "request validation failed",
                "correlation_id": correlation_id.get() or None,
                "details": _safe_errors(exc),
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, exc: Exception):
        # No traceback, token or payload goes to the client; the log has the details.
        logger.exception("unhandled_error", extra={"path": request.url.path})
        return _error(500, "internal_error", "internal error; quote the correlation id to the team")

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    protected = [Depends(require_api_key)]
    app.include_router(messages.router, prefix="/api/v1", dependencies=protected)
    app.include_router(voice.router, prefix="/api/v1", dependencies=protected)
    # Dashboard routes: the service key of the Next.js server and an operator session.
    app.include_router(auth.router, prefix="/api/v1", dependencies=protected)
    app.include_router(onboarding.router, prefix="/api/v1", dependencies=protected)
    app.include_router(testing.router, prefix="/api/v1", dependencies=protected)
    app.include_router(readiness.router, prefix="/api/v1", dependencies=protected)
    app.include_router(customers.router, prefix="/api/v1", dependencies=protected)
    app.include_router(operations.router, prefix="/api/v1", dependencies=protected)
    app.include_router(dialogs.router, prefix="/api/v1", dependencies=protected)
    app.include_router(integrations.router, prefix="/api/v1", dependencies=protected)
    # Provider callbacks authenticate themselves (secret header, signature).
    app.include_router(webhooks.router, prefix="/api/v1")
    app.include_router(telephony.router, prefix="/api/v1")
    return app


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": code,
            "code": code,
            "message": message,
            "correlation_id": correlation_id.get() or None,
        },
    )


def _safe_errors(exc: RequestValidationError) -> list[dict]:
    details = []
    for item in exc.errors():
        details.append(
            {
                "loc": [str(part) for part in item.get("loc", [])],
                "msg": item.get("msg", ""),
                "type": item.get("type", ""),
            }
        )
    return details


app = create_app()

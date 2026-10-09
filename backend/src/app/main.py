"""FastAPI application."""

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.deps import require_api_key
from app.api.routes import customers, messages, operations, telephony, voice
from app.application.services.handoff_service import drain_notifications
from app.config import Settings, get_settings
from app.container import Runtime, build_runtime
from app.correlation import correlation_id, request_id
from app.domain.errors import AppError
from app.infrastructure.logging.setup import setup_logging


def create_app(settings: Settings | None = None, runtime: Runtime | None = None) -> FastAPI:
    settings = settings or (runtime.settings if runtime else get_settings())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings.log_level)
        app.state.runtime = runtime or build_runtime(settings)
        yield
        await drain_notifications()
        await app.state.runtime.providers.aclose()
        close = getattr(app.state.runtime.handoff_provider, "aclose", None)
        if close is not None:
            await close()
        if app.state.runtime.owns_engine:
            await app.state.runtime.engine.dispose()

    app = FastAPI(
        title="Plumo AI Core",
        version="0.1.0",
        summary="Ядро AI-менеджера. Каналы и модели подключаются адаптерами.",
        description=(
            "Нормализованный контракт для WhatsApp, Telegram, Instagram и телефона. "
            "Текст — через OpenRouter или mock. Речь и каналы пока mock. "
            "POST /api/v1/messages принимает InboundMessage и возвращает AgentResponse."
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
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": exc.code,
                "message": exc.message,
                "correlation_id": correlation_id.get() or None,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_message",
                "message": "request validation failed",
                "correlation_id": correlation_id.get() or None,
                "details": _safe_errors(exc),
            },
        )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    protected = [Depends(require_api_key)]
    app.include_router(messages.router, prefix="/api/v1", dependencies=protected)
    app.include_router(voice.router, prefix="/api/v1", dependencies=protected)
    app.include_router(customers.router, prefix="/api/v1", dependencies=protected)
    app.include_router(operations.router, prefix="/api/v1", dependencies=protected)
    app.include_router(telephony.router, prefix="/api/v1")
    return app


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

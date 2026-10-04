"""FastAPI application."""

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import messages, operations, customers, voice
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
        if app.state.runtime.owns_engine:
            await app.state.runtime.engine.dispose()

    app = FastAPI(
        title="Plumo AI Core",
        version="0.1.0",
        summary="Ядро AI-менеджера. Каналы и модели подключаются адаптерами.",
        description=(
            "Нормализованный контракт для WhatsApp, Telegram, Instagram и телефона. "
            "Сейчас модели, речь и каналы — mock. Замена описана в INTEGRATION.md. "
            "POST /api/v1/messages принимает InboundMessage и возвращает AgentResponse."
        ),
        lifespan=lifespan,
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

    app.include_router(messages.router, prefix="/api/v1")
    app.include_router(voice.router, prefix="/api/v1")
    app.include_router(customers.router, prefix="/api/v1")
    app.include_router(operations.router, prefix="/api/v1")
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

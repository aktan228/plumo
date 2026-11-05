"""Health for monitoring (J-05). Calls no model, sends nothing, shows no texts, addresses or tokens.

- GET /health        the process answers; no database (cheap liveness)
- GET /health/db     the database answers within 2 s; 503 otherwise, without details
- GET /ops/status    service summary for the monitoring system: `Authorization: Bearer $OPS_TOKEN`.
                     Not proxied by the dashboard BFF; without OPS_TOKEN it is switched off (404).
"""

import asyncio
import hmac
import logging
import os
from datetime import timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from app.application.services.spend_limits import SERVICE, today
from app.domain.enums import JobStatus, OutboundStatus
from app.domain.errors import NotFound, Unauthorized
from app.domain.models import utcnow
from app.release import commit, config_status, worker_commit
from app.worker import HEARTBEAT_S
from app.infrastructure.database.models import (
    HandoffRequestRow,
    JobRow,
    OutboundMessageRow,
    SpendBudgetRow,
    WorkerHeartbeatRow,
)

logger = logging.getLogger("plumo.ops")
router = APIRouter(tags=["health"])

DB_TIMEOUT_S = 2.0
STALE_AFTER_S = 3 * HEARTBEAT_S


async def _db_ok(request: Request) -> bool:
    try:
        async with asyncio.timeout(DB_TIMEOUT_S):
            async with request.app.state.runtime.session_factory() as session:
                await session.execute(text("SELECT 1"))
        return True
    except Exception:  # any failure is "unhealthy"; the reason stays in the log, not the answer
        logger.warning("health_db_unavailable")
        return False


@router.get("/health/db", summary="База данных отвечает")
async def health_db(request: Request) -> JSONResponse:
    if await _db_ok(request):
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "unavailable"}, status_code=503)


def _authorize(request: Request) -> None:
    expected = os.getenv("OPS_TOKEN", "").strip()
    if not expected:
        raise NotFound("not found")
    header = request.headers.get("authorization", "")
    given = header[7:].strip() if header[:7].lower() == "bearer " else ""
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise Unauthorized("missing or wrong ops token")


@router.get("/ops/status", summary="Служебная сводка для мониторинга (OPS_TOKEN)")
async def ops_status(request: Request) -> JSONResponse:
    _authorize(request)
    if not await _db_ok(request):
        return JSONResponse({"status": "unavailable", "database": "unavailable"}, status_code=503)
    now = utcnow()
    settings = request.app.state.runtime.settings
    async with request.app.state.runtime.session_factory() as session:
        # None: the schema was not made by migrations (a test database); monitoring should flag it.
        has_alembic = await session.scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL"))
        schema = await session.scalar(text("SELECT version_num FROM alembic_version")) if has_alembic else None
        last_beat = await session.scalar(select(func.max(WorkerHeartbeatRow.seen_at)))
        alive_ids = (
            await session.scalars(select(WorkerHeartbeatRow.worker_id).where(WorkerHeartbeatRow.seen_at >= now - timedelta(seconds=STALE_AFTER_S)))
        ).all()
        due = (
            await session.execute(
                select(func.count(), func.min(JobRow.run_at)).where(JobRow.status == JobStatus.queued, JobRow.run_at <= now)
            )
        ).one()
        delayed = await session.scalar(
            select(func.count()).select_from(JobRow).where(JobRow.status == JobStatus.queued, JobRow.run_at > now)
        )
        stuck = await session.scalar(
            select(func.count()).select_from(JobRow).where(JobRow.status == JobStatus.running, JobRow.locked_until < now)
        )
        day_ago = now - timedelta(days=1)
        failed_jobs = await session.scalar(
            select(func.count()).select_from(JobRow).where(JobRow.status == JobStatus.failed, JobRow.updated_at >= day_ago)
        )
        unknown_replies = await session.scalar(
            select(func.count()).select_from(OutboundMessageRow).where(OutboundMessageRow.status == OutboundStatus.unknown)
        )
        notify_open = await session.scalar(
            select(func.count())
            .select_from(HandoffRequestRow)
            .where(HandoffRequestRow.notify_status.in_((OutboundStatus.failed, OutboundStatus.unknown)), HandoffRequestRow.updated_at >= day_ago)
        )
        service = await session.get(SpendBudgetRow, (SERVICE, today()))
    oldest_age = int((now - due[1]).total_seconds()) if due[1] else 0
    worker_age = int((now - last_beat).total_seconds()) if last_beat else None
    alive = len(alive_ids)
    healthy = alive > 0 and oldest_age < 300
    return JSONResponse(
        {
            "status": "ok" if healthy else "degraded",
            "app_version": request.app.version,
            "commit": commit(),
            "schema_version": schema,
            "database": "ok",
            "workers": {
                "alive": alive,
                "commits": sorted({worker_commit(worker_id) for worker_id in alive_ids}),
                "last_heartbeat_age_s": worker_age,
                "stale_after_s": int(STALE_AFTER_S),
            },
            "jobs": {
                "due": due[0],
                "oldest_due_age_s": oldest_age,
                "delayed_retries": delayed,
                "expired_leases": stuck,
                "failed_24h": failed_jobs,
            },
            "deliveries_unknown": unknown_replies,
            "notifications_failed_or_unknown_24h": notify_open,
            "limits": {
                "service_spent_usd": float((service.spent + service.reserved) if service else 0),
                "service_limit_usd": settings.limit_service_daily_usd,
            },
            "config": config_status(settings),
        }
    )

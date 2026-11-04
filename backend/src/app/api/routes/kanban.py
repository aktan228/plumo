"""Tenant-scoped board columns and versioned manual stage transitions."""
import binascii
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text

from app.api.deps import Services, current_operator, get_services
from app.application.services.auth_service import OperatorContext
from app.domain.errors import ConversationNotFound, InvalidMessage, VersionConflict
from app.domain.models import utcnow
from app.infrastructure.database.models import ConversationRow, CustomerRow
from app.infrastructure.database.dialog_queries import decode_cursor, encode_cursor

Stage = Literal["unassigned", "new", "discovery", "qualified", "meeting_requested", "meeting_confirmed"]
router = APIRouter(tags=["kanban"])


class StageIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    stage: Stage
    version: int = Field(ge=0, le=2_000_000_000)
    confirm_meeting: bool = False


class StageOut(BaseModel):
    id: UUID
    pipeline_stage: Stage
    stage_version: int


class BoardCard(StageOut):
    channel: str
    mode: Literal["ai", "human", "waiting"]
    name: str | None
    handle: str | None
    phone: str | None
    preview: str | None
    activity_at: datetime


class ColumnOut(BaseModel):
    stage: Stage
    total: int
    items: list[BoardCard]
    next_cursor: str | None


@router.get("/dashboard/kanban", response_model=ColumnOut, summary="Колонка канбана: полный счётчик, фильтры, курсор")
async def column(
    stage: Stage,
    q: str | None = Query(default=None, max_length=100),
    channel: str | None = Query(default=None, max_length=32),
    mode: Literal["ai", "human", "waiting"] | None = None,
    cursor: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=30, ge=1, le=100),
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
):
    params = {"business_id": operator.business_id, "stage": stage, "limit": limit + 1}
    where = ["c.business_id=:business_id", "cu.business_id=:business_id", "c.pipeline_stage=:stage"]
    if channel:
        where.append("c.channel=:channel")
        params["channel"] = channel
    if q and q.strip():
        def folded(column):
            return f"translate({column}, 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯҢӨҮ', 'абвгдеёжзийклмнопрстуфхцчшщъыьэюяңөү')"
        params["q"] = "%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append(f"""({folded('c.contact_name')} ILIKE :q ESCAPE '\\'
            OR {folded('c.contact_handle')} ILIKE :q ESCAPE '\\'
            OR cu.phone ILIKE :q ESCAPE '\\' OR cu.contact_phone ILIKE :q ESCAPE '\\'
            OR EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id=c.id AND m.role <> 'system'
                AND {folded('m.text')} ILIKE :q ESCAPE '\\'))""")
    outer = "WHERE mode=:mode" if mode else ""
    if mode:
        params["mode"] = mode
    page_where = ""
    if cursor:
        try:
            at, ident = decode_cursor(cursor)
            if at.tzinfo is None:
                raise ValueError("timezone required")
        except (ValueError, TypeError, AttributeError, binascii.Error):
            raise InvalidMessage("cursor is invalid") from None
        params.update(cursor_at=at, cursor_id=ident)
        page_where = "WHERE (activity_at,id) < (:cursor_at,:cursor_id)"
    sql = """WITH base AS (SELECT c.id, c.pipeline_stage, c.stage_version, c.channel,
        CASE WHEN c.mode='human' THEN 'human' WHEN EXISTS (SELECT 1 FROM handoff_requests h
            WHERE h.conversation_id=c.id AND h.status='PENDING') THEN 'waiting' ELSE 'ai' END AS mode,
        c.contact_name AS name, c.contact_handle AS handle, cu.phone,
        left(lm.text,300) AS preview, coalesce(lm.timestamp,c.started_at) AS activity_at
        FROM conversations c JOIN customers cu ON cu.id=c.customer_id
        LEFT JOIN LATERAL (SELECT m.text,m.timestamp FROM messages m WHERE m.conversation_id=c.id
            AND m.role <> 'system' ORDER BY m.timestamp DESC,m.seq DESC LIMIT 1) lm ON true
        WHERE """ + " AND ".join(where) + """), matching AS (SELECT * FROM base """ + outer + """),
        page AS (SELECT * FROM matching """ + page_where + """ ORDER BY activity_at DESC,id DESC LIMIT :limit)
        SELECT (SELECT count(*) FROM matching) AS total,
            coalesce(jsonb_agg(to_jsonb(page) ORDER BY activity_at DESC,id DESC), '[]'::jsonb) AS items FROM page"""
    result = (await services.session.execute(text(sql), params)).mappings().one()
    items = result["items"]
    more = len(items) > limit
    items = items[:limit]
    next_cursor = encode_cursor(datetime.fromisoformat(items[-1]["activity_at"]), UUID(items[-1]["id"])) if more else None
    return ColumnOut(stage=stage, total=result["total"], items=items, next_cursor=next_cursor)


@router.patch("/conversations/{ident}/stage", response_model=StageOut, summary="Изменить только стадию с проверкой версии")
async def move(ident: UUID, body: StageIn, operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    row = await services.session.scalar(select(ConversationRow).join(CustomerRow, CustomerRow.id == ConversationRow.customer_id)
        .where(ConversationRow.id == ident, ConversationRow.business_id == operator.business_id,
               CustomerRow.business_id == operator.business_id).with_for_update(of=ConversationRow))
    if row is None:
        raise ConversationNotFound("conversation not found")
    if row.stage_version != body.version:
        raise VersionConflict("Stage changed; reload the board")
    if row.pipeline_stage != body.stage:
        if body.stage == "meeting_confirmed" and not body.confirm_meeting:
            raise InvalidMessage("A manager must explicitly confirm the meeting", code="meeting_confirmation_required")
        row.pipeline_stage = body.stage
        row.stage_version += 1
        row.stage_updated_at, row.stage_updated_by = utcnow(), operator.operator_id
    await services.session.commit()
    return StageOut(id=row.id, pipeline_stage=row.pipeline_stage, stage_version=row.stage_version)

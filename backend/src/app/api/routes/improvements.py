"""Evidence-backed, tenant-scoped correction workflow. No automatic publication."""
import binascii
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import Services, current_operator, get_services
from app.application.services.auth_service import OperatorContext
from app.domain.errors import InvalidMessage, InvalidState, NotFound, VersionConflict
from app.domain.models import utcnow
from app.infrastructure.database.dialog_queries import decode_cursor, encode_cursor
from app.infrastructure.database.models import (
    BusinessRow, ConversationRow, CustomerRow, ImprovementRow, MessageRow, TestSessionRow, TestTurnRow,
)

Category = Literal["incorrect_fact", "missing_answer", "handoff", "language_tone"]
Status = Literal["new", "in_progress", "fixed", "verified"]
router = APIRouter(prefix="/improvements", tags=["improvements"])


class CreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    category: Category
    note: str = Field(min_length=1, max_length=2000)
    message_id: UUID | None = None
    test_session_id: UUID | None = None
    test_request_id: UUID | None = None

    @field_validator("note")
    @classmethod
    def clean_note(cls, value):
        if not value.strip() or "\0" in value:
            raise ValueError("note is empty or invalid")
        return value.strip()

    @model_validator(mode="after")
    def one_source(self):
        if self.message_id is not None:
            if self.test_session_id is not None or self.test_request_id is not None:
                raise ValueError("choose exactly one source")
        elif self.test_session_id is None or self.test_request_id is None:
            raise ValueError("test source requires both identifiers")
        return self


class UpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=0, le=2_000_000_000, strict=True)
    status: Status
    note: str = Field(default="", max_length=2000)
    test_session_id: UUID | None = None
    test_request_id: UUID | None = None

    @field_validator("note")
    @classmethod
    def clean_note(cls, value):
        if "\0" in value:
            raise ValueError("invalid note")
        return value.strip()


def publication(business):
    value = ((business.profile or {}).get("onboarding_publication") or {}).get("draft_version")
    return value if type(value) is int else None


def source_versions(values):
    # Only whitelisted evidence; never copy arbitrary message metadata into a response.
    result = []
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            ident = str(UUID(str(item.get("id"))))
        except (ValueError, TypeError, AttributeError):
            continue
        result.append({"id": ident, "title": str(item.get("title") or "")[:300],
                       "updated_at": item.get("updated_at"), "content_sha256": item.get("content_sha256")})
    return result


async def snapshot(db, business_id, body):
    if body.message_id:
        message = await db.scalar(select(MessageRow)
            .join(ConversationRow, ConversationRow.id == MessageRow.conversation_id)
            .join(CustomerRow, CustomerRow.id == ConversationRow.customer_id)
            .where(MessageRow.id == body.message_id, MessageRow.role == "assistant",
                   MessageRow.customer_id == ConversationRow.customer_id,
                   ConversationRow.business_id == business_id, CustomerRow.business_id == business_id))
        if message is None:
            raise NotFound("answer not found")
        question = await db.scalar(select(MessageRow.text).where(
            MessageRow.conversation_id == message.conversation_id, MessageRow.role == "user", MessageRow.seq < message.seq
        ).order_by(MessageRow.seq.desc()).limit(1))
        meta = message.metadata_json or {}
        version = meta.get("publication_version")
        return "message:" + str(message.id), {"kind": "message", "message_id": str(message.id),
            "conversation_id": str(message.conversation_id), "answer": message.text, "question": question,
            "publication_version": version if type(version) is int else None,
            "model": str(meta.get("model") or "")[:100], "source_versions": source_versions(meta.get("source_versions")),
            "answered_at": message.timestamp.isoformat()}
    session = await db.scalar(select(TestSessionRow).where(
        TestSessionRow.id == body.test_session_id, TestSessionRow.business_id == business_id))
    if session is None:
        raise NotFound("test answer not found")
    turn = await db.get(TestTurnRow, (session.id, body.test_request_id))
    if not turn or turn.status != "succeeded" or not (turn.result or {}).get("text"):
        raise InvalidState("Choose a successful test answer", code="improvement_answer_required")
    result = turn.result
    return f"test:{session.id}:{turn.request_id}", {"kind": "test", "test_session_id": str(session.id),
        "test_request_id": str(turn.request_id), "answer": result["text"], "question": turn.text,
        "publication_version": session.publication_version, "model": str(result.get("model") or "")[:100],
        "mock": bool(result.get("mock")), "source_versions": source_versions(result.get("source_versions", result.get("sources"))),
        "answered_at": turn.created_at.isoformat()}


def output(row, current):
    return {"id": row.id, "category": row.category, "note": row.note, "snapshot": row.snapshot,
            "status": row.status, "version": row.version, "created_at": row.created_at, "updated_at": row.updated_at,
            "fixed_publication_version": row.fixed_publication_version, "fixed_at": row.fixed_at,
            "correction_note": row.correction_note, "verification": row.verification, "history": row.history,
            "current_publication_version": current,
            "verification_current": row.status == "verified" and row.fixed_publication_version == current}


async def owned(db, business_id, ident, lock=False):
    query = select(ImprovementRow).where(ImprovementRow.id == ident, ImprovementRow.business_id == business_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await db.scalar(query)
    if row is None:
        raise NotFound("improvement not found")
    return row


@router.post("", summary="Замечание к своему ответу: неизменяемый снимок и идемпотентный ID")
async def create(body: CreateIn, operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    db = services.session
    key, evidence = await snapshot(db, operator.business_id, body)
    now = utcnow()
    await db.execute(insert(ImprovementRow).values(id=body.id, business_id=operator.business_id,
        category=body.category, note=body.note, source_key=key, snapshot=evidence, status="new", version=0,
        created_by=operator.operator_id, updated_by=operator.operator_id, created_at=now, updated_at=now,
        history=[{"status": "new", "at": now.isoformat(), "operator": str(operator.operator_id)}]
    ).on_conflict_do_nothing(index_elements=[ImprovementRow.id]))
    row = await owned(db, operator.business_id, body.id)
    if (row.source_key, row.category, row.note) != (key, body.category, body.note):
        raise InvalidState("Request ID was used for another improvement", code="improvement_request_conflict")
    business = await db.get(BusinessRow, operator.business_id)
    await db.commit()
    return output(row, publication(business))


@router.get("", summary="Замечания своего бизнеса: статус и курсор")
async def listing(status: Status | None = None, cursor: str | None = Query(default=None, max_length=300),
                  limit: int = Query(default=20, ge=1, le=100), operator: OperatorContext = Depends(current_operator),
                  services: Services = Depends(get_services)):
    query = select(ImprovementRow).where(ImprovementRow.business_id == operator.business_id)
    if status:
        query = query.where(ImprovementRow.status == status)
    if cursor:
        try:
            at, ident = decode_cursor(cursor)
            if at.tzinfo is None:
                raise ValueError("timezone required")
        except (ValueError, TypeError, AttributeError, binascii.Error):
            raise InvalidMessage("cursor is invalid") from None
        query = query.where(tuple_(ImprovementRow.created_at, ImprovementRow.id) < tuple_(at, ident))
    rows = list((await services.session.scalars(query.order_by(ImprovementRow.created_at.desc(), ImprovementRow.id.desc()).limit(limit + 1))).all())
    more = len(rows) > limit
    rows = rows[:limit]
    current = publication(await services.session.get(BusinessRow, operator.business_id))
    return {"items": [output(row, current) for row in rows],
            "next_cursor": encode_cursor(rows[-1].created_at, rows[-1].id) if more else None}


@router.get("/{ident}", summary="Карточка замечания с исходным ответом и историей проверки")
async def detail(ident: UUID, operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    row = await owned(services.session, operator.business_id, ident)
    current = publication(await services.session.get(BusinessRow, operator.business_id))
    return output(row, current)


@router.patch("/{ident}", summary="Статус замечания: новая публикация и свежая повторная проверка")
async def update(ident: UUID, body: UpdateIn, operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    db = services.session
    row = await owned(db, operator.business_id, ident, lock=True)
    if row.version != body.version:
        raise VersionConflict("Improvement changed; reload it")
    transitions = {"new": {"in_progress"}, "in_progress": {"fixed"}, "fixed": {"in_progress", "verified"}, "verified": {"in_progress"}}
    if body.status not in transitions[row.status]:
        raise InvalidState("This status transition is unavailable", code="improvement_transition_invalid")
    business = await db.scalar(select(BusinessRow).where(BusinessRow.id == operator.business_id).with_for_update().execution_options(populate_existing=True))
    current, now = publication(business), utcnow()
    if body.status != "verified" and (body.test_session_id or body.test_request_id):
        raise InvalidMessage("Test evidence is only accepted for verification")
    if body.status == "fixed":
        original = row.snapshot.get("publication_version")
        if not body.note or current is None or (original is not None and current <= original):
            raise InvalidState("Publish a newer correction and describe it first", code="improvement_publication_required")
        row.fixed_publication_version, row.fixed_at, row.correction_note = current, now, body.note
    elif body.status == "verified":
        if not body.note or not body.test_session_id or not body.test_request_id or current != row.fixed_publication_version:
            raise InvalidState("Select fresh evidence for the corrected publication", code="improvement_verification_required")
        session = await db.scalar(select(TestSessionRow).where(TestSessionRow.id == body.test_session_id,
            TestSessionRow.business_id == operator.business_id))
        turn = await db.get(TestTurnRow, (session.id, body.test_request_id)) if session else None
        if (not session or session.publication_version != current or session.created_at < row.fixed_at
                or not turn or turn.status != "succeeded" or turn.created_at < row.fixed_at or not (turn.result or {}).get("text")):
            raise InvalidState("Start a new test after marking the correction", code="improvement_verification_required")
        result = turn.result
        scope = "demo" if result.get("mock") else "rule" if str(result.get("model", "")).startswith("rules:") else "model"
        row.verification = {"test_session_id": str(session.id), "test_request_id": str(turn.request_id),
            "publication_version": current, "question": turn.text, "answer": result["text"],
            "model": str(result.get("model") or "")[:100], "scope": scope, "note": body.note,
            "source_versions": source_versions(result.get("source_versions", result.get("sources"))),
            "at": now.isoformat(), "operator": str(operator.operator_id)}
    else:
        row.fixed_at = row.fixed_publication_version = row.verification = None
    row.status, row.version, row.updated_at, row.updated_by = body.status, row.version + 1, now, operator.operator_id
    row.history = [*(row.history or []), {"status": row.status, "at": now.isoformat(), "operator": str(operator.operator_id),
        "publication_version": current, "note": body.note, "verification": row.verification}]
    await db.commit()
    return output(row, current)

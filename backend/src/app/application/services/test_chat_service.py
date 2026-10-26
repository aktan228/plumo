"""Tenant-scoped test sessions, durable idempotency and shared daily allowances."""

import asyncio
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.application.services.test_sandbox import STATE, initial_state, test_agent
from app.domain.errors import InvalidState, NotFound, TooManyRequests
from app.domain.models import InboundMessage, utcnow
from app.infrastructure.database.models import BusinessRow, TestBudgetRow, TestSessionRow, TestTurnRow


class TestChatService:
    def __init__(self, session, runtime):
        self.db, self.runtime, self.settings = session, runtime, runtime.settings

    async def budget(self, business_id):
        today = utcnow().date().isoformat()
        await self.db.execute(
            insert(TestBudgetRow)
            .values(business_id=business_id, day=today, attempts=0, sessions=0, charged=0)
            .on_conflict_do_nothing()
        )
        row = await self.db.scalar(
            select(TestBudgetRow)
            .where(TestBudgetRow.business_id == business_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row.day != today:
            row.day, row.attempts, row.sessions, row.charged = today, 0, 0, Decimal("0")
        return row

    def limits(self, budget):
        return {
            "daily_messages": self.settings.test_chat_daily_messages,
            "session_messages": self.settings.test_chat_session_messages,
            "daily_budget_usd": self.settings.test_chat_daily_budget_usd,
            "used_messages": budget.attempts if budget else 0,
            "charged_usd": float(budget.charged) if budget else 0,
        }

    async def business(self, business_id):
        business = await self.db.get(BusinessRow, business_id)
        if business is None:
            raise NotFound("business not found")
        return business

    @staticmethod
    def publication(business):
        return (business.profile or {}).get("onboarding_publication", {}).get("draft_version")

    async def owned(self, business_id, ident, *, lock=False):
        query = select(TestSessionRow).where(TestSessionRow.id == ident, TestSessionRow.business_id == business_id)
        if lock:
            query = query.with_for_update()
        row = await self.db.scalar(query.execution_options(populate_existing=True))
        if row is None:
            raise NotFound("test session not found")
        return row

    @staticmethod
    def summary(row):
        return {
            "id": str(row.id),
            "created_at": row.created_at.isoformat(),
            "paused": row.paused,
            "messages": row.attempts,
            "publication_version": row.publication_version,
        }

    @staticmethod
    def turn_out(row):
        return {
            "id": str(row.request_id),
            "text": row.text,
            "status": row.status,
            "error": row.error,
            "result": row.result or None,
            "created_at": row.created_at.isoformat(),
        }

    async def listing(self, business_id):
        rows = (
            await self.db.scalars(
                select(TestSessionRow)
                .where(TestSessionRow.business_id == business_id)
                .order_by(TestSessionRow.created_at.desc())
                .limit(20)
            )
        ).all()
        budget = await self.db.get(TestBudgetRow, business_id)
        if budget and budget.day != utcnow().date().isoformat():
            budget = None
        business = await self.business(business_id)
        return {
            "sessions": [self.summary(row) for row in rows],
            "limits": self.limits(budget),
            "mock": self.settings.mock_mode or self.settings.big_model_provider == "mock",
            "published": self.publication(business) is not None,
        }

    async def detail(self, business_id, ident):
        row = await self.owned(business_id, ident)
        if row.pending_id:
            pending = await self.db.get(TestTurnRow, (ident, row.pending_id))
            if pending and pending.status == "pending" and pending.created_at < utcnow() - timedelta(seconds=90):
                row = await self.owned(business_id, ident, lock=True)
                pending = await self.db.get(TestTurnRow, (ident, pending.request_id), populate_existing=True)
                if pending.status == "pending":
                    pending.status, pending.error = "failed", "test_interrupted"
                    row.pending_id = None
                    await self.db.commit()
        turns = (
            await self.db.scalars(
                select(TestTurnRow)
                .where(TestTurnRow.session_id == ident)
                .order_by(TestTurnRow.created_at, TestTurnRow.request_id)
            )
        ).all()
        return {**self.summary(row), "turns": [self.turn_out(turn) for turn in turns]}

    async def create(self, business_id, ident):
        budget = await self.budget(business_id)
        existing = await self.db.get(TestSessionRow, ident)
        if existing is not None:
            if existing.business_id != business_id:
                raise NotFound("test session not found")
            return await self.detail(business_id, ident)
        business = await self.business(business_id)
        version = self.publication(business)
        if version is None:
            raise InvalidState("Publish the business setup first", code="test_setup_required")
        if budget.sessions >= 20:
            raise TooManyRequests("Daily test session limit reached", code="test_session_limit")
        row = TestSessionRow(
            id=ident,
            business_id=business_id,
            publication_version=version,
            state=STATE.dump_python(initial_state(business_id), mode="json"),
            attempts=0,
            paused=False,
            created_at=utcnow(),
        )
        self.db.add(row)
        budget.sessions += 1
        await self.db.commit()
        return await self.detail(business_id, ident)

    async def send(self, business_id, ident, body):
        budget = await self.budget(business_id)
        row = await self.owned(business_id, ident, lock=True)
        existing = await self.db.get(TestTurnRow, (ident, body.request_id))
        if existing is not None:
            if existing.text != body.text:
                raise InvalidState("Request ID was already used for another message", code="test_request_conflict")
            if existing.status == "pending" and existing.created_at < utcnow() - timedelta(seconds=90):
                existing.status, existing.error = "failed", "test_interrupted"
                if row.pending_id == existing.request_id:
                    row.pending_id = None
                await self.db.commit()
            return self.turn_out(existing)
        if row.pending_id:
            previous = await self.db.get(TestTurnRow, (ident, row.pending_id))
            if previous.created_at > utcnow() - timedelta(seconds=90):
                raise InvalidState("Another message is still being processed", code="test_busy")
            previous.status, previous.error = "failed", "test_interrupted"
            row.pending_id = None
        if row.paused:
            raise InvalidState("Start a new test after the simulated handoff", code="test_paused")
        business = await self.business(business_id)
        if self.publication(business) != row.publication_version:
            raise InvalidState("Published settings changed; start a new test", code="test_settings_changed")
        reserve = Decimal(str(self.settings.test_chat_turn_reserve_usd))
        if (
            row.attempts >= self.settings.test_chat_session_messages
            or budget.attempts >= self.settings.test_chat_daily_messages
            or budget.charged + reserve > Decimal(str(self.settings.test_chat_daily_budget_usd))
        ):
            raise TooManyRequests("Test allowance reached", code="test_limit")
        now = utcnow()
        turn = TestTurnRow(
            session_id=ident,
            request_id=body.request_id,
            text=body.text,
            status="pending",
            result={},
            day=budget.day,
            created_at=now,
        )
        self.db.add(turn)
        row.attempts += 1
        row.pending_id = body.request_id
        budget.attempts += 1
        budget.charged += reserve
        state = STATE.validate_python(row.state)
        # Charge and idempotency marker survive browser disconnects or a process crash.
        await self.db.commit()
        result, error = None, None
        meter = {"cost": 0.0}
        try:
            agent, meter = test_agent(self.db, self.runtime, state)
            async with asyncio.timeout(25):
                reply = await agent.process_message(
                    InboundMessage(
                        channel="cli",
                        external_user_id=f"test:{ident}",
                        text=body.text,
                        message_id=str(body.request_id),
                        business_id=business_id,
                    )
                )
            if reply.model_used.endswith((":timeout", ":unavailable")):
                error = "test_provider_unavailable"
            else:
                result = {
                    "text": reply.response_text,
                    "handoff": reply.handoff_required,
                    "handoff_reason": reply.handoff_reason,
                    "model": reply.model_used,
                    "sources": [{"title": item.title, "id": str(item.id)} for item in reply.knowledge_sources],
                    "estimated_cost": reply.usage.estimated_cost,
                    "mock": self.settings.mock_mode or reply.model_used.startswith("mock"),
                }
        except Exception:
            # Raw provider exceptions can carry credentials or content; fixed error only.
            error = "test_provider_unavailable"
            await self.db.rollback()
        self.db.expire_all()
        budget = await self.budget(business_id)
        row = await self.owned(business_id, ident, lock=True)
        turn = await self.db.get(TestTurnRow, (ident, body.request_id))
        if turn.status != "pending" or row.pending_id != body.request_id:
            return self.turn_out(turn)
        turn.status, turn.error, turn.result = "failed" if error else "succeeded", error, result or {}
        if not error:
            row.state = STATE.dump_python(state, mode="json")
            row.paused = bool(result["handoff"])
        row.pending_id = None
        # Reconcile known successful usage; uncertain failures keep at least the reserve.
        if turn.day == budget.day:
            cost = Decimal(str(meter["cost"]))
            budget.charged += (max(reserve, cost) if error else cost) - reserve
        await self.db.commit()
        return self.turn_out(turn)

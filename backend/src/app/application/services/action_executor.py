"""Execute structured actions. The model is not allowed to write storage itself."""

from app.domain.enums import ActionType
from app.domain.models import Action, ActionContext, ActionResult, utcnow
from app.application.services.handoff_service import HandoffService
from app.application.services.meeting_service import MeetingService
from app.domain.ports import CustomerStore


class MockActionExecutor:
    """Local executor used until CRM, calendar or messenger actions exist.

    `schedule_meeting` writes a Meeting row. It does not call a calendar.
    `handoff` writes a HandoffRequest and notifies the handoff port.
    """

    def __init__(
        self,
        meetings: MeetingService,
        handoffs: HandoffService,
        customers: CustomerStore,
    ) -> None:
        self.meetings = meetings
        self.handoffs = handoffs
        self.customers = customers

    async def execute(self, actions: list[Action], ctx: ActionContext) -> list[ActionResult]:
        results: list[ActionResult] = []
        for action in actions:
            name = _HANDLER_NAMES.get(action.type)
            if name is None:
                results.append(ActionResult(action.type, "skipped", {"reason": "unknown_action"}))
                continue
            results.append(await getattr(self, name)(action, ctx))
        return results

    async def _schedule(self, action: Action, ctx: ActionContext) -> ActionResult:
        meeting = await self.meetings.schedule(
            customer_id=ctx.customer.id,
            business_id=ctx.business.id,
            text=str(action.payload.get("text") or ""),
            payload=action.payload,
            notes=action.payload.get("notes"),
        )
        return ActionResult(
            action.type,
            "executed",
            {
                "meeting_id": str(meeting.id),
                "datetime": meeting.scheduled_at.isoformat(),
                "status": meeting.status,
            },
        )

    async def _request_phone(self, action: Action, ctx: ActionContext) -> ActionResult:
        return ActionResult(
            action.type,
            "executed",
            {"customer_id": str(ctx.customer.id), "has_phone": bool(ctx.customer.phone or ctx.customer.contact_phone)},
        )

    async def _handoff(self, action: Action, ctx: ActionContext) -> ActionResult:
        reason = str(action.payload.get("reason") or "user_requested_human")
        priority = str(action.payload.get("priority") or "normal")
        handoff = await self.handoffs.request(
            customer=ctx.customer,
            conversation=ctx.conversation,
            reason=reason,
            priority=priority,
            summary=ctx.summary_text or (ctx.recent_messages[-1].text if ctx.recent_messages else ""),
            recent_messages=ctx.recent_messages,
        )
        return ActionResult(
            action.type,
            "executed",
            {"handoff_id": str(handoff.id), "status": handoff.status, "reason": handoff.reason},
        )

    async def _update_customer(self, action: Action, ctx: ActionContext) -> ActionResult:
        customer = ctx.customer
        changed = False
        need = action.payload.get("need")
        language = action.payload.get("language")
        if isinstance(need, str) and need and need != customer.need:
            customer.need = need
            changed = True
        if isinstance(language, str) and language and customer.language in ("", "unknown"):
            customer.language = language
            changed = True
        if changed:
            customer.updated_at = utcnow()
            await self.customers.save(customer)
        return ActionResult(action.type, "executed" if changed else "skipped", {"need": customer.need})


_HANDLER_NAMES = {
    ActionType.schedule_meeting: "_schedule",
    ActionType.request_phone: "_request_phone",
    ActionType.handoff: "_handoff",
    ActionType.update_customer: "_update_customer",
}

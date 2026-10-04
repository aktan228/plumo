"""Mock handoff transport. It records nothing beyond the log line; the row is already stored."""

import logging

from app.domain.models import HandoffRequest

logger = logging.getLogger("plumo.handoff")


class MockHandoffProvider:
    async def notify(self, handoff: HandoffRequest) -> None:
        logger.info(
            "handoff_saved",
            extra={
                "handoff_id": str(handoff.id),
                "customer_id": str(handoff.customer_id),
                "reason": handoff.reason,
                "priority": handoff.priority,
                "status": handoff.status,
            },
        )

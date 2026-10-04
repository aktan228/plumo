"""Meetings stored locally. A calendar adapter can replace the executor, not this record."""

from uuid import uuid4

from app.domain.enums import MeetingStatus
from app.domain.errors import MeetingNotFound
from app.domain.events import MEETING_SCHEDULED, DomainEvent
from app.domain.models import Meeting, utcnow
from app.domain.ports import EventBus, MeetingStore
from app.domain.scheduling import parse_slot


class MeetingService:
    def __init__(self, meetings: MeetingStore, events: EventBus) -> None:
        self.meetings = meetings
        self.events = events

    async def schedule(
        self,
        *,
        customer_id,
        business_id,
        text: str,
        payload: dict | None = None,
        notes: str | None = None,
    ) -> Meeting:
        when = parse_slot(text, payload, utcnow())
        now = utcnow()
        meeting = Meeting(
            id=uuid4(),
            customer_id=customer_id,
            business_id=business_id,
            scheduled_at=when,
            status=MeetingStatus.proposed,
            notes=notes,
            created_at=now,
            updated_at=now,
        )
        await self.meetings.add(meeting)
        await self.events.publish(
            DomainEvent(
                MEETING_SCHEDULED,
                {
                    "meeting_id": str(meeting.id),
                    "customer_id": str(customer_id),
                    "datetime": when.isoformat(),
                },
            )
        )
        return meeting

    async def get(self, meeting_id) -> Meeting:
        meeting = await self.meetings.get(meeting_id)
        if meeting is None:
            raise MeetingNotFound(f"meeting {meeting_id} was not found")
        return meeting

    async def list_for_customer(self, customer_id) -> list[Meeting]:
        return await self.meetings.list_for_customer(customer_id)

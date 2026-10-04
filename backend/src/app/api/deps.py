"""Request-scoped services."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.agent_service import AgentService
from app.application.services.handoff_service import HandoffService
from app.application.services.meeting_service import MeetingService
from app.application.services.metrics_service import MetricsService
from app.application.services.voice_service import VoiceService
from app.application.use_cases.handle_channel_event import HandleChannelEvent
from app.container import Runtime, build_agent, build_channel_handler, build_handoffs, build_meetings, build_metrics, build_voice
from app.infrastructure.database.repositories import (
    BusinessRepository,
    ConversationRepository,
    CustomerRepository,
    KnowledgeRepository,
    MessageRepository,
)


@dataclass
class Services:
    session: AsyncSession
    runtime: Runtime
    agent: AgentService
    voice: VoiceService
    channels: HandleChannelEvent
    handoffs: HandoffService
    meetings: MeetingService
    metrics: MetricsService
    customers: CustomerRepository
    conversations: ConversationRepository
    messages: MessageRepository
    knowledge: KnowledgeRepository
    businesses: BusinessRepository


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    runtime: Runtime = request.app.state.runtime
    async with runtime.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_services(
    session: AsyncSession = Depends(get_session),
    runtime: Runtime = Depends(get_runtime),
) -> Services:
    return Services(
        session=session,
        runtime=runtime,
        agent=build_agent(session, runtime),
        voice=build_voice(session, runtime),
        channels=build_channel_handler(session, runtime),
        handoffs=build_handoffs(session, runtime),
        meetings=build_meetings(session, runtime),
        metrics=build_metrics(session),
        customers=CustomerRepository(session),
        conversations=ConversationRepository(session),
        messages=MessageRepository(session),
        knowledge=KnowledgeRepository(session),
        businesses=BusinessRepository(session),
    )

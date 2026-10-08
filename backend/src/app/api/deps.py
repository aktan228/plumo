"""Request-scoped services."""

import hmac
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.agent_service import AgentService
from app.application.services.call_service import CallService
from app.application.services.handoff_service import HandoffService
from app.application.services.meeting_service import MeetingService
from app.application.services.metrics_service import MetricsService
from app.application.services.voice_service import VoiceService
from app.application.use_cases.handle_channel_event import HandleChannelEvent
from app.container import Runtime, build_agent, build_calls, build_handoffs, build_meetings, build_metrics
from app.domain.errors import Unauthorized
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
    calls: CallService
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


def require_api_key(request: Request) -> None:
    """Dashboard and channel calls carry `X-API-Key: $PLUMO_API_KEY`.

    Unset key = open API, for local development only. Telephony routes have
    their own provider auth and skip this check.
    """

    expected = os.getenv("PLUMO_API_KEY", "").strip()
    if not expected:
        return
    given = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise Unauthorized("missing or wrong X-API-Key")


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_services(
    session: AsyncSession = Depends(get_session),
    runtime: Runtime = Depends(get_runtime),
) -> Services:
    agent = build_agent(session, runtime)
    return Services(
        session=session,
        runtime=runtime,
        agent=agent,
        voice=VoiceService(runtime.providers.stt(), runtime.providers.tts(), agent),
        calls=build_calls(session, runtime, agent),
        channels=HandleChannelEvent(runtime.channels, agent),
        handoffs=build_handoffs(session, runtime),
        meetings=build_meetings(session, runtime),
        metrics=build_metrics(session),
        customers=CustomerRepository(session),
        conversations=ConversationRepository(session),
        messages=MessageRepository(session),
        knowledge=KnowledgeRepository(session),
        businesses=BusinessRepository(session),
    )

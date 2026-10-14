"""Request-scoped services and access checks."""

import hmac
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.agent_service import AgentService
from app.application.services.auth_service import AuthService, OperatorContext
from app.application.services.call_service import CallService
from app.application.services.dialog_service import DialogService
from app.application.services.handoff_service import HandoffService
from app.application.services.integration_service import IntegrationService
from app.application.services.meeting_service import MeetingService
from app.application.services.metrics_service import MetricsService
from app.application.services.outbound_service import OutboundService
from app.application.services.voice_service import VoiceService
from app.application.use_cases.handle_channel_event import HandleChannelEvent
from app.container import Runtime, build_agent, build_calls, build_handoffs, build_meetings, build_metrics
from app.domain.errors import Unauthorized
from app.infrastructure.database.channel_repositories import (
    ConnectionRepository,
    InboundEventRepository,
    JobQueue,
    OperatorRepository,
    OutboundRepository,
    ReadRepository,
)
from app.infrastructure.database.dialog_queries import DialogQueries
from app.infrastructure.database.repositories import (
    BusinessRepository,
    ConversationRepository,
    CustomerRepository,
    HandoffRepository,
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
    handoff_requests: HandoffRepository
    operators: OperatorRepository
    connections: ConnectionRepository
    inbound_events: InboundEventRepository
    outbound_messages: OutboundRepository
    jobs: JobQueue
    reads: ReadRepository
    dialog_queries: DialogQueries
    auth: AuthService
    dialogs: DialogService
    outbound: OutboundService
    integrations: IntegrationService


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
    """Server-to-server calls carry `X-API-Key: $PLUMO_API_KEY`.

    The dashboard's Next.js server adds it; the browser never sees it. Unset key =
    open API, for local development only (APP_ENV=development). Webhooks and
    telephony have their own provider auth and skip this check.
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
    conversations = ConversationRepository(session)
    messages = MessageRepository(session)
    handoff_requests = HandoffRepository(session)
    operators = OperatorRepository(session)
    connections = ConnectionRepository(session)
    outbound_messages = OutboundRepository(session)
    jobs = JobQueue(session)
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
        conversations=conversations,
        messages=messages,
        knowledge=KnowledgeRepository(session),
        businesses=BusinessRepository(session),
        handoff_requests=handoff_requests,
        operators=operators,
        connections=connections,
        inbound_events=InboundEventRepository(session),
        outbound_messages=outbound_messages,
        jobs=jobs,
        reads=ReadRepository(session),
        dialog_queries=DialogQueries(session),
        auth=AuthService(operators, session_ttl_hours=runtime.settings.session_ttl_hours),
        dialogs=DialogService(conversations, handoff_requests, messages, outbound_messages),
        outbound=OutboundService(
            conversations=conversations,
            messages=messages,
            outbound=outbound_messages,
            connections=connections,
            jobs=jobs,
        ),
        integrations=IntegrationService(
            session=session,
            connections=connections,
            outbound=outbound_messages,
            gateway=runtime.channel_gateway,
            settings=runtime.settings,
        ),
    )


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header[:7].lower() == "bearer ":
        return header[7:].strip()
    return ""


async def current_operator(request: Request, services: Services = Depends(get_services)) -> OperatorContext:
    """The signed-in operator and the one business they may see.

    Every dashboard route takes the business from here, never from the request body
    or query: an id of another business's object answers 404.
    """

    return await services.auth.authenticate(bearer_token(request))

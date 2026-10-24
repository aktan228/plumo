"""Pending account, workspace and setup draft in one request transaction; verify email before issuing a session."""

import asyncio
import hashlib
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.auth_service import AuthService, LoginLimiter, hash_password
from app.domain.errors import RegistrationConflict
from app.domain.models import Business, Operator, utcnow
from app.infrastructure.database.channel_repositories import OperatorRepository
from app.infrastructure.database.models import OnboardingDraftRow
from app.infrastructure.database.repositories import BusinessRepository

# A basic per-client ceiling on the current single API process. The Next.js server
# supplies this header under its service key; callers cannot choose it in the body.
REGISTRATION_LIMITER = LoginLimiter(limit=10, window_s=3600)


class RegistrationService:
    def __init__(self, session: AsyncSession, auth: AuthService) -> None:
        self.session = session
        self.auth = auth

    async def register(self, *, name: str, email: str, password: str, locale: str, client_ip: str) -> Operator:
        key = hashlib.sha256(client_ip.encode()).hexdigest()
        REGISTRATION_LIMITER.check(key)
        REGISTRATION_LIMITER.failed(key)
        password_hash = await asyncio.to_thread(hash_password, password)
        now = utcnow()
        business = Business(
            id=uuid4(),
            name="My business" if locale == "en" else "Мой бизнес",
            description="",
            working_hours="",
            contacts={},
            rules="",
            profile={},
            created_at=now,
            updated_at=now,
        )
        await BusinessRepository(self.session).add(business)
        operator = await OperatorRepository(self.session).add_registered(
            business_id=business.id,
            email=email,
            password_hash=password_hash,
            display_name=name,
        )
        if operator is None:
            # The request dependency rolls back the whole transaction, including
            # the workspace just inserted above. The DB constraint settles races.
            raise RegistrationConflict("Account could not be created. Try signing in or use another email.")
        self.session.add(OnboardingDraftRow(business_id=business.id, step=0, data={}, created_at=now, updated_at=now))
        await self.session.flush()
        return operator

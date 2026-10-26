"""Single-use account links. Locks serialize mail issuance, verification, login and password reset."""

import asyncio
import hashlib
import logging
import secrets
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select, update

from app.application.services.auth_service import LoginLimiter, hash_password, token_hash
from app.domain.errors import InvalidAccountToken, ProviderUnavailable
from app.domain.models import utcnow
from app.infrastructure.auth_mail import AuthEmail
from app.infrastructure.database.models import AuthEmailTokenRow, OperatorRow, OperatorSessionRow

logger = logging.getLogger("plumo.auth_email")
EMAIL_LIMITER = LoginLimiter(limit=12, window_s=3600)
TOKEN_LIMITER = LoginLimiter(limit=30, window_s=900)


def limit_requests(limiter, client_ip):
    key = hashlib.sha256(client_ip.encode()).hexdigest()
    limiter.check(key)
    limiter.failed(key)


class AccountEmailService:
    def __init__(self, session, settings, mailer):
        self.session = session
        self.settings = settings
        self.mailer = mailer

    async def prepare(self, operator_id, purpose, locale, *, initial=False):
        operator = await self.session.scalar(select(OperatorRow).where(OperatorRow.id == operator_id).with_for_update())
        if operator is None or not operator.active or (purpose == "verify") == (operator.email_verified_at is not None):
            return None
        now = utcnow()
        if not initial:
            # Persistent recipient ceiling and cooldown survive restarts and multiple API processes.
            recent = await self.session.scalar(
                select(func.count())
                .select_from(AuthEmailTokenRow)
                .where(
                    AuthEmailTokenRow.operator_id == operator.id,
                    AuthEmailTokenRow.created_at > now - timedelta(hours=1),
                )
            )
            latest = await self.session.scalar(
                select(func.max(AuthEmailTokenRow.created_at)).where(AuthEmailTokenRow.operator_id == operator.id)
            )
            if recent >= 5 or (latest and latest > now - timedelta(seconds=60)):
                return None
        token = secrets.token_urlsafe(32)
        ident = uuid4()
        self.session.add(
            AuthEmailTokenRow(
                id=ident,
                operator_id=operator.id,
                purpose=purpose,
                token_hash=token_hash(token),
                created_at=now,
                expires_at=now + timedelta(hours=24) if purpose == "verify" else now + timedelta(minutes=30),
            )
        )
        await self.session.flush()
        page = "verify-email" if purpose == "verify" else "reset-password"
        # Fragments never reach web server access logs; GET only displays the confirmation form.
        link = f"{self.settings.auth_public_url.rstrip('/')}/{page}#token={token}"
        return AuthEmail(id=ident, recipient=operator.email, purpose=purpose, link=link, locale=locale)

    async def request(self, email, purpose, locale, client_ip):
        limit_requests(EMAIL_LIMITER, client_ip)
        self.mailer.check_config()
        operator_id = await self.session.scalar(
            select(OperatorRow.id).where(OperatorRow.email == email.strip().lower())
        )
        mail = await self.prepare(operator_id, purpose, locale) if operator_id else None
        await self.session.commit()
        await self.deliver(mail)
        # The same response for unknown, verified/unverified, disabled and throttled recipients.

    async def deliver(self, mail):
        if mail is None:
            return True
        try:
            await self.mailer.send(mail)
            return True
        except ProviderUnavailable:
            logger.warning("account_email_delivery_unavailable")
            return False

    async def consume(self, token, purpose, client_ip):
        limit_requests(TOKEN_LIMITER, client_ip)
        operator_id = await self.session.scalar(
            select(AuthEmailTokenRow.operator_id).where(
                AuthEmailTokenRow.token_hash == token_hash(token), AuthEmailTokenRow.purpose == purpose
            )
        )
        if operator_id is None:
            raise InvalidAccountToken("This link has expired or already been used. Request another link.")
        operator = await self.session.scalar(
            select(OperatorRow)
            .where(OperatorRow.id == operator_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = utcnow()
        row = await self.session.scalar(
            select(AuthEmailTokenRow)
            .where(
                AuthEmailTokenRow.token_hash == token_hash(token),
                AuthEmailTokenRow.purpose == purpose,
                AuthEmailTokenRow.used_at.is_(None),
                AuthEmailTokenRow.expires_at > now,
            )
            .with_for_update()
        )
        if row is None or not operator.active or (purpose == "verify") == (operator.email_verified_at is not None):
            raise InvalidAccountToken("This link has expired or already been used. Request another link.")
        await self.session.execute(
            update(AuthEmailTokenRow)
            .where(
                AuthEmailTokenRow.operator_id == operator.id,
                AuthEmailTokenRow.purpose == purpose,
                AuthEmailTokenRow.used_at.is_(None),
            )
            .values(used_at=now)
        )
        return operator

    async def verify(self, token, client_ip, auth, operators):
        operator = await self.consume(token, "verify", client_ip)
        operator.email_verified_at = utcnow()
        operator.updated_at = utcnow()
        await self.session.flush()
        return await auth.issue_session(await operators.get(operator.id))

    async def reset(self, token, password, client_ip):
        operator = await self.consume(token, "reset", client_ip)
        operator.password_hash = await asyncio.to_thread(hash_password, password)
        operator.updated_at = utcnow()
        await self.session.execute(
            update(OperatorSessionRow)
            .where(OperatorSessionRow.operator_id == operator.id, OperatorSessionRow.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await self.session.flush()

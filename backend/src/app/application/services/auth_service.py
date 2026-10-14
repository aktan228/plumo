"""Team sign-in for the dashboard. No public registration: operators are created on the server.

Passwords: scrypt from the standard library. Sessions: a random token in an
HttpOnly cookie set by the Next.js server; the database keeps only its sha256.
"""

import base64
import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from app.domain.errors import NotAuthenticated, TooManyRequests
from app.domain.models import Operator, utcnow

_N, _R, _P = 2**14, 8, 1
# Verified against when the email is unknown, so timing does not reveal who exists.
_DUMMY = None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class OperatorContext:
    """Who is calling and which business they may see. Comes from the session, never from the request."""

    operator_id: UUID
    business_id: UUID
    email: str
    display_name: str
    session_expires_at: object


@dataclass(frozen=True, slots=True)
class LoginResult:
    token: str
    expires_at: object
    operator: Operator


class LoginLimiter:
    """At most `limit` failed sign-ins per email in `window_s`. In memory: one API process on the stand."""

    def __init__(self, limit: int = 8, window_s: float = 900.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._failures: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        now = time.monotonic()
        recent = [stamp for stamp in self._failures[key] if now - stamp < self.window_s]
        self._failures[key] = recent
        if len(recent) >= self.limit:
            raise TooManyRequests("too many failed sign-in attempts; try again later")

    def failed(self, key: str) -> None:
        self._failures[key].append(time.monotonic())

    def succeeded(self, key: str) -> None:
        self._failures.pop(key, None)


LIMITER = LoginLimiter()


class AuthService:
    def __init__(self, operators, *, session_ttl_hours: float = 12.0, limiter: LoginLimiter = LIMITER) -> None:
        self.operators = operators
        self.session_ttl = timedelta(hours=session_ttl_hours)
        self.limiter = limiter

    async def login(self, email: str, password: str) -> LoginResult:
        key = email.strip().lower()
        self.limiter.check(key)
        found = await self.operators.get_with_hash(key)
        if found is None:
            verify_password(password, _dummy_hash())
            self.limiter.failed(key)
            raise NotAuthenticated("wrong email or password")
        operator, stored = found
        if not verify_password(password, stored) or not operator.active:
            self.limiter.failed(key)
            raise NotAuthenticated("wrong email or password")
        self.limiter.succeeded(key)
        token = secrets.token_urlsafe(32)
        expires_at = utcnow() + self.session_ttl
        await self.operators.add_session(operator.id, token_hash(token), expires_at)
        return LoginResult(token=token, expires_at=expires_at, operator=operator)

    async def authenticate(self, token: str) -> OperatorContext:
        if not token:
            raise NotAuthenticated("sign in to continue")
        found = await self.operators.find_session(token_hash(token))
        if found is None:
            raise NotAuthenticated("the session has expired; sign in again")
        session, operator = found
        return OperatorContext(
            operator_id=operator.id,
            business_id=operator.business_id,
            email=operator.email,
            display_name=operator.display_name,
            session_expires_at=session.expires_at,
        )

    async def logout(self, token: str) -> None:
        if token:
            await self.operators.revoke_session(token_hash(token))


def _dummy_hash() -> str:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password(secrets.token_urlsafe(12))
    return _DUMMY

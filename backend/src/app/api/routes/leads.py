"""Pilot request form of the website. Called by the Next.js server (service key), not by a session."""

import re

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.api.deps import Services, get_services
from app.api.routes.auth import client_ip
from app.application.services.auth_service import LoginLimiter
from app.application.services.leads import store_lead

router = APIRouter(prefix="/leads", tags=["leads"])

# Per client address, in process memory: like the registration limit, one API process on the stand.
LIMITER = LoginLimiter(limit=5, window_s=3600.0)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class LeadIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")
    source: str = Field(pattern=r"^(landing|wizard)$")
    name: str = Field(min_length=1, max_length=100)
    company: str = Field(default="", max_length=200)
    email: EmailStr
    message: str = Field(default="", max_length=2000)
    plan: str = Field(default="", max_length=200)
    locale: str = Field(default="ru", pattern=r"^(ru|en|ky)$")

    @field_validator("name", "company", "plan")
    @classmethod
    def one_line(cls, value: str) -> str:
        if _CONTROL.search(value) or "\n" in value:
            raise ValueError("control characters are not allowed")
        return value


class LeadOut(BaseModel):
    number: int
    status: str = "accepted"


@router.post("", response_model=LeadOut, status_code=201, summary="Заявка на пилот с сайта")
async def create_lead(body: LeadIn, request: Request, services: Services = Depends(get_services)) -> LeadOut:
    ip = client_ip(request)
    LIMITER.check(ip)
    number, created = await store_lead(services.session, {**body.model_dump(), "email": str(body.email).lower()})
    await services.session.commit()
    if created:
        LIMITER.failed(ip)  # counts accepted requests, not failures: the class only keeps a sliding window
    return LeadOut(number=number)

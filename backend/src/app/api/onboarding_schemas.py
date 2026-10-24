"""Bounded, typed wizard snapshots. Tenant identity always comes from the session."""

import base64
import binascii
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def valid_text(cls, value):
        def check(item):
            if isinstance(item, str):
                if "\0" in item:
                    raise ValueError("NUL is not allowed in text")
                item.encode("utf-8")
            elif isinstance(item, dict):
                for key, child in item.items():
                    check(key)
                    check(child)
            elif isinstance(item, list):
                for child in item:
                    check(child)

        check(value)
        return value


class AgentSettings(StrictModel):
    purpose: Literal["sales", "support"] = "sales"
    company: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=3000)
    audience: str = Field(default="", max_length=2000)
    color: str = Field(default="#2b55ff", pattern=r"^#[0-9a-fA-F]{6}$")
    logo: str = Field(default="", max_length=1_333_400)
    logoName: str = Field(default="", max_length=255)
    name: str = Field(default="Plumo", max_length=60)
    tone: Literal["friendly", "formal"] = "friendly"
    language: Literal["ru", "en"] = "ru"
    greeting: str = Field(default="", max_length=1000)
    goal: str = Field(default="", max_length=1500)
    fallback: str = Field(default="", max_length=1000)

    @field_validator("logo")
    @classmethod
    def safe_logo(cls, value):
        if not value:
            return value
        header, separator, payload = value.partition(",")
        if not separator or header not in ("data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"):
            raise ValueError("logo must be an inline PNG, JPEG or WebP")
        try:
            raw = base64.b64decode(payload, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("invalid image encoding") from exc
        valid = (
            (header == "data:image/png;base64" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
            or (header == "data:image/jpeg;base64" and raw.startswith(b"\xff\xd8\xff"))
            or (header == "data:image/webp;base64" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP")
        )
        if not valid or len(raw) > 1_000_000:
            raise ValueError("invalid image or image exceeds 1 MB")
        return value


SourceKind = Literal["website", "instagram", "text", "file", "faq"]


class WizardSource(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    kind: SourceKind
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=100_000)
    question: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_content(self):
        if (
            "\0" in self.content
            or not self.content.strip()
            or len((self.content + (self.question or "")).encode()) > 100_000
        ):
            raise ValueError("source must be nonempty UTF-8 text up to 100 KB")
        if self.kind == "faq" and not (self.question or "").strip():
            raise ValueError("FAQ needs a question")
        if self.kind in ("website", "instagram"):
            parts = urlsplit(self.content)
            host = (parts.hostname or "").lower()
            if (
                parts.scheme not in ("http", "https")
                or "." not in host
                or parts.username
                or parts.password
                or any(c.isspace() for c in self.content)
            ):
                raise ValueError("invalid source URL")
            if self.kind == "instagram" and host != "instagram.com" and not host.endswith(".instagram.com"):
                raise ValueError("Instagram source needs instagram.com")
        return self


class SourceEntry(StrictModel):
    kind: SourceKind = "website"
    value: str = Field(default="", max_length=100_000)
    question: str = Field(default="", max_length=300)

    @field_validator("value")
    @classmethod
    def bound_text(cls, value):
        if len(value.encode()) > 100_000 or "\0" in value:
            raise ValueError("pending text exceeds 100 KB or contains NUL")
        return value


class PricingChoice(StrictModel):
    choice: Literal["start", "business", "custom", "demo"]
    volume: int = Field(ge=1000, le=10000, multiple_of=500)
    billing: Literal["quarter", "month"]
    voice: bool


class WizardData(StrictModel):
    settings: AgentSettings = Field(default_factory=AgentSettings)
    sources: list[WizardSource] = Field(default_factory=list, max_length=10)
    channel: int = Field(default=0, ge=0, le=4)
    pricing: PricingChoice | None = None
    entry: SourceEntry = Field(default_factory=SourceEntry)

    @model_validator(mode="after")
    def sources_bounded(self):
        if len({source.id for source in self.sources}) != len(self.sources):
            raise ValueError("source ids must be unique")
        if sum(len((s.content + (s.question or "")).encode()) for s in self.sources) > 200_000:
            raise ValueError("sources exceed 200 KB")
        return self


class SaveWizardIn(StrictModel):
    version: int = Field(ge=0, le=2_000_000_000)
    step: int = Field(ge=0, le=5)
    data: WizardData


class CompleteWizardIn(StrictModel):
    version: int = Field(ge=0, le=2_000_000_000)


class WizardOut(BaseModel):
    business_id: UUID
    step: int
    data: WizardData | None
    version: int
    completed_at: datetime | None
    updated_at: datetime

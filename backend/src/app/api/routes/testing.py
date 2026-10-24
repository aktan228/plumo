"""Authenticated sandbox endpoints. The caller cannot select a tenant or customer."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import Services, current_operator, get_services
from app.application.services.auth_service import OperatorContext
from app.application.services.test_chat_service import TestChatService

router = APIRouter(prefix="/testing/sessions", tags=["testing"])


class CreateTestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID


class TestMessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, value):
        if not value.strip() or "\0" in value:
            raise ValueError("message is empty or invalid")
        return value.strip()


@router.get("")
async def list_tests(operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    return await TestChatService(services.session, services.runtime).listing(operator.business_id)


@router.post("")
async def create_test(
    body: CreateTestIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
):
    return await TestChatService(services.session, services.runtime).create(operator.business_id, body.id)


@router.get("/{ident}")
async def get_test(
    ident: UUID, operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)
):
    return await TestChatService(services.session, services.runtime).detail(operator.business_id, ident)


@router.post("/{ident}/messages")
async def post_test(
    ident: UUID,
    body: TestMessageIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
):
    return await TestChatService(services.session, services.runtime).send(operator.business_id, ident, body)

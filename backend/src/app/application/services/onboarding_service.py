"""Tenant-scoped setup snapshots, optimistic concurrency and explicit completion."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.api.onboarding_schemas import WizardData
from app.application.services.publish_knowledge import publish_knowledge
from app.domain.errors import BusinessNotFound, InvalidMessage, VersionConflict
from app.domain.models import utcnow
from app.infrastructure.database.models import BusinessRow, OnboardingDraftRow


class OnboardingService:
    def __init__(self, session):
        self.session = session

    async def get(self, business_id, *, lock=False):
        now = utcnow()
        await self.session.execute(
            insert(OnboardingDraftRow)
            .values(business_id=business_id, step=0, data={}, version=0, created_at=now, updated_at=now)
            .on_conflict_do_nothing(index_elements=[OnboardingDraftRow.business_id])
        )
        stmt = select(OnboardingDraftRow).where(OnboardingDraftRow.business_id == business_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self.session.scalar(stmt)

    async def save(self, business_id, body):
        row = await self.get(business_id, lock=True)
        data = body.data.model_dump(exclude_none=True)
        # An acknowledged or lost-response retry is safe and does not clear completion.
        if row.data == data and row.step == body.step:
            return row
        if row.version != body.version:
            raise VersionConflict("The setup changed in another tab. Load its current version before saving.")
        row.step, row.data = body.step, data
        row.version += 1
        row.completed_at = None
        row.updated_at = utcnow()
        await self.session.flush()
        return row

    async def complete(self, business_id, version):
        row = await self.get(business_id, lock=True)
        business = await self.session.scalar(select(BusinessRow).where(BusinessRow.id == business_id).with_for_update())
        if business is None:
            raise BusinessNotFound("business not found")
        publication = (business.profile or {}).get("onboarding_publication", {})
        if (
            row.completed_at is not None
            and publication.get("draft_version") == row.version
            and version in (row.version, row.version - 1)
        ):
            return row
        if row.version != version:
            raise VersionConflict("The setup changed in another tab. Load its current version before completing.")
        data = WizardData.model_validate(row.data)
        settings = data.settings
        if (
            not data.sources
            or not all(
                value.strip()
                for value in (
                    settings.company,
                    settings.description,
                    settings.name,
                    settings.greeting,
                    settings.goal,
                    settings.fallback,
                )
            )
            or data.entry.value.strip()
            or data.entry.question.strip()
        ):
            raise InvalidMessage("Add sources and fill in business, agent and script fields before completing.")
        knowledge_count = await publish_knowledge(self.session, business_id, data)
        now = utcnow()
        business.name = settings.company.strip()
        business.description = settings.description.strip()
        # Preserve other business fields and provider configuration. This action does not enable any channel.
        business.contacts = {**(business.contacts or {}), "assistant_name": settings.name.strip()}
        business.profile = {
            **(business.profile or {}),
            "onboarding": data.model_dump(exclude_none=True, exclude={"settings": {"logo"}}),
            "agent_settings": settings.model_dump(exclude={"logo", "logoName", "color"}),
            "onboarding_publication": {"draft_version": row.version + 1, "knowledge_count": knowledge_count},
        }
        business.updated_at = now
        row.step, row.completed_at, row.updated_at = 5, now, now
        row.version += 1
        await self.session.flush()
        return row

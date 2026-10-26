"""Wizard snapshots for the signed-in operator's business; no tenant selector is accepted."""

from fastapi import APIRouter, Depends

from app.api.deps import Services, current_operator, get_services
from app.api.onboarding_schemas import CompleteWizardIn, SaveWizardIn, WizardOut
from app.application.services.auth_service import OperatorContext
from app.application.services.onboarding_service import OnboardingService

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


async def output(row, services):
    business = await services.businesses.get(row.business_id)
    publication = (business.profile or {}).get("onboarding_publication", {}) if business else {}
    return WizardOut(
        business_id=row.business_id,
        step=row.step,
        data=row.data or None,
        version=row.version,
        published=publication.get("draft_version") == row.version and row.completed_at is not None,
        knowledge_count=publication.get("knowledge_count", 0),
        completed_at=row.completed_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=WizardOut, summary="Загрузить настройки мастера своего бизнеса")
async def get_draft(operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services)):
    return await output(await OnboardingService(services.session).get(operator.business_id), services)


@router.patch("", response_model=WizardOut, summary="Сохранить шаги и материалы мастера")
async def save_draft(
    body: SaveWizardIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
):
    row = await OnboardingService(services.session).save(operator.business_id, body)
    result = await output(row, services)
    await services.session.commit()
    return result


@router.post("/complete", response_model=WizardOut, summary="Завершить настройку и сохранить карточку бизнеса")
async def complete_draft(
    body: CompleteWizardIn,
    operator: OperatorContext = Depends(current_operator),
    services: Services = Depends(get_services),
):
    row = await OnboardingService(services.session).complete(operator.business_id, body.version)
    result = await output(row, services)
    await services.session.commit()
    return result

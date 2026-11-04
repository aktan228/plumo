"""Read-only scenario history. All editing and publication use shared onboarding."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import Services, current_operator, get_services
from app.application.services.auth_service import OperatorContext
from app.domain.agent_settings import published_settings, scenario_snapshot
from app.infrastructure.database.models import BusinessRow, ScenarioRevisionRow

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("")
async def scenarios(
    before: int | None = Query(default=None, ge=1, le=2_000_000_000),
    operator: OperatorContext = Depends(current_operator), services: Services = Depends(get_services),
):
    business = await services.session.get(BusinessRow, operator.business_id)
    profile = business.profile or {}
    stmt = select(ScenarioRevisionRow).where(ScenarioRevisionRow.business_id == operator.business_id)
    if before is not None:
        stmt = stmt.where(ScenarioRevisionRow.publication_version < before)
    rows = (await services.session.scalars(stmt.order_by(ScenarioRevisionRow.publication_version.desc()).limit(21))).all()
    return {
        "publication_version": profile.get("onboarding_publication", {}).get("draft_version"),
        "settings": scenario_snapshot(published_settings(profile)),
        "items": [{"publication_version": row.publication_version, "settings": row.settings,
                   "published_at": row.published_at, "captured_at": row.captured_at} for row in rows[:20]],
        "next_before": rows[19].publication_version if len(rows) > 20 else None,
    }

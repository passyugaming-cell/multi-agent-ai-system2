import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.owner_ai.recommendations import RecommendationService
from app.agents.owner_ai.reports import ReportGenerator
from app.agents.owner_ai.approvals import ApprovalRouter
from app.agents.owner_ai.schemas import RecommendationStatus
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate
from app.core.exceptions import AppError


@pytest.mark.asyncio
async def test_recommendations_and_reports_flow(db_session: AsyncSession):
    repo = TenantRepository(db_session)
    tenant = await repo.create(TenantCreate(name="Report Tenant", slug="report-tenant"))
    await db_session.commit()

    rec_service = RecommendationService(db_session)

    # 1. Create Recommendation
    rec = await rec_service.create_recommendation(
        tenant_id=tenant.id,
        title="Increase sales follow-ups",
        problem="Lower conversion rate this month",
        reasoning_summary="Lead response time increased from 5 mins to 45 mins",
        expected_benefit="Improve conversion by 12%",
        suggested_action="Assign AI Sales follow-up task to new qualified leads",
        evidence=["Lead response time audit log"],
        risk="LOW",
        confidence=0.92,
    )

    assert rec.status == RecommendationStatus.PROPOSED
    assert rec.confidence == 0.92

    # 2. Update Recommendation status
    updated = await rec_service.update_status(
        tenant_id=tenant.id,
        recommendation_id=rec.recommendation_id,
        new_status=RecommendationStatus.ACCEPTED,
    )
    assert updated.status == RecommendationStatus.ACCEPTED

    # 3. Generate Daily Brief
    report_gen = ReportGenerator(db_session)
    brief = await report_gen.generate_daily_brief(tenant.id)
    assert brief.tenant_id == tenant.id
    assert brief.health.score >= 0.0
    assert len(brief.key_facts) > 0

    # 4. Verify Approval Router self-approval restriction
    router = ApprovalRouter(db_session)
    with pytest.raises(AppError) as exc_info:
        router.validate_owner_authority(is_high_risk=True, action_type="change_official_price")
    assert "forbidden" in str(exc_info.value).lower()

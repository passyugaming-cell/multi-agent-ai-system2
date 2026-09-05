import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, List
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.onboarding import OnboardingChecklist
from app.database.models.billing import Payment, Invoice
from app.database.models.tenant import Tenant
from app.database.models.customer import Customer
from app.analytics.schemas import SalesAnalyticsSchema, SalesFunnelStageSchema
from app.analytics.metrics import safe_decimal


class SalesAnalyticsService:
    """Service for computing sales funnel and conversion analytics."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_sales_analytics(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> SalesAnalyticsSchema:
        now = datetime.now(timezone.utc)
        if not period_end:
            period_end = now
        if not period_start:
            period_start = period_end - timedelta(days=30)

        tenant_filter = [Tenant.id == tenant_id] if tenant_id else []
        ob_filter = [OnboardingChecklist.tenant_id == tenant_id] if tenant_id else []

        # 1. Funnel counts based on actual database entities
        # Lead: Customers / Onboarding checklists initiated
        stmt_leads = select(func.count(OnboardingChecklist.id)).where(and_(*ob_filter))
        total_leads = (await self.session.execute(stmt_leads)).scalar() or 0

        # Qualified: Onboarding completed items
        stmt_qual = select(func.count(OnboardingChecklist.id)).where(
            and_(
                OnboardingChecklist.status == "COMPLETED",
                *ob_filter
            )
        )
        qualified_leads = (await self.session.execute(stmt_qual)).scalar() or 0

        # Consultations: Onboarding checklist items with completion percentage >= 50%
        stmt_consult = select(func.count(OnboardingChecklist.id)).where(
            and_(
                OnboardingChecklist.completion_percentage >= 50.0,
                *ob_filter
            )
        )
        consultations = (await self.session.execute(stmt_consult)).scalar() or 0

        # Proposals: Onboarding completed with readiness check >= 80%
        stmt_prop = select(func.count(OnboardingChecklist.id)).where(
            and_(
                OnboardingChecklist.completion_percentage >= 80.0,
                *ob_filter
            )
        )
        proposals = (await self.session.execute(stmt_prop)).scalar() or 0

        # Payments: Paid invoices/payments
        stmt_pmts = select(func.count(func.distinct(Invoice.tenant_id))).where(
            and_(
                Invoice.status == "PAID",
                *[Invoice.tenant_id == tenant_id] if tenant_id else []
            )
        )
        payments_count = (await self.session.execute(stmt_pmts)).scalar() or 0

        # Onboarding: Completed onboarding checklists
        stmt_onb = select(func.count(OnboardingChecklist.id)).where(
            and_(
                OnboardingChecklist.status == "COMPLETED",
                *ob_filter
            )
        )
        onboardings = (await self.session.execute(stmt_onb)).scalar() or 0

        # Active: Active tenants (lifecycle_state == 'READY' or 'ACTIVE')
        stmt_active = select(func.count(Tenant.id)).where(
            and_(
                Tenant.lifecycle_state.in_(["READY", "ACTIVE"]),
                *tenant_filter
            )
        )
        active_clients = (await self.session.execute(stmt_active)).scalar() or 0

        # Build funnel stages deterministically
        raw_stages = [
            ("Lead", total_leads),
            ("Qualified", min(total_leads, qualified_leads)),
            ("Consultation", min(qualified_leads, consultations)),
            ("Proposal", min(consultations, proposals)),
            ("Payment", min(proposals, max(payments_count, onboardings))),
            ("Onboarding", max(onboardings, payments_count)),
            ("Active", max(active_clients, 0)),
        ]

        funnel_stages: List[SalesFunnelStageSchema] = []
        prev_cnt = 0
        for idx, (stage_name, cnt) in enumerate(raw_stages):
            if idx == 0:
                conv_rate = 100.0 if cnt > 0 else 0.0
                drop_cnt = 0
                drop_rate = 0.0
            else:
                conv_rate = round((cnt / prev_cnt * 100.0), 2) if prev_cnt > 0 else 0.0
                drop_cnt = max(0, prev_cnt - cnt)
                drop_rate = round((drop_cnt / prev_cnt * 100.0), 2) if prev_cnt > 0 else 0.0

            funnel_stages.append(
                SalesFunnelStageSchema(
                    stage_name=stage_name,
                    count=cnt,
                    conversion_rate=conv_rate,
                    drop_off_count=drop_cnt,
                    drop_off_rate=drop_rate,
                )
            )
            prev_cnt = cnt

        overall_conversion_rate = round((active_clients / total_leads * 100.0), 2) if total_leads > 0 else 0.0

        # 2. Average deal value
        stmt_deal = select(func.avg(Invoice.total)).where(
            and_(
                Invoice.status == "PAID",
                *[Invoice.tenant_id == tenant_id] if tenant_id else []
            )
        )
        avg_deal = safe_decimal((await self.session.execute(stmt_deal)).scalar()).quantize(Decimal("0.01"))

        # 3. Revenue by source (if metadata contains lead source)
        revenue_by_source: Dict[str, Decimal] = {"UNKNOWN": Decimal("0.00")}
        stmt_src = select(
            Invoice.metadata_,
            Invoice.total
        ).where(
            and_(
                Invoice.status == "PAID",
                *[Invoice.tenant_id == tenant_id] if tenant_id else []
            )
        )
        src_rows = (await self.session.execute(stmt_src)).all()
        for meta, tot in src_rows:
            amt = safe_decimal(tot)
            src = "UNKNOWN"
            if isinstance(meta, dict) and "source" in meta and meta["source"]:
                src = str(meta["source"]).upper()
            revenue_by_source[src] = revenue_by_source.get(src, Decimal("0.00")) + amt

        return SalesAnalyticsSchema(
            total_leads=total_leads,
            qualified_leads=qualified_leads,
            consultations=consultations,
            proposals=proposals,
            payments=payments_count,
            onboardings=onboardings,
            active_clients=active_clients,
            overall_conversion_rate=overall_conversion_rate,
            average_deal_value=avg_deal,
            sales_cycle_days=7.0,  # Baseline onboarding duration
            revenue_by_source=revenue_by_source,
            funnel_stages=funnel_stages,
            generated_at=now,
        )

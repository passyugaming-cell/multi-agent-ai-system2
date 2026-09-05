import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.billing import Subscription, Plan, SubscriptionHistory, Payment
from app.analytics.schemas import SubscriptionAnalyticsSchema


class SubscriptionAnalyticsService:
    """Service for computing subscription lifecycle and cohort analytics."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_subscription_analytics(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> SubscriptionAnalyticsSchema:
        now = datetime.now(timezone.utc)
        if not period_end:
            period_end = now
        if not period_start:
            period_start = period_end - timedelta(days=30)

        sub_filter = [Subscription.tenant_id == tenant_id] if tenant_id else []
        hist_filter = [SubscriptionHistory.tenant_id == tenant_id] if tenant_id else []

        # 1. Current Subscription Status Counts
        stmt_status = select(
            Subscription.status,
            func.count(Subscription.id)
        ).where(and_(*sub_filter)).group_by(Subscription.status)
        status_rows = (await self.session.execute(stmt_status)).all()

        counts = {st: cnt for st, cnt in status_rows}
        active_subs = counts.get("ACTIVE", 0)
        trial_subs = counts.get("TRIALING", 0)
        suspended_subs = counts.get("SUSPENDED", 0)
        expired_subs = counts.get("EXPIRED", 0)

        # 2. Plan Distribution
        stmt_plan = select(
            Plan.code,
            func.count(Subscription.id)
        ).join(
            Subscription, Subscription.plan_id == Plan.id
        ).where(and_(*sub_filter)).group_by(Plan.code)
        plan_rows = (await self.session.execute(stmt_plan)).all()
        distribution = {code: cnt for code, cnt in plan_rows}

        # 3. Transitions in Period (Upgrades, Downgrades, Cancellations, Conversions)
        stmt_transitions = select(
            SubscriptionHistory.previous_status,
            SubscriptionHistory.new_status,
            func.count(SubscriptionHistory.id)
        ).where(
            and_(
                SubscriptionHistory.created_at >= period_start,
                SubscriptionHistory.created_at <= period_end,
                *hist_filter,
            )
        ).group_by(SubscriptionHistory.previous_status, SubscriptionHistory.new_status)

        trans_rows = (await self.session.execute(stmt_transitions)).all()
        upgrades = 0
        downgrades = 0
        cancellations = 0
        trial_conversions = 0

        for prev_st, new_st, cnt in trans_rows:
            p_upper = prev_st.upper() if prev_st else ""
            n_upper = new_st.upper() if new_st else ""

            if p_upper == "TRIALING" and n_upper == "ACTIVE":
                trial_conversions += cnt
            elif n_upper == "CANCELLED":
                cancellations += cnt

        # 4. Failed renewals & Successful Renewals
        stmt_renewals = select(
            Payment.status,
            func.count(Payment.id)
        ).where(
            and_(
                Payment.created_at >= period_start,
                Payment.created_at <= period_end,
                *[Payment.tenant_id == tenant_id] if tenant_id else [],
            )
        ).group_by(Payment.status)

        pmt_rows = (await self.session.execute(stmt_renewals)).all()
        renewals = 0
        failed_renewals = 0
        for st, cnt in pmt_rows:
            st_u = st.upper() if st else ""
            if st_u in ["SUCCESSFUL", "PAID"]:
                renewals += cnt
            elif st_u == "FAILED":
                failed_renewals += cnt

        # 5. Rates Calculation
        total_subs = active_subs + trial_subs + suspended_subs + expired_subs
        churn_rate = round((cancellations / total_subs * 100.0), 2) if total_subs > 0 else 0.0
        retention_rate = round((100.0 - churn_rate), 2)
        trial_conversion_rate = round((trial_conversions / (trial_subs + trial_conversions) * 100.0), 2) if (trial_subs + trial_conversions) > 0 else 100.0

        return SubscriptionAnalyticsSchema(
            active_subscriptions=active_subs,
            trial_subscriptions=trial_subs,
            trial_conversion_rate=trial_conversion_rate,
            upgrades_count=upgrades,
            downgrades_count=downgrades,
            cancellations_count=cancellations,
            expired_subscriptions=expired_subs,
            suspended_subscriptions=suspended_subs,
            renewals_count=renewals,
            failed_renewals_count=failed_renewals,
            churn_rate=churn_rate,
            retention_rate=retention_rate,
            subscription_distribution_by_plan=distribution,
            generated_at=now,
        )

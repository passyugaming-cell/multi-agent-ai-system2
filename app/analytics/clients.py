import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.database.models.billing import Subscription, Plan, SubscriptionHistory
from app.agents.owner_ai.health import ClientHealthCalculator
from app.analytics.schemas import ClientAnalyticsSchema
from app.analytics.metrics import calculate_change_pct


class ClientAnalyticsService:
    """Service for computing client and subscription lifecycle analytics."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_client_analytics(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> ClientAnalyticsSchema:
        now = datetime.now(timezone.utc)
        if not period_end:
            period_end = now
        if not period_start:
            period_start = period_end - timedelta(days=30)

        period_duration = period_end - period_start
        prior_period_start = period_start - period_duration

        tenant_filter = [Tenant.id == tenant_id] if tenant_id else []
        sub_filter = [Subscription.tenant_id == tenant_id] if tenant_id else []

        # 1. Total Tenants/Clients
        stmt_total = select(func.count(Tenant.id))
        if tenant_filter:
            stmt_total = stmt_total.where(Tenant.id == tenant_id)
        total_clients = (await self.session.execute(stmt_total)).scalar() or 0

        # 2. Lifecycle breakdown (using Tenant.lifecycle_state)
        stmt_lifecycle = select(
            Tenant.lifecycle_state,
            func.count(Tenant.id)
        ).group_by(Tenant.lifecycle_state)
        if tenant_filter:
            stmt_lifecycle = stmt_lifecycle.where(Tenant.id == tenant_id)
        lc_rows = (await self.session.execute(stmt_lifecycle)).all()
        clients_by_lifecycle: Dict[str, int] = {lc or "UNKNOWN": cnt for lc, cnt in lc_rows}

        # Active, Trial, Suspended, Expired clients
        stmt_sub_status = select(
            Subscription.status,
            func.count(func.distinct(Subscription.tenant_id))
        ).group_by(Subscription.status)
        if sub_filter:
            stmt_sub_status = stmt_sub_status.where(Subscription.tenant_id == tenant_id)
        sub_rows = (await self.session.execute(stmt_sub_status)).all()

        sub_status_counts = {status: cnt for status, cnt in sub_rows}
        active_clients = sub_status_counts.get("ACTIVE", 0)
        trial_clients = sub_status_counts.get("TRIALING", 0)
        suspended_clients = sub_status_counts.get("SUSPENDED", 0)
        expired_clients = sub_status_counts.get("EXPIRED", 0)
        active_subscriptions = active_clients + trial_clients

        # 3. New clients in period
        stmt_new = select(func.count(Tenant.id)).where(
            and_(
                Tenant.created_at >= period_start,
                Tenant.created_at <= period_end,
                *tenant_filter,
            )
        )
        new_clients = (await self.session.execute(stmt_new)).scalar() or 0

        stmt_prior_new = select(func.count(Tenant.id)).where(
            and_(
                Tenant.created_at >= prior_period_start,
                Tenant.created_at < period_start,
                *tenant_filter,
            )
        )
        prior_new_clients = (await self.session.execute(stmt_prior_new)).scalar() or 0
        client_growth_pct = calculate_change_pct(new_clients, prior_new_clients)

        # 4. Churned and Reactivated clients in period (from SubscriptionHistory)
        stmt_churn = select(func.count(func.distinct(SubscriptionHistory.tenant_id))).where(
            and_(
                SubscriptionHistory.created_at >= period_start,
                SubscriptionHistory.created_at <= period_end,
                SubscriptionHistory.new_status.in_(["CANCELLED", "EXPIRED"]),
                *[SubscriptionHistory.tenant_id == tenant_id] if tenant_id else [],
            )
        )
        churned_clients = (await self.session.execute(stmt_churn)).scalar() or 0

        stmt_reactivated = select(func.count(func.distinct(SubscriptionHistory.tenant_id))).where(
            and_(
                SubscriptionHistory.created_at >= period_start,
                SubscriptionHistory.created_at <= period_end,
                SubscriptionHistory.previous_status.in_(["CANCELLED", "EXPIRED", "SUSPENDED"]),
                SubscriptionHistory.new_status == "ACTIVE",
                *[SubscriptionHistory.tenant_id == tenant_id] if tenant_id else [],
            )
        )
        reactivated_clients = (await self.session.execute(stmt_reactivated)).scalar() or 0

        # 5. Clients by Plan
        stmt_plan = select(
            Plan.code,
            func.count(func.distinct(Subscription.tenant_id))
        ).join(
            Subscription, Subscription.plan_id == Plan.id
        ).where(
            and_(
                Subscription.status.in_(["ACTIVE", "TRIALING"]),
                *sub_filter,
            )
        ).group_by(Plan.code)
        plan_rows = (await self.session.execute(stmt_plan)).all()
        clients_by_plan = {code: cnt for code, cnt in plan_rows}

        # 6. Health Calculation (REUSING ClientHealthCalculator)
        at_risk_clients = 0
        health_summary: Dict[str, Any] = {
            "HEALTHY": 0,
            "NEEDS_ATTENTION": 0,
            "AT_RISK": 0,
            "CRITICAL": 0,
            "individual_results": {},
        }

        if tenant_id:
            h_res = await ClientHealthCalculator.calculate(self.session, tenant_id)
            health_summary[h_res.category] = 1
            health_summary["individual_results"][str(tenant_id)] = h_res.model_dump(mode="json")
            if h_res.category in ["AT_RISK", "CRITICAL"]:
                at_risk_clients = 1
        else:
            stmt_active_tenants = select(Tenant.id).where(Tenant.is_active.is_(True))
            tenant_ids = (await self.session.execute(stmt_active_tenants)).scalars().all()
            for t_id in tenant_ids:
                h_res = await ClientHealthCalculator.calculate(self.session, t_id)
                cat = h_res.category
                health_summary[cat] = health_summary.get(cat, 0) + 1
                if cat in ["AT_RISK", "CRITICAL"]:
                    at_risk_clients += 1

        return ClientAnalyticsSchema(
            total_clients=total_clients,
            active_clients=active_clients,
            new_clients=new_clients,
            churned_clients=churned_clients,
            reactivated_clients=reactivated_clients,
            trial_clients=trial_clients,
            active_subscriptions=active_subscriptions,
            suspended_clients=suspended_clients,
            expired_clients=expired_clients,
            at_risk_clients=at_risk_clients,
            clients_by_plan=clients_by_plan,
            clients_by_lifecycle=clients_by_lifecycle,
            client_growth_pct=client_growth_pct,
            health_summary=health_summary,
            generated_at=now,
        )

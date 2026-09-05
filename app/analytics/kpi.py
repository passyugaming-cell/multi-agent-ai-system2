import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import KPISchema
from app.analytics.metrics import safe_decimal, calculate_change_pct, determine_trend_direction, determine_kpi_status
from app.analytics.financial import FinancialAnalyticsService
from app.analytics.clients import ClientAnalyticsService
from app.analytics.ai import AIAnalyticsService


class KPIService:
    """Centralized KPI computation service."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_kpis(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period: str = "30d",
    ) -> List[KPISchema]:
        now = datetime.now(timezone.utc)
        days = 30
        if period == "7d":
            days = 7
        elif period == "24h":
            days = 1

        period_end = now
        period_start = period_end - timedelta(days=days)

        fin_svc = FinancialAnalyticsService(self.session)
        fin_data = await fin_svc.get_financial_analytics(tenant_id, period_start, period_end)

        client_svc = ClientAnalyticsService(self.session)
        client_data = await client_svc.get_client_analytics(tenant_id, period_start, period_end)

        ai_svc = AIAnalyticsService(self.session)
        ai_data = await ai_svc.get_ai_analytics(tenant_id, period_start, period_end)

        # Build list of core KPIs
        kpis: List[KPISchema] = []

        # 1. MRR
        kpis.append(
            KPISchema(
                key="mrr",
                name="Monthly Recurring Revenue",
                value=fin_data.mrr,
                unit="IDR",
                period=period,
                previous_value=Decimal("0.00"),
                change=fin_data.mrr,
                change_percentage=fin_data.revenue_growth_pct,
                trend="UP" if fin_data.revenue_growth_pct > 0 else ("DOWN" if fin_data.revenue_growth_pct < 0 else "STABLE"),
                status="HEALTHY" if fin_data.mrr > Decimal("0") else "WARNING",
                source="billing",
                generated_at=now,
            )
        )

        # 2. Total Revenue
        kpis.append(
            KPISchema(
                key="total_revenue",
                name="Total Revenue",
                value=fin_data.total_revenue,
                unit="IDR",
                period=period,
                previous_value=Decimal("0.00"),
                change=fin_data.total_revenue,
                change_percentage=fin_data.revenue_growth_pct,
                trend="UP" if fin_data.revenue_growth_pct > 0 else "STABLE",
                status="HEALTHY",
                source="billing",
                generated_at=now,
            )
        )

        # 3. Active Clients
        kpis.append(
            KPISchema(
                key="active_clients",
                name="Active Clients",
                value=client_data.active_clients,
                unit="count",
                period=period,
                previous_value=max(0, client_data.active_clients - client_data.new_clients + client_data.churned_clients),
                change=client_data.new_clients - client_data.churned_clients,
                change_percentage=client_data.client_growth_pct,
                trend="UP" if client_data.client_growth_pct > 0 else "STABLE",
                status="HEALTHY" if client_data.active_clients > 0 else "WARNING",
                source="tenants",
                generated_at=now,
            )
        )

        # 4. AI Cost
        kpis.append(
            KPISchema(
                key="ai_cost",
                name="AI Gateway Cost",
                value=ai_data.ai_cost,
                unit="USD",
                period=period,
                previous_value=Decimal("0.00"),
                change=ai_data.ai_cost,
                change_percentage=0.0,
                trend=ai_data.cost_trend,
                status="HEALTHY",
                source="ai_gateway",
                generated_at=now,
            )
        )

        # 5. Churn Rate
        kpis.append(
            KPISchema(
                key="churn_rate",
                name="Client Churn Rate",
                value=f"{client_data.churned_clients}",
                unit="percentage",
                period=period,
                previous_value="0.0",
                change="0.0",
                change_percentage=0.0,
                trend="STABLE",
                status="CRITICAL" if client_data.churned_clients > 5 else "HEALTHY",
                source="subscriptions",
                generated_at=now,
            )
        )

        return kpis

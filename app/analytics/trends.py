import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import TrendSchema
from app.analytics.metrics import safe_decimal, calculate_change_pct, determine_trend_direction
from app.analytics.financial import FinancialAnalyticsService
from app.analytics.ai import AIAnalyticsService
from app.analytics.clients import ClientAnalyticsService


class TrendDetectionService:
    """Service for deterministic trend detection across metrics."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def detect_trends(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_days: int = 30,
    ) -> List[TrendSchema]:
        now = datetime.now(timezone.utc)
        period_end = now
        period_start = period_end - timedelta(days=period_days)
        prior_period_start = period_start - timedelta(days=period_days)

        fin_svc = FinancialAnalyticsService(self.session)
        curr_fin = await fin_svc.get_financial_analytics(tenant_id, period_start, period_end)
        prior_fin = await fin_svc.get_financial_analytics(tenant_id, prior_period_start, period_start)

        ai_svc = AIAnalyticsService(self.session)
        curr_ai = await ai_svc.get_ai_analytics(tenant_id, period_start, period_end)
        prior_ai = await ai_svc.get_ai_analytics(tenant_id, prior_period_start, period_start)

        client_svc = ClientAnalyticsService(self.session)
        curr_client = await client_svc.get_client_analytics(tenant_id, period_start, period_end)

        trends: List[TrendSchema] = []

        # 1. Revenue Trend
        rev_change = calculate_change_pct(curr_fin.total_revenue, prior_fin.total_revenue)
        rev_dir = determine_trend_direction(curr_fin.total_revenue, prior_fin.total_revenue)
        trends.append(
            TrendSchema(
                metric_key="revenue",
                metric_name="Total Revenue",
                direction="INCREASING" if rev_dir == "UP" else ("DECREASING" if rev_dir == "DOWN" else "STABLE"),
                period_comparison=f"Past {period_days}d vs prior {period_days}d",
                current_value=curr_fin.total_revenue,
                previous_value=prior_fin.total_revenue,
                change_pct=rev_change,
                explanation=f"Revenue changed by {rev_change}% compared with prior period.",
            )
        )

        # 2. AI Cost Trend
        ai_change = calculate_change_pct(curr_ai.ai_cost, prior_ai.ai_cost)
        ai_dir = determine_trend_direction(curr_ai.ai_cost, prior_ai.ai_cost)
        trends.append(
            TrendSchema(
                metric_key="ai_cost",
                metric_name="AI Cost",
                direction="INCREASING" if ai_dir == "UP" else ("DECREASING" if ai_dir == "DOWN" else "STABLE"),
                period_comparison=f"Past {period_days}d vs prior {period_days}d",
                current_value=curr_ai.ai_cost,
                previous_value=prior_ai.ai_cost,
                change_pct=ai_change,
                explanation=f"AI cost changed by {ai_change}% compared with prior period.",
            )
        )

        # 3. Client Growth Trend
        client_dir = "INCREASING" if curr_client.new_clients > curr_client.churned_clients else ("DECREASING" if curr_client.churned_clients > curr_client.new_clients else "STABLE")
        trends.append(
            TrendSchema(
                metric_key="active_clients",
                metric_name="Client Base Growth",
                direction=client_dir,
                period_comparison=f"Past {period_days}d",
                current_value=curr_client.active_clients,
                previous_value=max(0, curr_client.active_clients - curr_client.new_clients + curr_client.churned_clients),
                change_pct=curr_client.client_growth_pct,
                explanation=f"Client base changed with {curr_client.new_clients} new additions and {curr_client.churned_clients} churns.",
            )
        )

        return trends

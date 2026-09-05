import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import ForecastSchema
from app.analytics.financial import FinancialAnalyticsService
from app.analytics.clients import ClientAnalyticsService
from app.analytics.ai import AIAnalyticsService


class ForecastingService:
    """Service providing deterministic forecasting abstractions."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def generate_forecasts(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_days: int = 30,
    ) -> List[ForecastSchema]:
        now = datetime.now(timezone.utc)
        period_end = now
        period_start = period_end - timedelta(days=period_days)
        prior_period_start = period_start - timedelta(days=period_days)

        fin_svc = FinancialAnalyticsService(self.session)
        curr_fin = await fin_svc.get_financial_analytics(tenant_id, period_start, period_end)
        prior_fin = await fin_svc.get_financial_analytics(tenant_id, prior_period_start, period_start)

        client_svc = ClientAnalyticsService(self.session)
        curr_client = await client_svc.get_client_analytics(tenant_id, period_start, period_end)

        ai_svc = AIAnalyticsService(self.session)
        curr_ai = await ai_svc.get_ai_analytics(tenant_id, period_start, period_end)

        forecasts: List[ForecastSchema] = []

        # 1. Revenue Forecast
        if curr_fin.total_revenue == Decimal("0") and prior_fin.total_revenue == Decimal("0"):
            forecasts.append(
                ForecastSchema(
                    metric="revenue",
                    predicted_value=None,
                    period="Next 30 Days",
                    confidence_indicator="INSUFFICIENT_DATA",
                    methodology="Linear Growth Projection",
                    data_sufficiency="INSUFFICIENT_DATA",
                    explanation="Insufficient historical revenue records to produce a reliable forecast.",
                    generated_at=now,
                )
            )
        else:
            rev_growth_rate = (curr_fin.revenue_growth_pct / 100.0)
            projected_rev = (curr_fin.total_revenue * Decimal(str(1.0 + max(-0.5, min(0.5, rev_growth_rate))))).quantize(Decimal("0.01"))
            forecasts.append(
                ForecastSchema(
                    metric="revenue",
                    predicted_value=projected_rev,
                    period="Next 30 Days",
                    confidence_indicator="MEDIUM",
                    methodology="Weighted Historical Growth Trend",
                    data_sufficiency="SUFFICIENT",
                    explanation=f"Projected revenue based on recent period growth of {curr_fin.revenue_growth_pct}%.",
                    generated_at=now,
                )
            )

        # 2. Active Clients Forecast
        if curr_client.active_clients == 0:
            forecasts.append(
                ForecastSchema(
                    metric="active_clients",
                    predicted_value=None,
                    period="Next 30 Days",
                    confidence_indicator="INSUFFICIENT_DATA",
                    methodology="Net Client Acquisition Model",
                    data_sufficiency="INSUFFICIENT_DATA",
                    explanation="Insufficient active client history available to forecast future client counts.",
                    generated_at=now,
                )
            )
        else:
            net_additions = curr_client.new_clients - curr_client.churned_clients
            projected_clients = max(0, curr_client.active_clients + net_additions)
            forecasts.append(
                ForecastSchema(
                    metric="active_clients",
                    predicted_value=projected_clients,
                    period="Next 30 Days",
                    confidence_indicator="HIGH",
                    methodology="Net Client Acquisition Model",
                    data_sufficiency="SUFFICIENT",
                    explanation=f"Projected {projected_clients} active clients assuming net addition rate of {net_additions} clients/month.",
                    generated_at=now,
                )
            )

        # 3. AI Usage Forecast
        if curr_ai.total_tokens == 0:
            forecasts.append(
                ForecastSchema(
                    metric="ai_tokens",
                    predicted_value=None,
                    period="Next 30 Days",
                    confidence_indicator="INSUFFICIENT_DATA",
                    methodology="Token Consumption Velocity",
                    data_sufficiency="INSUFFICIENT_DATA",
                    explanation="Insufficient AI token usage history to forecast future token consumption.",
                    generated_at=now,
                )
            )
        else:
            projected_tokens = int(curr_ai.total_tokens * 1.1)  # 10% expected volume growth
            forecasts.append(
                ForecastSchema(
                    metric="ai_tokens",
                    predicted_value=projected_tokens,
                    period="Next 30 Days",
                    confidence_indicator="MEDIUM",
                    methodology="Token Consumption Velocity",
                    data_sufficiency="SUFFICIENT",
                    explanation=f"Projected ~{projected_tokens} AI tokens based on current period velocity.",
                    generated_at=now,
                )
            )

        return forecasts

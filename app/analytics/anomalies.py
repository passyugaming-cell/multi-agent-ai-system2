import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import AnomalySchema
from app.analytics.financial import FinancialAnalyticsService
from app.analytics.ai import AIAnalyticsService
from app.analytics.automation import AutomationAnalyticsService
from app.analytics.clients import ClientAnalyticsService


class AnomalyDetectionService:
    """Service for lightweight deterministic anomaly detection using rolling baselines."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def detect_anomalies(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_days: int = 30,
    ) -> List[AnomalySchema]:
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

        auto_svc = AutomationAnalyticsService(self.session)
        curr_auto = await auto_svc.get_automation_analytics(tenant_id, period_start, period_end)

        client_svc = ClientAnalyticsService(self.session)
        curr_client = await client_svc.get_client_analytics(tenant_id, period_start, period_end)

        anomalies: List[AnomalySchema] = []

        # 1. Unusual Revenue Drop (e.g. > 30% drop compared to baseline)
        if prior_fin.total_revenue > Decimal("0"):
            rev_diff_pct = float(((curr_fin.total_revenue - prior_fin.total_revenue) / prior_fin.total_revenue) * Decimal("100"))
            if rev_diff_pct <= -30.0:
                anomalies.append(
                    AnomalySchema(
                        metric="revenue",
                        observed_value=curr_fin.total_revenue,
                        expected_baseline_value=prior_fin.total_revenue,
                        deviation_pct=round(rev_diff_pct, 2),
                        severity="CRITICAL" if rev_diff_pct <= -50.0 else "HIGH",
                        time_period=f"Past {period_days}d",
                        explanation=f"Revenue decreased by {round(abs(rev_diff_pct), 1)}% compared to the prior period baseline.",
                        detected_at=now,
                    )
                )

        # 2. Unusual AI Cost Spike (e.g. > 100% increase compared to baseline)
        if prior_ai.ai_cost > Decimal("0"):
            ai_diff_pct = float(((curr_ai.ai_cost - prior_ai.ai_cost) / prior_ai.ai_cost) * Decimal("100"))
            if ai_diff_pct >= 100.0:
                anomalies.append(
                    AnomalySchema(
                        metric="ai_cost",
                        observed_value=curr_ai.ai_cost,
                        expected_baseline_value=prior_ai.ai_cost,
                        deviation_pct=round(ai_diff_pct, 2),
                        severity="HIGH" if ai_diff_pct < 300.0 else "CRITICAL",
                        time_period=f"Past {period_days}d",
                        explanation=f"AI cost increased by {round(ai_diff_pct, 1)}% compared to the prior period baseline.",
                        detected_at=now,
                    )
                )

        # 3. High Workflow Failures
        if curr_auto.failure_rate >= 15.0 and curr_auto.workflow_executions > 5:
            anomalies.append(
                AnomalySchema(
                    metric="workflow_failures",
                    observed_value=curr_auto.failed_executions,
                    expected_baseline_value=0,
                    deviation_pct=round(curr_auto.failure_rate, 2),
                    severity="HIGH" if curr_auto.failure_rate >= 30.0 else "MEDIUM",
                    time_period=f"Past {period_days}d",
                    explanation=f"Workflow failure rate reached {curr_auto.failure_rate}%, above normal threshold.",
                    detected_at=now,
                )
            )

        # 4. Unusual Payment Failures
        if curr_fin.failed_payments_amount > Decimal("0"):
            anomalies.append(
                AnomalySchema(
                    metric="failed_payments",
                    observed_value=curr_fin.failed_payments_amount,
                    expected_baseline_value=Decimal("0.00"),
                    deviation_pct=100.0,
                    severity="MEDIUM",
                    time_period=f"Past {period_days}d",
                    explanation=f"Failed payment attempts totaling {curr_fin.failed_payments_amount} IDR recorded.",
                    detected_at=now,
                )
            )

        return anomalies

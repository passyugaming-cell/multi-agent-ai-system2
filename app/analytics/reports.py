import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import DailyBusinessBriefSchema, WeeklyStrategicReviewSchema
from app.analytics.financial import FinancialAnalyticsService
from app.analytics.clients import ClientAnalyticsService
from app.analytics.sales import SalesAnalyticsService
from app.analytics.ai import AIAnalyticsService
from app.analytics.automation import AutomationAnalyticsService
from app.analytics.trends import TrendDetectionService
from app.analytics.anomalies import AnomalyDetectionService
from app.analytics.forecasting import ForecastingService
from app.analytics.recommendations import RecommendationAnalyticsService
from app.agents.owner_ai.health import BusinessHealthCalculator


class ExecutiveReportService:
    """Service generating structured Daily Business Brief and Weekly Strategic Review."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def generate_daily_brief(
        self,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> DailyBusinessBriefSchema:
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=1)

        fin_svc = FinancialAnalyticsService(self.session)
        fin = await fin_svc.get_financial_analytics(tenant_id, period_start, now)

        client_svc = ClientAnalyticsService(self.session)
        client = await client_svc.get_client_analytics(tenant_id, period_start, now)

        ai_svc = AIAnalyticsService(self.session)
        ai = await ai_svc.get_ai_analytics(tenant_id, period_start, now)

        auto_svc = AutomationAnalyticsService(self.session)
        auto = await auto_svc.get_automation_analytics(tenant_id, period_start, now)

        anomaly_svc = AnomalyDetectionService(self.session)
        anomalies = await anomaly_svc.detect_anomalies(tenant_id, period_days=1)

        health_res = None
        health_score = 100.0
        if tenant_id:
            health_res = await BusinessHealthCalculator.calculate(self.session, tenant_id)
            health_score = health_res.score

        # Structured sections
        key_numbers = {
            "daily_revenue": str(fin.total_revenue),
            "mrr": str(fin.mrr),
            "active_clients": client.active_clients,
            "ai_cost_24h": str(ai.ai_cost),
            "workflow_executions_24h": auto.workflow_executions,
        }

        what_changed = [
            f"Recorded {fin.total_revenue} IDR in revenue in the past 24 hours.",
            f"Active client base stands at {client.active_clients} clients.",
            f"Executed {auto.workflow_executions} workflows with {auto.success_rate}% success rate.",
        ]

        what_needs_attention = []
        if fin.failed_payments_amount > 0:
            what_needs_attention.append(f"Failed payments totaled {fin.failed_payments_amount} IDR.")
        if auto.failed_executions > 0:
            what_needs_attention.append(f"{auto.failed_executions} workflow execution failure(s) recorded.")
        for anom in anomalies:
            what_needs_attention.append(f"Anomaly in {anom.metric}: {anom.explanation}")

        if not what_needs_attention:
            what_needs_attention.append("No critical anomalies or payment failures detected in the past 24 hours.")

        opportunities = [
            f"Trial clients ({client.trial_clients}) eligible for conversion outreach.",
            f"AI gateway success rate at {ai.success_rate}%.",
        ]

        recommendations = [
            {
                "title": "Monitor Workflow Failures" if auto.failed_executions > 0 else "Maintain Operational Efficiency",
                "suggested_action": "Review failed workflow execution logs." if auto.failed_executions > 0 else "Continue automated operational monitoring.",
                "priority": "HIGH" if auto.failed_executions > 0 else "NORMAL",
            }
        ]

        summary = f"Daily Business Brief: System operating at {health_score}/100 business health score with {fin.total_revenue} IDR 24h revenue."

        return DailyBusinessBriefSchema(
            summary=summary,
            key_numbers=key_numbers,
            what_changed=what_changed,
            what_needs_attention=what_needs_attention,
            opportunities=opportunities,
            recommendations=recommendations,
            business_health_score=health_score,
            generated_at=now,
        )

    async def generate_weekly_review(
        self,
        tenant_id: Optional[uuid.UUID] = None,
    ) -> WeeklyStrategicReviewSchema:
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=7)

        fin_svc = FinancialAnalyticsService(self.session)
        fin = await fin_svc.get_financial_analytics(tenant_id, period_start, now)

        client_svc = ClientAnalyticsService(self.session)
        client = await client_svc.get_client_analytics(tenant_id, period_start, now)

        sales_svc = SalesAnalyticsService(self.session)
        sales = await sales_svc.get_sales_analytics(tenant_id, period_start, now)

        ai_svc = AIAnalyticsService(self.session)
        ai = await ai_svc.get_ai_analytics(tenant_id, period_start, now)

        auto_svc = AutomationAnalyticsService(self.session)
        auto = await auto_svc.get_automation_analytics(tenant_id, period_start, now)

        trend_svc = TrendDetectionService(self.session)
        trends = await trend_svc.detect_trends(tenant_id, period_days=7)

        anomaly_svc = AnomalyDetectionService(self.session)
        anomalies = await anomaly_svc.detect_anomalies(tenant_id, period_days=7)

        forecast_svc = ForecastingService(self.session)
        forecasts = await forecast_svc.generate_forecasts(tenant_id, period_days=7)

        rec_analytics_svc = RecommendationAnalyticsService(self.session)
        rec_outcomes = await rec_analytics_svc.get_recommendation_analytics(tenant_id, period_days=7)

        health_score = 100.0
        if tenant_id:
            health_res = await BusinessHealthCalculator.calculate(self.session, tenant_id)
            health_score = health_res.score

        summary = f"Weekly Strategic Review: Weekly revenue reached {fin.total_revenue} IDR with {fin.revenue_growth_pct}% growth and health score {health_score}."

        return WeeklyStrategicReviewSchema(
            summary=summary,
            weekly_revenue=fin.total_revenue,
            revenue_growth_pct=fin.revenue_growth_pct,
            client_growth_pct=client.client_growth_pct,
            churn_rate=client.churned_clients / max(1, client.total_clients) * 100.0,
            sales_funnel_summary=sales.model_dump(mode="json"),
            ai_usage_and_cost=ai.model_dump(mode="json"),
            automation_performance=auto.model_dump(mode="json"),
            client_health_summary=client.health_summary,
            business_health_score=health_score,
            trends=trends,
            anomalies=anomalies,
            forecast=forecasts,
            recommendations=[
                {
                    "title": "Optimize High-Volume Workflows",
                    "suggested_action": "Review top active workflows for rate limit optimization.",
                    "priority": "NORMAL",
                }
            ],
            recommendation_outcomes=rec_outcomes,
            generated_at=now,
        )

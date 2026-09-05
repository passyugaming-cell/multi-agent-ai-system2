import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.owner_ai.health import BusinessHealthCalculator
from app.agents.owner_ai.approvals import ApprovalRouter
from app.agents.owner_ai.recommendations import RecommendationService
from app.agents.owner_ai.schemas import BusinessBriefSchema, WeeklyReviewSchema
from app.core.tasks.service import TaskService


class ReportGenerator:
    """Generates Daily Business Brief and Weekly Strategic Review reports."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session
        self.task_service = TaskService(db_session)
        self.approval_router = ApprovalRouter(db_session)
        self.rec_service = RecommendationService(db_session)

    async def generate_daily_brief(self, tenant_id: uuid.UUID) -> BusinessBriefSchema:
        now = datetime.now(timezone.utc)

        # 1. Health Score
        health = await BusinessHealthCalculator.calculate(self.session, tenant_id)

        # 2. Pending Approvals
        pending_approvals = await self.approval_router.get_pending_approvals_with_explanations(tenant_id)

        # 3. Priority Tasks
        all_tasks = await self.task_service.list_tasks(tenant_id)
        priority_tasks = [
            {
                "task_id": str(t.id),
                "title": t.title,
                "priority": t.priority,
                "status": t.status,
                "assigned_agent": t.assigned_agent,
            }
            for t in all_tasks
            if t.status in ("CREATED", "ASSIGNED", "IN_PROGRESS", "BLOCKED")
        ][:5]

        # 4. Existing Recommendations
        recs = await self.rec_service.list_recommendations(tenant_id, status="PROPOSED")

        # 5. Key Facts & Insights
        key_facts = [
            f"30-day revenue: ${health.historical_comparison.get('curr_30d_revenue', 0.0):,.2f}",
            f"30-day orders count: {health.historical_comparison.get('curr_30d_orders', 0)}",
            f"Active open priority tasks: {len(priority_tasks)}",
            f"Pending approval requests: {len(pending_approvals)}",
        ]

        insights = [
            f"Business health score is {health.score}/100 ({health.trend} trend).",
            f"Order fulfillment score is {health.category_scores.get('order_fulfillment', 100.0)}/100.",
        ]

        return BusinessBriefSchema(
            tenant_id=tenant_id,
            health=health,
            key_facts=key_facts,
            insights=insights,
            risks=health.warnings,
            opportunities=["Follow up on conversion drop to recover revenue."],
            pending_approvals=pending_approvals,
            priority_tasks=priority_tasks,
            recommendations=recs,
            confidence=1.0,
            data_freshness=now,
        )

    async def generate_weekly_review(self, tenant_id: uuid.UUID) -> WeeklyReviewSchema:
        now = datetime.now(timezone.utc)

        # Health
        health = await BusinessHealthCalculator.calculate(self.session, tenant_id)

        # Recommendations
        recs = await self.rec_service.list_recommendations(tenant_id, status="PROPOSED")

        return WeeklyReviewSchema(
            tenant_id=tenant_id,
            health=health,
            weekly_performance={
                "revenue": health.historical_comparison.get("curr_30d_revenue", 0.0),
                "orders": health.historical_comparison.get("curr_30d_orders", 0),
            },
            revenue_trend=health.trend,
            sales_trend=health.trend,
            customer_trend="STABLE",
            support_trend="STABLE",
            automation_performance={"success_rate": health.category_scores.get("system_workflows", 100.0)},
            ai_usage_summary={"cost_estimate": "$0.05"},
            client_health_movement=[],
            anomalies=health.warnings,
            decisions_made=[],
            completed_actions=[],
            failed_actions=[],
            unresolved_risks=health.warnings,
            opportunities=["Promote highest converting products to active customers."],
            strategic_recommendations=recs,
            next_week_priorities=["Resolve open priority tasks", "Review pending approvals"],
            forecasts={"projected_monthly_revenue": health.historical_comparison.get("curr_30d_revenue", 0.0) * 1.05},
            confidence=0.9,
        )

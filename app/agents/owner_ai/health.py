import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.order import Order
from app.database.models.customer import Customer
from app.database.models.workflow import Task, WorkflowExecution
from app.database.models.ai_usage import AIUsageRecord


class BusinessHealthResult(BaseModel):
    score: float = Field(..., ge=0.0, le=100.0)
    category_scores: Dict[str, float] = Field(default_factory=dict)
    trend: str = "STABLE"  # UP, DOWN, STABLE
    historical_comparison: Dict[str, Any] = Field(default_factory=dict)
    contributing_factors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    data_freshness: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClientHealthResult(BaseModel):
    score: float = Field(..., ge=0.0, le=100.0)
    category: str = "HEALTHY"  # HEALTHY (80-100), NEEDS_ATTENTION (60-79), AT_RISK (40-59), CRITICAL (0-39)
    trend: str = "STABLE"  # UP, DOWN, STABLE
    contributing_factors: List[str] = Field(default_factory=list)
    warning_indicators: List[str] = Field(default_factory=list)
    last_calculated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BusinessHealthCalculator:
    """100% Deterministic calculator for overall business health scoring. DO NOT ask AI for numerical score."""

    @staticmethod
    async def calculate(db_session: AsyncSession, tenant_id: uuid.UUID) -> BusinessHealthResult:
        now = datetime.now(timezone.utc)
        period_30d = now - timedelta(days=30)
        period_60d = now - timedelta(days=60)

        # 1. Revenue & Orders (Current 30d vs Previous 30d)
        stmt_curr_orders = select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), 0)
        ).where(and_(Order.tenant_id == tenant_id, Order.created_at >= period_30d))
        res_curr = (await db_session.execute(stmt_curr_orders)).one()
        curr_count, curr_revenue = res_curr[0], float(res_curr[1])

        stmt_prev_orders = select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), 0)
        ).where(and_(
            Order.tenant_id == tenant_id,
            Order.created_at >= period_60d,
            Order.created_at < period_30d
        ))
        res_prev = (await db_session.execute(stmt_prev_orders)).one()
        prev_count, prev_revenue = res_prev[0], float(res_prev[1])

        # Revenue score calculation (Weight: 30%)
        rev_change_pct = 0.0
        if prev_revenue > 0:
            rev_change_pct = round(((curr_revenue - prev_revenue) / prev_revenue) * 100, 2)

        rev_score = 80.0  # Baseline
        if rev_change_pct >= 10.0:
            rev_score = 95.0
        elif rev_change_pct >= 0.0:
            rev_score = 85.0
        elif rev_change_pct >= -10.0:
            rev_score = 65.0
        else:
            rev_score = 45.0

        # 2. Order Success Rate (Weight: 25%)
        stmt_completed = select(func.count(Order.id)).where(
            and_(Order.tenant_id == tenant_id, Order.status.in_(["COMPLETED", "PAID", "DELIVERED"]))
        )
        completed_orders = (await db_session.execute(stmt_completed)).scalar() or 0

        stmt_cancelled = select(func.count(Order.id)).where(
            and_(Order.tenant_id == tenant_id, Order.status.in_(["CANCELLED", "FAILED"]))
        )
        cancelled_orders = (await db_session.execute(stmt_cancelled)).scalar() or 0

        total_orders_all = completed_orders + cancelled_orders
        order_success_rate = (completed_orders / total_orders_all * 100.0) if total_orders_all > 0 else 100.0
        order_fulfillment_score = min(100.0, order_success_rate)

        # 3. System & Workflow Health (Weight: 25%)
        stmt_wf_runs = select(func.count(WorkflowExecution.id)).where(
            and_(WorkflowExecution.tenant_id == tenant_id, WorkflowExecution.created_at >= period_30d)
        )
        total_wf = (await db_session.execute(stmt_wf_runs)).scalar() or 0

        stmt_wf_failed = select(func.count(WorkflowExecution.id)).where(
            and_(
                WorkflowExecution.tenant_id == tenant_id,
                WorkflowExecution.created_at >= period_30d,
                WorkflowExecution.status.in_(["FAILED", "TIMED_OUT"])
            )
        )
        failed_wf = (await db_session.execute(stmt_wf_failed)).scalar() or 0

        wf_success_rate = ((total_wf - failed_wf) / total_wf * 100.0) if total_wf > 0 else 100.0
        system_health_score = round(wf_success_rate, 2)

        # 4. Support Health & Incident Tasks (Weight: 20%)
        stmt_open_incidents = select(func.count(Task.id)).where(
            and_(
                Task.tenant_id == tenant_id,
                Task.status.in_(["CREATED", "ASSIGNED", "IN_PROGRESS", "BLOCKED"]),
                Task.priority.in_(["HIGH", "CRITICAL"])
            )
        )
        open_incidents = (await db_session.execute(stmt_open_incidents)).scalar() or 0

        if open_incidents == 0:
            support_score = 100.0
        elif open_incidents <= 2:
            support_score = 75.0
        elif open_incidents <= 5:
            support_score = 50.0
        else:
            support_score = 25.0

        # Weighted Total Score
        total_score = round(
            (rev_score * 0.30) +
            (order_fulfillment_score * 0.25) +
            (system_health_score * 0.25) +
            (support_score * 0.20),
            2
        )

        category_scores = {
            "revenue_sales": round(rev_score, 2),
            "order_fulfillment": round(order_fulfillment_score, 2),
            "system_workflows": round(system_health_score, 2),
            "support_health": round(support_score, 2),
        }

        # Trend calculation
        if rev_change_pct > 2.0:
            trend = "UP"
        elif rev_change_pct < -2.0:
            trend = "DOWN"
        else:
            trend = "STABLE"

        contributing_factors = []
        if rev_change_pct < 0:
            contributing_factors.append(f"Revenue changed by {rev_change_pct}% compared to previous period.")
        else:
            contributing_factors.append(f"Revenue changed by +{rev_change_pct}% compared to previous period.")

        if order_success_rate < 90.0:
            contributing_factors.append(f"Order success rate is {round(order_success_rate, 1)}%.")

        warnings = []
        if rev_change_pct <= -5.0:
            warnings.append("Significant revenue decline detected compared to previous 30-day period.")
        if open_incidents > 0:
            warnings.append(f"{open_incidents} high-priority open incident task(s) active.")
        if failed_wf > 0:
            warnings.append(f"{failed_wf} workflow execution failure(s) recorded in past 30 days.")

        return BusinessHealthResult(
            score=total_score,
            category_scores=category_scores,
            trend=trend,
            historical_comparison={
                "curr_30d_revenue": curr_revenue,
                "prev_30d_revenue": prev_revenue,
                "revenue_change_pct": rev_change_pct,
                "curr_30d_orders": curr_count,
                "prev_30d_orders": prev_count,
            },
            contributing_factors=contributing_factors,
            warnings=warnings,
            data_freshness=now,
        )


class ClientHealthCalculator:
    """100% Deterministic calculator for evaluating individual tenant/client health score."""

    @staticmethod
    async def calculate(db_session: AsyncSession, tenant_id: uuid.UUID) -> ClientHealthResult:
        now = datetime.now(timezone.utc)
        period_30d = now - timedelta(days=30)

        # 1. Orders and fulfillment
        stmt_orders = select(func.count(Order.id)).where(
            and_(Order.tenant_id == tenant_id, Order.created_at >= period_30d)
        )
        order_count = (await db_session.execute(stmt_orders)).scalar() or 0

        stmt_failed_orders = select(func.count(Order.id)).where(
            and_(
                Order.tenant_id == tenant_id,
                Order.created_at >= period_30d,
                Order.status.in_(["CANCELLED", "FAILED"])
            )
        )
        failed_orders = (await db_session.execute(stmt_failed_orders)).scalar() or 0

        # 2. Blocked or failed tasks
        stmt_blocked_tasks = select(func.count(Task.id)).where(
            and_(Task.tenant_id == tenant_id, Task.status.in_(["BLOCKED", "FAILED"]))
        )
        blocked_tasks = (await db_session.execute(stmt_blocked_tasks)).scalar() or 0

        # Base score 100, deduct for issues
        score = 100.0
        factors = []
        warnings = []

        if failed_orders > 0:
            deduction = min(30.0, failed_orders * 10.0)
            score -= deduction
            factors.append(f"{failed_orders} failed or cancelled order(s) in past 30 days.")
            warnings.append("Order failures impacting client performance.")

        if blocked_tasks > 0:
            deduction = min(30.0, blocked_tasks * 10.0)
            score -= deduction
            factors.append(f"{blocked_tasks} blocked or failed operational task(s).")
            warnings.append("Blocked operational tasks requiring resolution.")

        score = max(0.0, min(100.0, round(score, 2)))

        # Category mapping
        if score >= 80.0:
            category = "HEALTHY"
        elif score >= 60.0:
            category = "NEEDS_ATTENTION"
        elif score >= 40.0:
            category = "AT_RISK"
        else:
            category = "CRITICAL"

        if not factors:
            factors.append("Operational metrics and task executions are within healthy bounds.")

        return ClientHealthResult(
            score=score,
            category=category,
            trend="STABLE",
            contributing_factors=factors,
            warning_indicators=warnings,
            last_calculated_at=now,
        )

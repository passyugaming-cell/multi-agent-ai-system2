from typing import Any
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.schemas import ToolRequest, ToolResult
from app.database.models.order import Order
from app.database.models.ai_usage import AIUsageRecord
from app.database.models.customer import Customer


async def get_revenue_analytics_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Calculate actual historical revenue and order count from database."""
    stmt = select(
        func.count(Order.id).label("total_orders"),
        func.coalesce(func.sum(Order.total), 0.0).label("total_revenue"),
    ).where(and_(Order.tenant_id == tool_req.tenant_id, Order.status != "CANCELLED"))

    res = (await session.execute(stmt)).one()
    total_orders = res.total_orders or 0
    total_revenue = float(res.total_revenue or 0.0)

    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0.0

    return ToolResult(
        success=True,
        tool_name="get_revenue_analytics",
        data={
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "average_order_value": round(avg_order_value, 2),
            "label": "ACTUAL",
        },
        evidence=[{"total_orders": total_orders, "total_revenue": total_revenue}],
        metadata={"tenant_id": str(tool_req.tenant_id), "read_only": True},
        correlation_id=tool_req.correlation_id,
    )


async def get_order_analytics_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Aggregate order breakdown by status."""
    stmt = (
        select(Order.status, func.count(Order.id))
        .where(Order.tenant_id == tool_req.tenant_id)
        .group_by(Order.status)
    )
    results = (await session.execute(stmt)).all()

    breakdown = {status: count for status, count in results}

    return ToolResult(
        success=True,
        tool_name="get_order_analytics",
        data={"order_status_breakdown": breakdown, "label": "ACTUAL"},
        evidence=[{"status_breakdown": breakdown}],
        metadata={"tenant_id": str(tool_req.tenant_id), "read_only": True},
        correlation_id=tool_req.correlation_id,
    )


async def get_ai_usage_analytics_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Aggregate tenant AI Gateway token usage and cost metrics."""
    stmt = select(
        func.count(AIUsageRecord.id).label("total_ai_requests"),
        func.coalesce(func.sum(AIUsageRecord.total_tokens), 0).label("total_tokens"),
        func.coalesce(func.sum(AIUsageRecord.estimated_cost), 0.0).label("total_cost"),
    ).where(AIUsageRecord.tenant_id == tool_req.tenant_id)

    res = (await session.execute(stmt)).one()

    return ToolResult(
        success=True,
        tool_name="get_ai_usage_analytics",
        data={
            "total_ai_requests": res.total_ai_requests or 0,
            "total_tokens": res.total_tokens or 0,
            "total_cost": float(res.total_cost or 0.0),
            "label": "ACTUAL",
        },
        evidence=[{"total_ai_requests": res.total_ai_requests, "total_cost": float(res.total_cost or 0.0)}],
        metadata={"tenant_id": str(tool_req.tenant_id), "read_only": True},
        correlation_id=tool_req.correlation_id,
    )

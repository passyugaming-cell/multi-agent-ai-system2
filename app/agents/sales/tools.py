from typing import Any
import uuid
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.schemas import ToolRequest, ToolResult
from app.database.models.product import Product
from app.database.models.customer import Customer
from app.database.models.conversation import Conversation
from app.database.models.message import Message
from app.core.tasks.service import TaskService


async def get_products_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Retrieve official product, pricing, and stock directly from PostgreSQL source of truth."""
    product_name = tool_req.parameters.get("product_name")

    stmt = select(Product).where(and_(Product.tenant_id == tool_req.tenant_id, Product.is_active.is_(True)))
    if product_name:
        stmt = stmt.where(Product.name.ilike(f"%{product_name}%"))

    products = (await session.execute(stmt)).scalars().all()

    product_data = [
        {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "price": float(p.price),
            "stock_quantity": p.stock,
            "is_available": p.stock > 0,
            "sku": p.sku,
        }
        for p in products
    ]

    return ToolResult(
        success=True,
        tool_name="get_products",
        data=product_data,
        evidence=[{"product_count": len(product_data), "query": product_name}],
        metadata={"tenant_id": str(tool_req.tenant_id)},
        correlation_id=tool_req.correlation_id,
    )


async def get_customer_conversation_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Retrieve recent customer conversation messages from database."""
    customer_id = tool_req.parameters.get("customer_id")
    if not customer_id:
        return ToolResult(
            success=False,
            tool_name="get_customer_conversation",
            error="customer_id parameter is required.",
            correlation_id=tool_req.correlation_id,
        )

    try:
        cust_uuid = uuid.UUID(str(customer_id))
    except ValueError:
        return ToolResult(
            success=False,
            tool_name="get_customer_conversation",
            error="Invalid customer_id UUID format.",
            correlation_id=tool_req.correlation_id,
        )

    stmt = (
        select(Message)
        .where(and_(Message.tenant_id == tool_req.tenant_id, Message.customer_id == cust_uuid))
        .order_by(Message.created_at.desc())
        .limit(20)
    )
    messages = (await session.execute(stmt)).scalars().all()

    msg_data = [
        {
            "id": str(m.id),
            "sender": m.sender,
            "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in reversed(messages)
    ]

    return ToolResult(
        success=True,
        tool_name="get_customer_conversation",
        data=msg_data,
        evidence=[{"message_count": len(msg_data)}],
        metadata={"customer_id": str(cust_uuid)},
        correlation_id=tool_req.correlation_id,
    )


async def create_followup_task_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Create a follow-up task via TaskService."""
    title = tool_req.parameters.get("title", "Sales Follow-up Task")
    description = tool_req.parameters.get("description", "")
    assigned_agent = tool_req.parameters.get("assigned_agent", "ai_sales")

    task_service = TaskService(session)
    task = await task_service.create_task(
        tenant_id=tool_req.tenant_id,
        title=title,
        description=description,
        task_type="sales_followup",
        assigned_agent=assigned_agent,
        source="agent_ai_sales",
    )

    return ToolResult(
        success=True,
        tool_name="create_followup_task",
        data={"task_id": str(task.id), "status": task.status, "title": task.title},
        evidence=[{"task_id": str(task.id)}],
        metadata={"tenant_id": str(tool_req.tenant_id)},
        correlation_id=tool_req.correlation_id,
    )


async def recommend_discount_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Prepare a discount recommendation request."""
    discount_percent = float(tool_req.parameters.get("discount_percent", 0.0))
    reason = tool_req.parameters.get("reason", "Sales incentive")

    # Policy threshold: Discounts > 10% require approval
    requires_approval = discount_percent > 10.0

    return ToolResult(
        success=True,
        tool_name="recommend_discount",
        data={
            "proposed_discount_percent": discount_percent,
            "reason": reason,
            "requires_approval": requires_approval,
        },
        evidence=[{"discount_percent": discount_percent, "policy_limit": 10.0}],
        metadata={"requires_approval": requires_approval},
        correlation_id=tool_req.correlation_id,
    )

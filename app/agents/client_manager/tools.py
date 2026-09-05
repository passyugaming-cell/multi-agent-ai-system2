from typing import Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.schemas import ToolRequest, ToolResult
from app.database.models.onboarding import OnboardingChecklist
from app.database.models.business_profile import BusinessProfile
from app.tenants.provisioning.readiness import ReadinessCalculator
from app.core.tasks.service import TaskService


async def get_client_onboarding_state_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Retrieve tenant onboarding checklist and business profile state from DB."""
    stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tool_req.tenant_id)
    checklist_items = (await session.execute(stmt)).scalars().all()

    profile_stmt = select(BusinessProfile).where(BusinessProfile.tenant_id == tool_req.tenant_id)
    profile = (await session.execute(profile_stmt)).scalar_one_or_none()

    checklist_data = [
        {
            "id": str(item.id),
            "key": item.key,
            "category": item.category,
            "title": item.title,
            "required": item.required,
            "status": item.status,
        }
        for item in checklist_items
    ]

    profile_data = {
        "company_name": profile.company_name if profile else None,
        "operating_hours": profile.operating_hours if profile else None,
        "contact_email": profile.contact_email if profile else None,
        "industry": profile.industry if profile else None,
    }

    return ToolResult(
        success=True,
        tool_name="get_client_onboarding_state",
        data={
            "checklist": checklist_data,
            "profile": profile_data,
        },
        evidence=[{"checklist_count": len(checklist_data), "has_profile": profile is not None}],
        metadata={"tenant_id": str(tool_req.tenant_id)},
        correlation_id=tool_req.correlation_id,
    )


async def calculate_readiness_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Deterministically calculate tenant readiness score via ReadinessCalculator."""
    stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tool_req.tenant_id)
    checklist_items = (await session.execute(stmt)).scalars().all()

    readiness = ReadinessCalculator.calculate(checklist_items)

    return ToolResult(
        success=True,
        tool_name="calculate_readiness",
        data={
            "score": readiness.score,
            "readiness_status": readiness.readiness_status,
            "blocking_requirements": readiness.blocking_requirements,
            "completed_requirements": readiness.completed_requirements,
            "incomplete_requirements": readiness.incomplete_requirements,
            "category_scores": readiness.category_scores,
        },
        evidence=[{"score": readiness.score, "status": readiness.readiness_status}],
        metadata={"tenant_id": str(tool_req.tenant_id)},
        correlation_id=tool_req.correlation_id,
    )


async def create_onboarding_task_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Create an onboarding task via TaskService."""
    title = tool_req.parameters.get("title", "Onboarding Requirement Task")
    description = tool_req.parameters.get("description", "")
    priority = tool_req.parameters.get("priority", "HIGH")

    task_service = TaskService(session)
    task = await task_service.create_task(
        tenant_id=tool_req.tenant_id,
        title=title,
        description=description,
        task_type="onboarding",
        priority=priority,
        assigned_agent="ai_client_manager",
        source="agent_ai_client_manager",
    )

    return ToolResult(
        success=True,
        tool_name="create_onboarding_task",
        data={"task_id": str(task.id), "status": task.status, "title": task.title},
        evidence=[{"task_id": str(task.id)}],
        metadata={"tenant_id": str(tool_req.tenant_id)},
        correlation_id=tool_req.correlation_id,
    )


async def recommend_configuration_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Formulate a configuration change request."""
    config_key = tool_req.parameters.get("config_key")
    recommended_value = tool_req.parameters.get("recommended_value")
    reason = tool_req.parameters.get("reason", "Onboarding completion requirement")

    return ToolResult(
        success=True,
        tool_name="recommend_configuration",
        data={
            "config_key": config_key,
            "recommended_value": recommended_value,
            "reason": reason,
            "requires_approval": True,  # Critical config changes require approval
        },
        evidence=[{"config_key": config_key}],
        metadata={"requires_approval": True},
        correlation_id=tool_req.correlation_id,
    )

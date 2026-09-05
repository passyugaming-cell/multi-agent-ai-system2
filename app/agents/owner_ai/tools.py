import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.schemas import ToolRequest, ToolResult, AgentRequest
from app.agents.base.registry import agent_registry
from app.agents.owner_ai.health import BusinessHealthCalculator, ClientHealthCalculator
from app.agents.owner_ai.reports import ReportGenerator
from app.agents.owner_ai.recommendations import RecommendationService
from app.memory.service import MemoryService
from app.core.tasks.service import TaskService
from app.core.approvals.service import ApprovalService
from app.core.exceptions import AppError


async def tool_evaluate_business_health(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        res = await BusinessHealthCalculator.calculate(db_session, request.tenant_id)
        return ToolResult(
            success=True,
            tool_name="evaluate_business_health",
            data=res.model_dump(mode="json"),
            evidence=[f"Business Health Score calculated as {res.score} based on DB metrics."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="evaluate_business_health",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_evaluate_client_health(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        res = await ClientHealthCalculator.calculate(db_session, request.tenant_id)
        return ToolResult(
            success=True,
            tool_name="evaluate_client_health",
            data=res.model_dump(mode="json"),
            evidence=[f"Client Health Score calculated as {res.score} ({res.category})."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="evaluate_client_health",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_get_memory_context(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        objective = request.parameters.get("objective", "")
        mem_service = MemoryService(db_session)
        ctx = await mem_service.get_relevant_context(request.tenant_id, objective)
        return ToolResult(
            success=True,
            tool_name="get_memory_context",
            data=ctx.model_dump(mode="json"),
            evidence=[f"Retrieved {len(ctx.business_memories)} business and {len(ctx.client_memories)} client memories."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="get_memory_context",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_delegate_task_to_agent(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        target_agent = request.parameters.get("target_agent")
        task_type = request.parameters.get("task_type", "general_task")
        objective = request.parameters.get("objective", "")
        context = request.parameters.get("context", {})
        delegation_depth = request.parameters.get("delegation_depth", 0)

        agent_req = AgentRequest(
            tenant_id=request.tenant_id,
            source="owner_ai",
            source_agent="owner_ai",
            target_agent=target_agent,
            task_type=task_type,
            objective=objective,
            context=context,
            correlation_id=request.correlation_id,
            delegation_depth=delegation_depth,
        )

        agent_res = await agent_registry.delegate_task(agent_req, db_session)
        return ToolResult(
            success=agent_res.status.value not in ("FAILED", "BLOCKED"),
            tool_name="delegate_task_to_agent",
            data=agent_res.model_dump(mode="json"),
            evidence=agent_res.evidence,
            error=agent_res.error,
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="delegate_task_to_agent",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_create_orchestration_task(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        task_service = TaskService(db_session)
        task = await task_service.create_task(
            tenant_id=request.tenant_id,
            title=request.parameters.get("title", "Owner AI Task"),
            description=request.parameters.get("description"),
            task_type=request.parameters.get("task_type", "orchestration"),
            priority=request.parameters.get("priority", "NORMAL"),
            assigned_agent=request.parameters.get("assigned_agent"),
            source="owner_ai",
        )
        return ToolResult(
            success=True,
            tool_name="create_orchestration_task",
            data={"task_id": str(task.id), "status": task.status, "title": task.title},
            evidence=[f"Created task '{task.title}' assigned to {task.assigned_agent}."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="create_orchestration_task",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_generate_daily_brief(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        generator = ReportGenerator(db_session)
        brief = await generator.generate_daily_brief(request.tenant_id)
        return ToolResult(
            success=True,
            tool_name="generate_daily_brief",
            data=brief.model_dump(mode="json"),
            evidence=["Daily Business Brief generated successfully."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="generate_daily_brief",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_generate_weekly_review(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        generator = ReportGenerator(db_session)
        review = await generator.generate_weekly_review(request.tenant_id)
        return ToolResult(
            success=True,
            tool_name="generate_weekly_review",
            data=review.model_dump(mode="json"),
            evidence=["Weekly Strategic Review generated successfully."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="generate_weekly_review",
            error=str(exc),
            correlation_id=request.correlation_id,
        )


async def tool_create_recommendation(request: ToolRequest, db_session: AsyncSession) -> ToolResult:
    try:
        rec_service = RecommendationService(db_session)
        rec = await rec_service.create_recommendation(
            tenant_id=request.tenant_id,
            title=request.parameters.get("title", ""),
            problem=request.parameters.get("problem", ""),
            reasoning_summary=request.parameters.get("reasoning_summary", ""),
            expected_benefit=request.parameters.get("expected_benefit", ""),
            suggested_action=request.parameters.get("suggested_action", ""),
            evidence=request.parameters.get("evidence", []),
            risk=request.parameters.get("risk", "LOW"),
            confidence=request.parameters.get("confidence", 1.0),
            required_approval=request.parameters.get("required_approval", False),
            priority=request.parameters.get("priority", "NORMAL"),
        )
        return ToolResult(
            success=True,
            tool_name="create_recommendation",
            data=rec.model_dump(mode="json"),
            evidence=[f"Created recommendation '{rec.title}' with status PROPOSED."],
            correlation_id=request.correlation_id,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            tool_name="create_recommendation",
            error=str(exc),
            correlation_id=request.correlation_id,
        )

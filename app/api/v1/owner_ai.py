import uuid
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.database.models.owner_ai import OwnerAIExecution
from app.agents.owner_ai.orchestrator import OwnerAIOrchestrator
from app.agents.owner_ai.reports import ReportGenerator
from app.agents.owner_ai.recommendations import RecommendationService
from app.memory.service import MemoryService
from app.memory.schemas import (
    MemoryScope,
    MemoryType,
    MemoryCreateSchema,
    MemoryChangeProposalSchema,
)
from app.agents.owner_ai.schemas import (
    BusinessBriefSchema,
    WeeklyReviewSchema,
    RecommendationSchema,
)
from app.core.auth import resolve_actor_permissions
from app.core.context import get_actor_context
from app.core.exceptions import AppException

router = APIRouter(prefix="/owner-ai", tags=["Owner AI"])


def enforce_owner_actor(actor_perms: set[str] = Depends(resolve_actor_permissions)) -> None:
    """Enforce that only authenticated actors with the 'owner' role can access Owner AI endpoints."""
    actor = get_actor_context()
    if not actor or actor.role != "owner":
        raise AppException(
            code="PERMISSION_DENIED",
            message="Owner AI access is restricted strictly to platform owners.",
            status_code=403,
        )


class OwnerAIRunRequest(BaseModel):
    objective: str
    context: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None


class ProposalRequest(BaseModel):
    memory_scope: MemoryScope
    proposed_key: str
    proposed_type: MemoryType
    proposed_content: dict[str, Any]
    reason: str


@router.post("/run", status_code=status.HTTP_200_OK)
async def run_owner_ai(
    payload: OwnerAIRunRequest,
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(enforce_owner_actor),
) -> dict[str, Any]:
    tenant_id = get_tenant_id()
    orchestrator = OwnerAIOrchestrator(db)
    res = await orchestrator.orchestrate(
        tenant_id=tenant_id,
        objective=payload.objective,
        context=payload.context,
        correlation_id=payload.correlation_id,
    )
    return res.model_dump(mode="json")


@router.get("/status")
async def get_owner_ai_status(
    execution_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(enforce_owner_actor),
) -> list[dict[str, Any]]:
    tenant_id = get_tenant_id()
    filters = [OwnerAIExecution.tenant_id == tenant_id]
    if execution_id:
        filters.append(OwnerAIExecution.id == uuid.UUID(execution_id))

    stmt = select(OwnerAIExecution).where(and_(*filters)).order_by(OwnerAIExecution.started_at.desc())
    executions = (await db.execute(stmt)).scalars().all()

    return [
        {
            "execution_id": str(e.id),
            "tenant_id": str(e.tenant_id),
            "objective": e.objective,
            "status": e.status,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
            "agents_called": e.agents_called,
            "tasks_created": e.tasks_created,
            "confidence": e.confidence,
            "error": e.error,
        }
        for e in executions
    ]


@router.get("/recommendations", response_model=list[RecommendationSchema])
async def list_recommendations(
    status: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(enforce_owner_actor),
) -> list[RecommendationSchema]:
    tenant_id = get_tenant_id()
    service = RecommendationService(db)
    return await service.list_recommendations(tenant_id, status=status)


@router.get("/brief/daily", response_model=BusinessBriefSchema)
async def get_daily_brief(
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(enforce_owner_actor),
) -> BusinessBriefSchema:
    tenant_id = get_tenant_id()
    generator = ReportGenerator(db)
    return await generator.generate_daily_brief(tenant_id)


@router.get("/review/weekly", response_model=WeeklyReviewSchema)
async def get_weekly_review(
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(enforce_owner_actor),
) -> WeeklyReviewSchema:
    tenant_id = get_tenant_id()
    generator = ReportGenerator(db)
    return await generator.generate_weekly_review(tenant_id)


@router.get("/memory")
async def get_memory(
    objective: str = Query(default=""),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(enforce_owner_actor),
) -> dict[str, Any]:
    tenant_id = get_tenant_id()
    mem_service = MemoryService(db)
    context = await mem_service.get_relevant_context(tenant_id, objective=objective)
    return context.model_dump(mode="json")


@router.post("/memory/proposals", response_model=dict[str, Any])
async def create_memory_proposal(
    payload: ProposalRequest,
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(enforce_owner_actor),
) -> dict[str, Any]:
    tenant_id = get_tenant_id()
    mem_service = MemoryService(db)

    create_data = MemoryCreateSchema(
        memory_type=payload.proposed_type,
        key=payload.proposed_key,
        content=payload.proposed_content,
        source="owner_api_proposal",
    )

    item, proposal = await mem_service.save_memory_or_propose(
        scope=payload.memory_scope,
        tenant_id=tenant_id,
        create_data=create_data,
        source_agent="owner_api",
    )

    if proposal:
        return {"status": "PROPOSED", "proposal": proposal.model_dump(mode="json")}
    elif item:
        return {"status": "SAVED", "item": item.model_dump(mode="json")}

    return {"status": "SUCCESS"}

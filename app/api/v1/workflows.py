import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.database.models.workflow import WorkflowConfiguration
from app.schemas.phase2 import WorkflowCreateRequest, WorkflowResponse

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(db: AsyncSession = Depends(get_db_session)) -> list[WorkflowResponse]:
    tenant_id = get_tenant_id()
    stmt = select(WorkflowConfiguration).where(WorkflowConfiguration.tenant_id == tenant_id)
    wfs = (await db.execute(stmt)).scalars().all()
    return [
        WorkflowResponse(
            id=str(wf.id),
            tenant_id=str(wf.tenant_id),
            key=wf.key,
            name=wf.name,
            description=wf.description,
            trigger_type=wf.trigger_type or (wf.config_data or {}).get("trigger"),
            conditions=wf.conditions,
            actions=wf.actions,
            is_active=wf.is_active,
        )
        for wf in wfs
    ]


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: WorkflowCreateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> WorkflowResponse:
    tenant_id = get_tenant_id()

    wf = WorkflowConfiguration(
        tenant_id=tenant_id,
        key=body.key,
        name=body.name,
        description=body.description,
        trigger_type=body.trigger_type,
        trigger_config=body.trigger_config,
        conditions=body.conditions,
        actions=body.actions,
        max_execution_time=body.max_execution_time,
        max_steps=body.max_steps,
        max_retries=body.max_retries,
        is_active=body.is_active,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)

    return WorkflowResponse(
        id=str(wf.id),
        tenant_id=str(wf.tenant_id),
        key=wf.key,
        name=wf.name,
        description=wf.description,
        trigger_type=wf.trigger_type,
        conditions=wf.conditions,
        actions=wf.actions,
        is_active=wf.is_active,
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db_session)) -> WorkflowResponse:
    tenant_id = get_tenant_id()
    stmt = select(WorkflowConfiguration).where(
        and_(
            WorkflowConfiguration.id == uuid.UUID(workflow_id),
            WorkflowConfiguration.tenant_id == tenant_id,
        )
    )
    wf = (await db.execute(stmt)).scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow configuration not found")

    return WorkflowResponse(
        id=str(wf.id),
        tenant_id=str(wf.tenant_id),
        key=wf.key,
        name=wf.name,
        description=wf.description,
        trigger_type=wf.trigger_type,
        conditions=wf.conditions,
        actions=wf.actions,
        is_active=wf.is_active,
    )


@router.post("/{workflow_id}/enable", response_model=WorkflowResponse)
async def enable_workflow(workflow_id: str, db: AsyncSession = Depends(get_db_session)) -> WorkflowResponse:
    tenant_id = get_tenant_id()
    stmt = select(WorkflowConfiguration).where(
        and_(
            WorkflowConfiguration.id == uuid.UUID(workflow_id),
            WorkflowConfiguration.tenant_id == tenant_id,
        )
    )
    wf = (await db.execute(stmt)).scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow configuration not found")

    wf.is_active = True
    await db.commit()
    await db.refresh(wf)

    return WorkflowResponse(
        id=str(wf.id),
        tenant_id=str(wf.tenant_id),
        key=wf.key,
        name=wf.name,
        description=wf.description,
        trigger_type=wf.trigger_type,
        conditions=wf.conditions,
        actions=wf.actions,
        is_active=wf.is_active,
    )


@router.post("/{workflow_id}/disable", response_model=WorkflowResponse)
async def disable_workflow(workflow_id: str, db: AsyncSession = Depends(get_db_session)) -> WorkflowResponse:
    tenant_id = get_tenant_id()
    stmt = select(WorkflowConfiguration).where(
        and_(
            WorkflowConfiguration.id == uuid.UUID(workflow_id),
            WorkflowConfiguration.tenant_id == tenant_id,
        )
    )
    wf = (await db.execute(stmt)).scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow configuration not found")

    wf.is_active = False
    await db.commit()
    await db.refresh(wf)

    return WorkflowResponse(
        id=str(wf.id),
        tenant_id=str(wf.tenant_id),
        key=wf.key,
        name=wf.name,
        description=wf.description,
        trigger_type=wf.trigger_type,
        conditions=wf.conditions,
        actions=wf.actions,
        is_active=wf.is_active,
    )

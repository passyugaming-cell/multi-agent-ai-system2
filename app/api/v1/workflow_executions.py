import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.database.models.workflow import WorkflowExecution
from app.schemas.phase2 import ExecutionResponse

router = APIRouter(prefix="/workflow-executions", tags=["Workflow Executions"])


@router.get("", response_model=list[ExecutionResponse])
async def list_executions(db: AsyncSession = Depends(get_db_session)) -> list[ExecutionResponse]:
    tenant_id = get_tenant_id()
    stmt = select(WorkflowExecution).where(WorkflowExecution.tenant_id == tenant_id).order_by(WorkflowExecution.created_at.desc())
    execs = (await db.execute(stmt)).scalars().all()
    return [
        ExecutionResponse(
            id=str(e.id),
            tenant_id=str(e.tenant_id),
            workflow_id=str(e.workflow_id),
            event_id=e.event_id,
            status=e.status,
            current_step=e.current_step,
            context=e.context,
            result=e.result,
            error=e.error,
        )
        for e in execs
    ]


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: str, db: AsyncSession = Depends(get_db_session)) -> ExecutionResponse:
    tenant_id = get_tenant_id()
    stmt = select(WorkflowExecution).where(
        and_(
            WorkflowExecution.id == uuid.UUID(execution_id),
            WorkflowExecution.tenant_id == tenant_id,
        )
    )
    e = (await db.execute(stmt)).scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")

    return ExecutionResponse(
        id=str(e.id),
        tenant_id=str(e.tenant_id),
        workflow_id=str(e.workflow_id),
        event_id=e.event_id,
        status=e.status,
        current_step=e.current_step,
        context=e.context,
        result=e.result,
        error=e.error,
    )


@router.post("/{execution_id}/cancel", response_model=ExecutionResponse)
async def cancel_execution(execution_id: str, db: AsyncSession = Depends(get_db_session)) -> ExecutionResponse:
    tenant_id = get_tenant_id()
    stmt = select(WorkflowExecution).where(
        and_(
            WorkflowExecution.id == uuid.UUID(execution_id),
            WorkflowExecution.tenant_id == tenant_id,
        )
    )
    e = (await db.execute(stmt)).scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Execution not found")

    if e.status in ("COMPLETED", "FAILED", "CANCELLED"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel execution in status {e.status}")

    e.status = "CANCELLED"
    await db.commit()
    await db.refresh(e)

    return ExecutionResponse(
        id=str(e.id),
        tenant_id=str(e.tenant_id),
        workflow_id=str(e.workflow_id),
        event_id=e.event_id,
        status=e.status,
        current_step=e.current_step,
        context=e.context,
        result=e.result,
        error=e.error,
    )

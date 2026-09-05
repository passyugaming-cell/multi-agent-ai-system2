import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.core.tasks.service import TaskService
from app.core.exceptions import AppException
from app.schemas.phase2 import TaskCreateRequest, TaskResponse

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    status: str | None = Query(default=None),
    assigned_to: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> list[TaskResponse]:
    tenant_id = get_tenant_id()
    service = TaskService(db)
    tasks = await service.list_tasks(tenant_id, status=status, assigned_to=assigned_to)
    return [
        TaskResponse(
            id=str(t.id),
            tenant_id=str(t.tenant_id),
            title=t.title,
            description=t.description,
            task_type=t.task_type,
            priority=t.priority,
            status=t.status,
            assigned_to=t.assigned_to,
        )
        for t in tasks
    ]


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreateRequest,
    db: AsyncSession = Depends(get_db_session),
) -> TaskResponse:
    tenant_id = get_tenant_id()
    service = TaskService(db)
    t = await service.create_task(
        tenant_id=tenant_id,
        title=body.title,
        description=body.description,
        task_type=body.task_type,
        priority=body.priority,
        assigned_to=body.assigned_to,
    )
    return TaskResponse(
        id=str(t.id),
        tenant_id=str(t.tenant_id),
        title=t.title,
        description=t.description,
        task_type=t.task_type,
        priority=t.priority,
        status=t.status,
        assigned_to=t.assigned_to,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db_session)) -> TaskResponse:
    tenant_id = get_tenant_id()
    service = TaskService(db)
    try:
        t = await service.get_task(tenant_id, uuid.UUID(task_id))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return TaskResponse(
        id=str(t.id),
        tenant_id=str(t.tenant_id),
        title=t.title,
        description=t.description,
        task_type=t.task_type,
        priority=t.priority,
        status=t.status,
        assigned_to=t.assigned_to,
    )


@router.post("/{task_id}/assign", response_model=TaskResponse)
async def assign_task(
    task_id: str,
    assigned_to: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
) -> TaskResponse:
    tenant_id = get_tenant_id()
    service = TaskService(db)
    try:
        t = await service.assign_task(tenant_id, uuid.UUID(task_id), assigned_to=assigned_to)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return TaskResponse(
        id=str(t.id),
        tenant_id=str(t.tenant_id),
        title=t.title,
        description=t.description,
        task_type=t.task_type,
        priority=t.priority,
        status=t.status,
        assigned_to=t.assigned_to,
    )


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> TaskResponse:
    tenant_id = get_tenant_id()
    service = TaskService(db)
    try:
        t = await service.update_status(tenant_id, uuid.UUID(task_id), new_status="COMPLETED")
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return TaskResponse(
        id=str(t.id),
        tenant_id=str(t.tenant_id),
        title=t.title,
        description=t.description,
        task_type=t.task_type,
        priority=t.priority,
        status=t.status,
        assigned_to=t.assigned_to,
    )


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> TaskResponse:
    tenant_id = get_tenant_id()
    service = TaskService(db)
    try:
        t = await service.update_status(tenant_id, uuid.UUID(task_id), new_status="CANCELLED")
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return TaskResponse(
        id=str(t.id),
        tenant_id=str(t.tenant_id),
        title=t.title,
        description=t.description,
        task_type=t.task_type,
        priority=t.priority,
        status=t.status,
        assigned_to=t.assigned_to,
    )

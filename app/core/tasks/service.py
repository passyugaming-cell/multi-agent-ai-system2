import uuid
from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.workflow import Task, WorkflowExecution
from app.core.exceptions import AppError
from app.core.task_state import (
    apply_task_status_transition,
    validate_task_status_transition,
    ALLOWED_TASK_TRANSITIONS,
)

VALID_TASK_TRANSITIONS = {k.value: {v.value for v in vals} for k, vals in ALLOWED_TASK_TRANSITIONS.items()}


class TaskService:
    """Service layer managing Task lifecycle and tenant isolation."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def create_task(
        self,
        tenant_id: uuid.UUID,
        title: str,
        description: str | None = None,
        task_type: str = "general",
        priority: str = "NORMAL",
        assigned_to: str | None = None,
        assigned_agent: str | None = None,
        workflow_execution_id: uuid.UUID | None = None,
        source: str = "manual",
        due_at: datetime | None = None,
    ) -> Task:
        task = Task(
            tenant_id=tenant_id,
            title=title,
            description=description,
            task_type=task_type,
            priority=priority,
            status="ASSIGNED" if (assigned_to or assigned_agent) else "CREATED",
            source=source,
            assigned_to=assigned_to,
            assigned_agent=assigned_agent,
            workflow_execution_id=workflow_execution_id,
            due_at=due_at,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def get_task(self, tenant_id: uuid.UUID, task_id: uuid.UUID) -> Task:
        stmt = select(Task).where(and_(Task.id == task_id, Task.tenant_id == tenant_id))
        task = (await self.session.execute(stmt)).scalar_one_or_none()
        if not task:
            raise AppError("Task not found or access denied.", status_code=404)
        return task

    async def list_tasks(
        self,
        tenant_id: uuid.UUID,
        status: str | None = None,
        assigned_to: str | None = None,
    ) -> Sequence[Task]:
        filters = [Task.tenant_id == tenant_id]
        if status:
            filters.append(Task.status == status)
        if assigned_to:
            filters.append(Task.assigned_to == assigned_to)

        stmt = select(Task).where(and_(*filters)).order_by(Task.created_at.desc())
        return (await self.session.execute(stmt)).scalars().all()

    async def update_status(
        self,
        tenant_id: uuid.UUID,
        task_id: uuid.UUID,
        new_status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> Task:
        task = await self.get_task(tenant_id, task_id)

        apply_task_status_transition(task, new_status)

        if new_status == "COMPLETED" and result:
            task.result = result

        if error:
            task.error = error

        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def assign_task(self, tenant_id: uuid.UUID, task_id: uuid.UUID, assigned_to: str) -> Task:
        task = await self.get_task(tenant_id, task_id)
        task.assigned_to = assigned_to
        if task.status == "CREATED":
            apply_task_status_transition(task, "ASSIGNED")
        await self.session.commit()
        await self.session.refresh(task)
        return task

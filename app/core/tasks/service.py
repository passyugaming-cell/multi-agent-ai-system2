import uuid
from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.workflow import Task, WorkflowExecution
from app.core.exceptions import AppError


VALID_TASK_TRANSITIONS = {
    "CREATED": {"ASSIGNED", "IN_PROGRESS", "WAITING_APPROVAL", "WAITING_DATA", "COMPLETED", "FAILED", "BLOCKED", "CANCELLED"},
    "ASSIGNED": {"IN_PROGRESS", "WAITING_APPROVAL", "WAITING_DATA", "COMPLETED", "FAILED", "BLOCKED", "CANCELLED"},
    "IN_PROGRESS": {"WAITING_DATA", "WAITING_APPROVAL", "COMPLETED", "FAILED", "BLOCKED", "CANCELLED"},
    "WAITING_DATA": {"IN_PROGRESS", "CANCELLED"},
    "WAITING_APPROVAL": {"IN_PROGRESS", "CANCELLED"},
    "COMPLETED": set(),  # Terminal
    "FAILED": set(),     # Terminal
    "BLOCKED": {"IN_PROGRESS", "CANCELLED"},
    "CANCELLED": set(),  # Terminal
}


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
        current_status = task.status

        allowed_next = VALID_TASK_TRANSITIONS.get(current_status, set())
        if new_status not in allowed_next:
            raise AppError(
                f"Invalid task status transition from '{current_status}' to '{new_status}'",
                status_code=400,
            )

        task.status = new_status
        if new_status == "IN_PROGRESS" and not task.started_at:
            task.started_at = datetime.now(timezone.utc)
        elif new_status == "COMPLETED":
            task.completed_at = datetime.now(timezone.utc)
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
            task.status = "ASSIGNED"
        await self.session.commit()
        await self.session.refresh(task)
        return task

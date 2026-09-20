import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Set, Any
from app.core.exceptions import AppException, AppError
from app.database.models.workflow import Task

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_DATA = "WAITING_DATA"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


ALLOWED_TASK_TRANSITIONS: dict[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.CREATED: {
        TaskStatus.ASSIGNED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.CANCELLED,
    },
    TaskStatus.ASSIGNED: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.CANCELLED,
    },
    TaskStatus.IN_PROGRESS: {
        TaskStatus.WAITING_DATA,
        TaskStatus.WAITING_APPROVAL,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.BLOCKED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.WAITING_DATA: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    TaskStatus.WAITING_APPROVAL: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    },
    # Terminal statuses: COMPLETED, FAILED, BLOCKED, CANCELLED
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.BLOCKED: set(),
    TaskStatus.CANCELLED: set(),
}


def validate_task_status_transition(current_status: str, target_status: str) -> None:
    """Enforces state transition rules for Task entities."""
    if current_status == target_status:
        return

    try:
        curr_enum = TaskStatus(current_status)
    except ValueError:
        raise AppException(
            code="INVALID_TASK_STATE_TRANSITION",
            message=f"Unknown current task status: '{current_status}'.",
            status_code=400,
        )

    try:
        target_enum = TaskStatus(target_status)
    except ValueError:
        raise AppException(
            code="INVALID_TASK_STATE_TRANSITION",
            message=f"Unknown target task status: '{target_status}'.",
            status_code=400,
        )

    allowed = ALLOWED_TASK_TRANSITIONS.get(curr_enum, set())
    if target_enum not in allowed:
        logger.warning(
            "Rejected invalid task state transition: '%s' -> '%s'",
            current_status,
            target_status,
        )
        raise AppError(
            message=f"Invalid task status transition from '{current_status}' to '{target_status}'.",
            code="INVALID_TASK_STATE_TRANSITION",
            status_code=400,
        )


def apply_task_status_transition(task: Task, target_status: str) -> None:
    """
    Validates task status transition, applies target status, and manages timestamp side effects:
    - started_at: Preserved on re-entry to IN_PROGRESS (not reset if already set).
    - completed_at: Populated strictly on terminal states (COMPLETED, FAILED, CANCELLED).
    """
    validate_task_status_transition(task.status, target_status)
    target_enum = TaskStatus(target_status)

    now = datetime.now(timezone.utc)
    task.status = target_enum.value

    if target_enum == TaskStatus.IN_PROGRESS:
        if not task.started_at:
            task.started_at = now
    elif target_enum in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
        task.completed_at = now

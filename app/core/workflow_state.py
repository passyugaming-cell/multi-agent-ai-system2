import logging
from enum import Enum
from typing import Set
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


class WorkflowExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_RETRY = "WAITING_RETRY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    BLOCKED = "BLOCKED"


ALLOWED_WORKFLOW_EXECUTION_TRANSITIONS: dict[WorkflowExecutionStatus, Set[WorkflowExecutionStatus]] = {
    WorkflowExecutionStatus.PENDING: {
        WorkflowExecutionStatus.RUNNING,
        WorkflowExecutionStatus.CANCELLED,
    },
    WorkflowExecutionStatus.RUNNING: {
        WorkflowExecutionStatus.WAITING_APPROVAL,
        WorkflowExecutionStatus.WAITING_RETRY,
        WorkflowExecutionStatus.COMPLETED,
        WorkflowExecutionStatus.FAILED,
        WorkflowExecutionStatus.TIMED_OUT,
        WorkflowExecutionStatus.BLOCKED,
        WorkflowExecutionStatus.CANCELLED,
    },
    WorkflowExecutionStatus.WAITING_APPROVAL: {
        WorkflowExecutionStatus.RUNNING,
        WorkflowExecutionStatus.FAILED,
        WorkflowExecutionStatus.CANCELLED,
    },
    WorkflowExecutionStatus.WAITING_RETRY: {
        WorkflowExecutionStatus.RUNNING,
        WorkflowExecutionStatus.FAILED,
        WorkflowExecutionStatus.CANCELLED,
    },
    # Terminal statuses: COMPLETED, FAILED, CANCELLED, TIMED_OUT, BLOCKED
    WorkflowExecutionStatus.COMPLETED: set(),
    WorkflowExecutionStatus.FAILED: set(),
    WorkflowExecutionStatus.CANCELLED: set(),
    WorkflowExecutionStatus.TIMED_OUT: set(),
    WorkflowExecutionStatus.BLOCKED: set(),
}


def validate_workflow_execution_transition(current_status: str, target_status: str) -> None:
    """Enforces state transition rules for WorkflowExecution entities."""
    if current_status == target_status:
        return

    try:
        curr_enum = WorkflowExecutionStatus(current_status)
    except ValueError:
        curr_enum = None

    try:
        target_enum = WorkflowExecutionStatus(target_status)
    except ValueError:
        raise AppException(
            code="INVALID_WORKFLOW_STATE_TRANSITION",
            message=f"Unknown target workflow execution status: '{target_status}'.",
            status_code=400,
        )

    if curr_enum:
        allowed = ALLOWED_WORKFLOW_EXECUTION_TRANSITIONS.get(curr_enum, set())
        if target_enum not in allowed:
            logger.warning(
                "Rejected invalid workflow execution transition: '%s' -> '%s'",
                current_status,
                target_status,
            )
            raise AppException(
                code="INVALID_WORKFLOW_STATE_TRANSITION",
                message=f"Cannot transition workflow execution status from '{current_status}' to '{target_status}'.",
                status_code=400,
            )

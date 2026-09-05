import uuid
from typing import Any
from pydantic import BaseModel, Field


class EventPublishRequest(BaseModel):
    event_type: str = Field(..., description="Dot-notation event type e.g. order.created")
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="api_client")
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None


class EventResponse(BaseModel):
    event_id: str
    tenant_id: str
    event_type: str
    occurred_at: str
    source: str
    status: str = "published"


class WorkflowCreateRequest(BaseModel):
    key: str
    name: str
    description: str | None = None
    trigger_type: str | None = None
    trigger_config: dict[str, Any] | None = None
    conditions: list[dict[str, Any]] | None = None
    actions: list[dict[str, Any]] | None = None
    max_execution_time: int = 300
    max_steps: int = 50
    max_retries: int = 3
    is_active: bool = True


class WorkflowResponse(BaseModel):
    id: str
    tenant_id: str
    key: str
    name: str
    description: str | None = None
    trigger_type: str | None = None
    conditions: list[dict[str, Any]] | None = None
    actions: list[dict[str, Any]] | None = None
    is_active: bool


class ExecutionResponse(BaseModel):
    id: str
    tenant_id: str
    workflow_id: str
    event_id: str
    status: str
    current_step: int
    context: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


class TaskCreateRequest(BaseModel):
    title: str
    description: str | None = None
    task_type: str = "general"
    priority: str = "NORMAL"
    assigned_to: str | None = None


class TaskResponse(BaseModel):
    id: str
    tenant_id: str
    title: str
    description: str | None = None
    task_type: str
    priority: str
    status: str
    assigned_to: str | None = None


class ApprovalResponse(BaseModel):
    id: str
    tenant_id: str
    workflow_execution_id: str | None = None
    requested_by: str
    action_type: str
    target: str
    reason: str
    risk_level: str
    status: str


class ApprovalDecisionRequest(BaseModel):
    decided_by: str
    reason: str | None = None
    modified_params: dict[str, Any] | None = None

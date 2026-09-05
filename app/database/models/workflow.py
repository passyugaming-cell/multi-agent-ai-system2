import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Text, Boolean, Integer, Float, ForeignKey, UniqueConstraint, Index, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel


class WorkflowConfiguration(BaseModel):
    """Workflow configuration model."""

    __tablename__ = "workflow_configurations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_workflow_configurations_tenant_key"),
        Index("ix_workflow_configurations_tenant_active", "tenant_id", "is_active"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Executable workflow definition fields
    trigger_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    trigger_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    conditions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    actions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    max_execution_time: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    max_steps: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowExecution(BaseModel):
    """Workflow execution instance tracking."""

    __tablename__ = "workflow_executions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "workflow_id", "event_id", name="uq_workflow_executions_idempotency"),
        Index("ix_workflow_executions_tenant_status", "tenant_id", "status"),
        Index("ix_workflow_executions_next_retry", "next_retry_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    status: Mapped[str] = mapped_column(
        String(50), default="PENDING", nullable=False, index=True
    )  # PENDING, RUNNING, WAITING_APPROVAL, WAITING_RETRY, COMPLETED, FAILED, CANCELLED, TIMED_OUT, BLOCKED

    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    workflow = relationship("WorkflowConfiguration", back_populates="executions")
    history = relationship("WorkflowExecutionHistory", back_populates="execution", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="execution", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="execution", cascade="all, delete-orphan")


class WorkflowExecutionHistory(BaseModel):
    """Detailed audit history of workflow steps."""

    __tablename__ = "workflow_execution_history"
    __table_args__ = (
        Index("ix_workflow_execution_history_tenant_exec", "tenant_id", "workflow_execution_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_or_source: Mapped[str] = mapped_column(String(255), default="workflow_engine", nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    execution = relationship("WorkflowExecution", back_populates="history")


class Task(BaseModel):
    """Task model."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_tenant_status", "tenant_id", "status"),
        Index("ix_tasks_tenant_assigned", "tenant_id", "assigned_to"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(String(100), default="general", nullable=False)
    priority: Mapped[str] = mapped_column(String(50), default="NORMAL", nullable=False) # LOW, NORMAL, HIGH, CRITICAL

    status: Mapped[str] = mapped_column(
        String(50), default="CREATED", nullable=False, index=True
    )  # CREATED, ASSIGNED, IN_PROGRESS, WAITING_DATA, WAITING_APPROVAL, COMPLETED, FAILED, BLOCKED, CANCELLED

    source: Mapped[str] = mapped_column(String(100), default="manual", nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    workflow_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    execution = relationship("WorkflowExecution", back_populates="tasks")


class Approval(BaseModel):
    """Human approval request model for high risk operations."""

    __tablename__ = "approvals"
    __table_args__ = (
        Index("ix_approvals_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=False) # LOW, MEDIUM, HIGH, CRITICAL
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(
        String(50), default="PENDING", nullable=False, index=True
    )  # PENDING, APPROVED, REJECTED, MODIFIED, EXPIRED, CANCELLED

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    execution = relationship("WorkflowExecution", back_populates="approvals")


class EventRecord(BaseModel):
    """Persistence record for events."""

    __tablename__ = "event_records"
    __table_args__ = (
        Index("ix_event_records_tenant_type", "tenant_id", "event_type"),
        UniqueConstraint("tenant_id", "event_id", name="uq_event_records_tenant_event_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    causation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

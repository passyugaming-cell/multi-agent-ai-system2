import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Text, Boolean, Integer, Float, ForeignKey, Index, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class OwnerAIExecution(BaseModel):
    """Audit table recording Owner AI orchestration runs, decisions, agent calls, and execution state."""

    __tablename__ = "owner_ai_executions"
    __table_args__ = (
        Index("ix_owner_ai_executions_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="CREATED", nullable=False, index=True
    )  # CREATED, PLANNING, DELEGATING, WAITING_FOR_AGENTS, ANALYZING, WAITING_APPROVAL, COMPLETED, PARTIAL, FAILED, BLOCKED, CANCELLED

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agents_called: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    tasks_created: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    events_used: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    recommendations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    approvals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)

    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)


class Recommendation(BaseModel):
    """Structured Owner AI recommendation tracking, evidence, required approval, and feedback state."""

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_tenant_status", "tenant_id", "status"),
        Index("ix_recommendations_tenant_priority", "tenant_id", "priority"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("owner_ai_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[Any]] = mapped_column(JSONB, default=list, nullable=False)
    reasoning_summary: Mapped[str] = mapped_column(Text, nullable=False)
    expected_benefit: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[str] = mapped_column(String(50), default="LOW", nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)

    required_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    priority: Mapped[str] = mapped_column(String(50), default="NORMAL", nullable=False)  # LOW, NORMAL, HIGH, URGENT
    status: Mapped[str] = mapped_column(
        String(50), default="PROPOSED", nullable=False, index=True
    )  # PROPOSED, ACCEPTED, REJECTED, DEFERRED, EXECUTED, EXPIRED

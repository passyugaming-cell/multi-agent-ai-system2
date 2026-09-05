import uuid
from typing import Any
from sqlalchemy import String, Text, Float, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class AgentExecution(BaseModel):
    """Audit log and history for Specialist AI Agent executions."""

    __tablename__ = "agent_executions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="COMPLETED")
    finding: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    needs_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actions: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    execution_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Text, Boolean, Integer, Float, ForeignKey, UniqueConstraint, Index, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class BusinessMemory(BaseModel):
    """Durable business-level memory item (strategy, policies, goals, decisions)."""

    __tablename__ = "business_memories"
    __table_args__ = (
        Index("ix_business_memories_tenant_key", "tenant_id", "key"),
        Index("ix_business_memories_type_status", "memory_type", "status"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    is_platform_wide: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # FACT, DECISION, PREFERENCE, POLICY, GOAL, CONSTRAINT, HISTORY, INSIGHT
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(100), default="system", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False, index=True)  # ACTIVE, OUTDATED, ARCHIVED, PENDING_REVIEW
    importance: Mapped[str] = mapped_column(String(50), default="NORMAL", nullable=False)  # LOW, NORMAL, HIGH, CRITICAL
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class ClientMemory(BaseModel):
    """Durable tenant-isolated client memory item."""

    __tablename__ = "client_memories"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_client_memories_tenant_key"),
        Index("ix_client_memories_tenant_status", "tenant_id", "status"),
        Index("ix_client_memories_tenant_type", "tenant_id", "memory_type"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # FACT, DECISION, PREFERENCE, POLICY, GOAL, CONSTRAINT, HISTORY, INSIGHT
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(100), default="system", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False, index=True)  # ACTIVE, OUTDATED, ARCHIVED, PENDING_REVIEW
    importance: Mapped[str] = mapped_column(String(50), default="NORMAL", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class MemoryChangeProposal(BaseModel):
    """Change proposal for updating important business or client memory requiring validation/approval."""

    __tablename__ = "memory_change_proposals"
    __table_args__ = (
        Index("ix_memory_change_proposals_tenant_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    memory_scope: Mapped[str] = mapped_column(String(50), nullable=False)  # BUSINESS, CLIENT
    proposed_key: Mapped[str] = mapped_column(String(255), nullable=False)
    proposed_type: Mapped[str] = mapped_column(String(50), nullable=False)
    proposed_content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_agent: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)  # PENDING, APPROVED, REJECTED
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("approvals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

import uuid
from typing import Any
from sqlalchemy import String, Text, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class AIGuardrail(BaseModel):
    """Database-backed AI Guardrails for tenant system operations."""

    __tablename__ = "ai_guardrails"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_ai_guardrails_tenant_key"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_definition: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(50), default="CRITICAL", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

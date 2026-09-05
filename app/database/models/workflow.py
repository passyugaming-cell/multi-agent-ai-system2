import uuid
from typing import Any
from sqlalchemy import String, Text, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class WorkflowConfiguration(BaseModel):
    """Minimal workflow configuration representation for Phase 1.5."""

    __tablename__ = "workflow_configurations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_workflow_configurations_tenant_key"),
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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

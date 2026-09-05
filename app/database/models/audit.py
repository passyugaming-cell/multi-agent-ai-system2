import uuid
from typing import Any
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class ProvisioningAudit(BaseModel):
    """Audit log for tenant lifecycle and provisioning actions."""

    __tablename__ = "provisioning_audits"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actor: Mapped[str] = mapped_column(String(100), default="system", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(String(50), default="SUCCESS", nullable=False)
    metadata_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

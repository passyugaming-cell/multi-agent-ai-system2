import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class Tenant(BaseModel):
    """Tenant entity representing an isolated client/organization."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Client Lifecycle tracking
    lifecycle_state: Mapped[str] = mapped_column(String(50), default="PROSPECT", nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    state_transition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transition_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

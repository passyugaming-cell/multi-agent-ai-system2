import uuid
from typing import Any
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class BusinessProfile(BaseModel):
    """BusinessProfile entity storing tenant business configuration."""

    __tablename__ = "business_profiles"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    operating_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    payment_methods: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    shipping_information: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    return_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    exchange_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund_policy: Mapped[str | None] = mapped_column(Text, nullable=True)

import uuid
from decimal import Decimal
from sqlalchemy import String, Text, Boolean, Numeric, Integer, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class AIUsageRecord(BaseModel):
    """AIUsageRecord entity tracking tenant AI gateway execution metadata and costs."""

    __tablename__ = "ai_usage_records"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    usage_status: Mapped[str] = mapped_column(String(50), default="EXACT", nullable=False)  # EXACT / UNKNOWN
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_ai_usage_tenant_created", "tenant_id", "created_at"),
        Index("idx_ai_usage_tenant_task", "tenant_id", "task_type"),
    )

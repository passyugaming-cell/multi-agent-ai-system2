import uuid
from typing import Any
from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class Message(BaseModel):
    """Message entity representing individual messages within a conversation."""

    __tablename__ = "messages"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # INBOUND / OUTBOUND
    message_type: Mapped[str] = mapped_column(String(50), default="TEXT", nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        Index("idx_messages_tenant_conversation", "tenant_id", "conversation_id"),
        Index("idx_messages_tenant_external_id", "tenant_id", "external_message_id"),
        Index("idx_messages_tenant_created", "tenant_id", "created_at"),
    )

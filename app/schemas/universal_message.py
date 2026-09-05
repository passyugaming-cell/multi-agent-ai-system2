from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class UniversalMessage(BaseModel):
    """Normalized universal message schema used across all integrations and Universal Core."""

    model_config = ConfigDict(from_attributes=True)

    message_id: UUID | None = None
    tenant_id: UUID
    conversation_id: UUID | None = None
    customer_id: UUID | None = None
    channel: str = "whatsapp"
    external_message_id: str | None = None
    direction: Literal["INBOUND", "OUTBOUND"] = "INBOUND"
    message_type: Literal["TEXT", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT", "OTHER"] = "TEXT"
    text: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

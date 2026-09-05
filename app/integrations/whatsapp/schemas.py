from typing import Any, List, Optional
from pydantic import BaseModel, Field


class WhatsAppProfile(BaseModel):
    name: Optional[str] = None


class WhatsAppContact(BaseModel):
    profile: Optional[WhatsAppProfile] = None
    wa_id: str


class WhatsAppTextMessage(BaseModel):
    body: str


class WhatsAppMedia(BaseModel):
    id: str
    mime_type: Optional[str] = None
    caption: Optional[str] = None


class WhatsAppWebhookMessage(BaseModel):
    from_: str = Field(..., alias="from")
    id: str
    timestamp: str
    type: str = "text"
    text: Optional[WhatsAppTextMessage] = None
    image: Optional[WhatsAppMedia] = None
    video: Optional[WhatsAppMedia] = None
    audio: Optional[WhatsAppMedia] = None
    document: Optional[WhatsAppMedia] = None


class WhatsAppValue(BaseModel):
    messaging_product: str = "whatsapp"
    metadata: dict[str, Any] = Field(default_factory=dict)
    contacts: Optional[List[WhatsAppContact]] = None
    messages: Optional[List[WhatsAppWebhookMessage]] = None


class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str = "messages"


class WhatsAppEntry(BaseModel):
    id: str
    changes: List[WhatsAppChange]


class WhatsAppWebhookPayload(BaseModel):
    object: str = "whatsapp_business_account"
    entry: List[WhatsAppEntry]

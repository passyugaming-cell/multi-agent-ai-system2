import uuid
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict

ConnectionStatus = Literal[
    "DISCONNECTED",
    "CONNECTING",
    "CONNECTED",
    "ACTIVE",
    "ERROR",
    "RECONNECTING",
    "EXPIRED",
    "REVOKED",
    "DISABLED",
]

CredentialType = Literal["api_key", "oauth2", "bearer_token", "basic_auth"]
ExecutionStatus = Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "RETRYING"]


class IntegrationBase(BaseModel):
    integration_key: str = Field(..., max_length=100)
    provider_key: str = Field(..., max_length=100)
    display_name: str = Field(..., max_length=255)
    category: str = Field(default="general", max_length=100)
    configuration: dict[str, Any] | None = None


class IntegrationCreate(IntegrationBase):
    pass


class IntegrationResponse(IntegrationBase):
    id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    status: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrationConnectionCreate(BaseModel):
    integration_id: uuid.UUID
    external_account_id: str | None = None
    meta_data: dict[str, Any] | None = None
    credentials: dict[str, Any]  # Secrets to be encrypted at rest


class IntegrationConnectionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    integration_id: uuid.UUID
    status: ConnectionStatus
    external_account_id: str | None = None
    meta_data: dict[str, Any] | None = None
    last_connected_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OperationExecutionRequest(BaseModel):
    operation: str
    params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    correlation_id: str | None = None


class OperationExecutionResult(BaseModel):
    execution_id: uuid.UUID
    connection_id: uuid.UUID
    operation: str
    status: ExecutionStatus
    result: dict[str, Any] | None = None
    error_code: str | None = None
    safe_error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    retry_count: int = 0


class WebhookConfigCreate(BaseModel):
    connection_id: uuid.UUID | None = None
    webhook_type: Literal["INBOUND", "OUTBOUND"]
    url: str | None = None
    secret: str | None = None
    event_types: list[str] | None = None


class WebhookConfigResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    connection_id: uuid.UUID | None = None
    webhook_type: str
    url: str | None = None
    event_types: list[str] | None = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InboundWebhookPayload(BaseModel):
    provider: str
    event_type: str
    payload: dict[str, Any]
    headers: dict[str, str] = Field(default_factory=dict)
    signature: str | None = None

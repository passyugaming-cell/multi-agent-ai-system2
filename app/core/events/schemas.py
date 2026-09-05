import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field, field_validator


class EventSchema(BaseModel):
    """Universal Event Schema according to Phase 2 specs."""

    event_id: str = Field(..., description="Unique event identifier")
    tenant_id: str = Field(..., description="Tenant ID to enforce isolation")
    event_type: str = Field(..., description="Dot-notation event type e.g. order.created")
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of occurrence")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event payload (no secrets allowed)")
    source: str = Field(..., description="Source service or component")
    correlation_id: str | None = Field(default=None, description="Traces workflow or chain of events")
    causation_id: str | None = Field(default=None, description="Direct cause event_id")
    idempotency_key: str | None = Field(default=None, description="Key for idempotency check")
    schema_version: int = Field(default=1, description="Event schema version")

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id_valid_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("tenant_id must be a valid UUID string")
        return v

    @field_validator("payload")
    @classmethod
    def ensure_no_secrets_in_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        secret_keys = {"password", "secret", "api_key", "token", "jwt", "private_key"}
        for key in v.keys():
            if any(s in key.lower() for s in secret_keys):
                raise ValueError(f"Event payload must not contain secret fields like '{key}'")
        return v

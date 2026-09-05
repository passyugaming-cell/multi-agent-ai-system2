from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field, field_validator


class MemoryType(str, Enum):
    FACT = "FACT"
    DECISION = "DECISION"
    PREFERENCE = "PREFERENCE"
    POLICY = "POLICY"
    GOAL = "GOAL"
    CONSTRAINT = "CONSTRAINT"
    HISTORY = "HISTORY"
    INSIGHT = "INSIGHT"


class MemoryScope(str, Enum):
    BUSINESS = "BUSINESS"
    CLIENT = "CLIENT"


class MemoryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    OUTDATED = "OUTDATED"
    ARCHIVED = "ARCHIVED"
    PENDING_REVIEW = "PENDING_REVIEW"


class MemoryImportance(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MemoryItemSchema(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    is_business: bool = False
    memory_type: MemoryType
    key: str
    content: dict[str, Any]
    source: str = "system"
    confidence: float = 1.0
    status: MemoryStatus = MemoryStatus.ACTIVE
    importance: MemoryImportance = MemoryImportance.NORMAL
    version: int = 1
    expires_at: datetime | None = None
    last_verified_at: datetime | None = None
    meta_data: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return round(v, 4)


class MemoryCreateSchema(BaseModel):
    memory_type: MemoryType
    key: str
    content: dict[str, Any]
    source: str = "system"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: MemoryImportance = MemoryImportance.NORMAL
    expires_at: datetime | None = None
    meta_data: dict[str, Any] | None = None


class MemoryUpdateSchema(BaseModel):
    content: dict[str, Any] | None = None
    memory_type: MemoryType | None = None
    source: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: MemoryStatus | None = None
    importance: MemoryImportance | None = None
    expires_at: datetime | None = None
    meta_data: dict[str, Any] | None = None


class MemoryChangeProposalSchema(BaseModel):
    id: uuid.UUID | None = None
    tenant_id: uuid.UUID | None = None
    memory_scope: MemoryScope
    proposed_key: str
    proposed_type: MemoryType
    proposed_content: dict[str, Any]
    reason: str
    source_agent: str
    status: str = "PENDING"
    approval_id: uuid.UUID | None = None
    created_at: datetime | None = None


class MemoryContextSchema(BaseModel):
    tenant_id: uuid.UUID
    business_memories: list[MemoryItemSchema] = Field(default_factory=list)
    client_memories: list[MemoryItemSchema] = Field(default_factory=list)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

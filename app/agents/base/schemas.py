from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, Field, field_validator


class AgentRequestStatus(str, Enum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    WAITING_DATA = "WAITING_DATA"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class AgentRequest(BaseModel):
    """Machine-to-machine contract for invoking specialist agents."""

    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    tenant_id: uuid.UUID
    source: str = "api"
    source_agent: str | None = None
    target_agent: str
    task_type: str
    objective: str
    context: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    requested_action: str | None = None
    correlation_id: str | None = None
    delegation_depth: int = 0


class AgentResult(BaseModel):
    """Machine-to-machine result output from specialist agents."""

    request_id: str
    agent: str
    status: AgentRequestStatus
    finding: str | None = None
    evidence: list[Any] = Field(default_factory=list)
    recommendation: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    needs_approval: bool = False
    approval_id: str | None = None
    error: str | None = None
    correlation_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("confidence")
    @classmethod
    def validate_confidence_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence must be a bounded value between 0.0 and 1.0")
        return round(v, 4)


class ToolRequest(BaseModel):
    """Structured request for tool invocation."""

    tool_name: str
    tenant_id: uuid.UUID
    parameters: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class ToolResult(BaseModel):
    """Structured result from tool execution."""

    success: bool
    tool_name: str
    data: Any | None = None
    error: str | None = None
    evidence: list[Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class AgentConfig(BaseModel):
    """Database/config-driven settings for individual agents."""

    agent_name: str
    enabled: bool = True
    allowed_tools: list[str] = Field(default_factory=list)
    risk_policy: dict[str, Any] = Field(default_factory=dict)
    model_name: str = "gemini-3.1-flash-lite"
    max_delegation_depth: int = 3
    max_ai_calls: int = 5

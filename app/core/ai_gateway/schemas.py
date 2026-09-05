from decimal import Decimal
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class AIRequest(BaseModel):
    """Normalized request sent to AIGateway."""

    tenant_id: UUID
    task_type: str
    system_instruction: str
    user_message: str
    context: dict[str, Any] = Field(default_factory=dict)
    temperature: float | None = None
    max_output_tokens: int | None = None
    response_schema: type[BaseModel] | None = None


class AIResponse(BaseModel):
    """Normalized response returned from AIGateway."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: Decimal | None = None
    finish_reason: str | None = None
    request_id: str
    structured_output: Any | None = None
    usage_status: str = "EXACT"  # EXACT / UNKNOWN

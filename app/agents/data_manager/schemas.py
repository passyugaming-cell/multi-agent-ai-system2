from typing import Any
from pydantic import BaseModel, Field


class DataManagerOutputSchema(BaseModel):
    """Structured AI output schema for AI Data Manager."""

    is_valid: bool = Field(description="True if data validation passed with no missing required fields or conflicts.")
    finding: str = Field(description="Validation finding, field mapping summary, or error report.")
    evidence: list[dict[str, Any]] = Field(default_factory=list, description="Factual validation evidence.")
    missing_fields: list[str] = Field(default_factory=list, description="List of missing required fields.")
    invalid_fields: list[str] = Field(default_factory=list, description="List of invalid fields.")
    conflicts_detected: list[str] = Field(default_factory=list, description="List of detected data conflicts or duplicate records.")
    recommendation: str = Field(description="Correction recommendation or import instruction.")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Validation confidence score bounded 0.0 to 1.0.")
    requires_change_request: bool = Field(default=False, description="True if a formal data change request/approval is required.")

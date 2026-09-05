from typing import Any
from pydantic import BaseModel, Field


class SalesOutputSchema(BaseModel):
    """Structured AI output schema for Sales reasoning."""

    finding: str = Field(description="Summary of lead status, conversation analysis, or inquiry.")
    evidence: list[dict[str, Any]] = Field(default_factory=list, description="Factual evidence from DB tools (e.g. products, prices, conversation history).")
    recommendation: str = Field(description="Sales recommendation or next step.")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Confidence score bounded 0.0 to 1.0.")
    proposed_discount_percent: float | None = Field(default=None, description="Proposed discount percentage if recommending a discount.")
    requires_approval: bool = Field(default=False, description="True if proposed action/discount exceeds authorization limits.")
    followup_task_needed: bool = Field(default=False, description="True if a follow-up task should be created.")
    task_title: str | None = Field(default=None, description="Title for follow-up task.")
    task_description: str | None = Field(default=None, description="Description for follow-up task.")

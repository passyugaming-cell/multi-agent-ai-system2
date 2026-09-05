from typing import Any
from pydantic import BaseModel, Field


class ClientManagerOutputSchema(BaseModel):
    """Structured AI output schema for AI Client Manager."""

    finding: str = Field(description="Summary of tenant onboarding status, readiness, or blockers.")
    evidence: list[dict[str, Any]] = Field(default_factory=list, description="Factual evidence from DB and deterministic readiness calculator.")
    recommendation: str = Field(description="Client management or onboarding recommendation.")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Confidence score bounded 0.0 to 1.0.")
    missing_configurations: list[str] = Field(default_factory=list, description="List of missing required configurations.")
    onboarding_task_needed: bool = Field(default=False, description="True if an onboarding task should be created.")
    task_title: str | None = Field(default=None, description="Title for onboarding task.")
    task_description: str | None = Field(default=None, description="Description for onboarding task.")
    request_config_change: bool = Field(default=False, description="True if requesting configuration changes.")

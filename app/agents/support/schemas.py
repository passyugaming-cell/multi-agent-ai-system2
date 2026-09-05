from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SupportDiagnosisOutputSchema(BaseModel):
    """Structured AI output schema for AI Support incident diagnosis."""

    observed_evidence: list[str] = Field(default_factory=list, description="Observed factual logs, health status, or error messages.")
    possible_cause: str = Field(description="Inferred probable cause of the incident.")
    incident_severity: IncidentSeverity = Field(default=IncidentSeverity.MEDIUM, description="Incident classification.")
    recommendation: str = Field(description="Recommended fix or remediation step.")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0, description="Diagnosis confidence bounded 0.0 to 1.0.")
    support_task_needed: bool = Field(default=False, description="True if a support incident task should be created.")
    task_title: str | None = Field(default=None, description="Title for support task.")
    requires_high_risk_remediation: bool = Field(default=False, description="True if remediation involves high-risk production changes.")

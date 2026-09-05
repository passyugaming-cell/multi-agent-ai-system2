from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class DataCategoryLabel(str, Enum):
    ACTUAL = "ACTUAL"
    ESTIMATE = "ESTIMATE"
    FORECAST = "FORECAST"
    RECOMMENDATION = "RECOMMENDATION"


class AnalyticsMetric(BaseModel):
    metric_name: str
    value: Any
    category_label: DataCategoryLabel = DataCategoryLabel.ACTUAL
    period: str | None = None
    notes: str | None = None


class AnalystOutputSchema(BaseModel):
    """Structured AI output schema for AI Analyst."""

    finding: str = Field(description="Summary of analytical findings or performance analysis.")
    metrics: list[AnalyticsMetric] = Field(default_factory=list, description="Calculated analytics metrics explicitly labeled as ACTUAL, ESTIMATE, FORECAST, or RECOMMENDATION.")
    evidence: list[dict[str, Any]] = Field(default_factory=list, description="Factual DB analytics data.")
    recommendation: str = Field(description="Strategic or operational recommendation.")
    confidence: float = Field(default=0.90, ge=0.0, le=1.0, description="Analysis confidence bounded 0.0 to 1.0.")

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Dict, Optional
from pydantic import BaseModel, Field, field_validator

from app.agents.owner_ai.health import BusinessHealthResult, ClientHealthResult


class RecommendationStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    EXECUTED = "EXECUTED"
    EXPIRED = "EXPIRED"


class RecommendationPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class RecommendationSchema(BaseModel):
    recommendation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    title: str
    problem: str
    evidence: List[Any] = Field(default_factory=list)
    reasoning_summary: str
    expected_benefit: str
    risk: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    suggested_action: str
    required_approval: bool = False
    approval_id: Optional[uuid.UUID] = None
    priority: RecommendationPriority = RecommendationPriority.NORMAL
    status: RecommendationStatus = RecommendationStatus.PROPOSED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return round(v, 4)


class BusinessBriefSchema(BaseModel):
    report_id: str = Field(default_factory=lambda: f"brief_{uuid.uuid4().hex[:10]}")
    tenant_id: uuid.UUID
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    period: str = "daily"
    health: BusinessHealthResult
    key_facts: List[str] = Field(default_factory=list)
    insights: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    pending_approvals: List[Dict[str, Any]] = Field(default_factory=list)
    priority_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[RecommendationSchema] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    data_freshness: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WeeklyReviewSchema(BaseModel):
    report_id: str = Field(default_factory=lambda: f"review_{uuid.uuid4().hex[:10]}")
    tenant_id: uuid.UUID
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    period: str = "weekly"
    health: BusinessHealthResult
    weekly_performance: Dict[str, Any] = Field(default_factory=dict)
    revenue_trend: str = "STABLE"
    sales_trend: str = "STABLE"
    customer_trend: str = "STABLE"
    support_trend: str = "STABLE"
    automation_performance: Dict[str, Any] = Field(default_factory=dict)
    ai_usage_summary: Dict[str, Any] = Field(default_factory=dict)
    client_health_movement: List[Dict[str, Any]] = Field(default_factory=list)
    anomalies: List[str] = Field(default_factory=list)
    decisions_made: List[str] = Field(default_factory=list)
    completed_actions: List[str] = Field(default_factory=list)
    failed_actions: List[str] = Field(default_factory=list)
    unresolved_risks: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    strategic_recommendations: List[RecommendationSchema] = Field(default_factory=list)
    next_week_priorities: List[str] = Field(default_factory=list)
    forecasts: Dict[str, Any] = Field(default_factory=dict, description="Clearly labeled AI forecasts")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

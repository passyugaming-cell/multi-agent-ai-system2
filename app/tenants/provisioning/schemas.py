import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class ChecklistItemBase(BaseModel):
    key: str = Field(..., description="Unique key for checklist item")
    title: str = Field(..., description="Title of checklist item")
    description: Optional[str] = Field(None, description="Detailed description")
    category: str = Field(..., description="Category group")
    required: bool = Field(True, description="Whether item is required for readiness")


class ChecklistItemCreate(ChecklistItemBase):
    pass


class ChecklistItemUpdate(BaseModel):
    status: Optional[str] = Field(None, description="Status: PENDING, IN_PROGRESS, COMPLETED, BLOCKED, SKIPPED")
    completion_percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    metadata_info: Optional[dict[str, Any]] = None


class ChecklistItemResponse(ChecklistItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    status: str
    completion_percentage: float
    completed_at: Optional[datetime] = None
    metadata_info: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class ChecklistSummary(BaseModel):
    total: int
    completed: int
    pending: int
    completion_percentage: float


class ReadinessCategoryScore(BaseModel):
    category: str
    weight: float
    score: float
    percentage: float
    status: str


class ReadinessResultSchema(BaseModel):
    score: float = Field(..., ge=0.0, le=100.0, description="Overall readiness score percentage")
    percentage: float = Field(..., ge=0.0, le=100.0)
    completed_requirements: list[str] = Field(default_factory=list)
    incomplete_requirements: list[str] = Field(default_factory=list)
    blocking_requirements: list[str] = Field(default_factory=list)
    category_scores: dict[str, float] = Field(default_factory=dict)
    readiness_status: str = Field(..., description="NOT_READY, NEARLY_READY, READY")


class ProvisioningResponse(BaseModel):
    tenant_id: uuid.UUID
    lifecycle_state: str
    provisioning_status: str
    readiness_score: float
    checklist: ChecklistSummary
    initialized_components: list[str]
    warnings: list[str]
    blocking_items: list[str]


class OnboardingSummaryResponse(BaseModel):
    tenant_id: uuid.UUID
    lifecycle_state: str
    readiness_score: float
    readiness_status: str
    checklist_summary: ChecklistSummary
    checklist_items: list[ChecklistItemResponse]
    blocking_items: list[str]
    warnings: list[str]


class LifecycleTransitionRequest(BaseModel):
    target_state: str = Field(..., description="Target lifecycle state")
    reason: Optional[str] = Field(None, description="Reason for transition")


class LifecycleTransitionResponse(BaseModel):
    tenant_id: uuid.UUID
    previous_state: Optional[str]
    current_state: str
    transition_timestamp: datetime
    transition_reason: Optional[str]

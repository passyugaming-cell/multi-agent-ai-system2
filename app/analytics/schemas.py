from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MetricValueSchema(BaseModel):
    """Universal metric output structure."""
    key: str
    name: str
    current_value: Decimal | float | int | str
    previous_value: Optional[Decimal | float | int | str] = None
    change_absolute: Optional[Decimal | float | int | str] = None
    change_percentage: Optional[float] = None
    trend_direction: str = "STABLE"  # UP, DOWN, STABLE, INSUFFICIENT_DATA
    unit: str = "count"  # IDR, USD, count, percentage, tokens, credits, ms
    status: str = "HEALTHY"  # HEALTHY, WARNING, CRITICAL, NO_DATA
    target: Optional[Decimal | float | int] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KPISchema(BaseModel):
    """Reusable KPI object."""
    key: str
    name: str
    value: Decimal | float | int | str
    unit: str
    period: str  # 30d, 7d, 24h, 12m
    previous_value: Optional[Decimal | float | int | str] = None
    change: Optional[Decimal | float | int | str] = None
    change_percentage: Optional[float] = None
    trend: str = "STABLE"  # UP, DOWN, STABLE, INSUFFICIENT_DATA
    target: Optional[Decimal | float | int] = None
    status: str = "HEALTHY"  # HEALTHY, WARNING, CRITICAL, NO_DATA
    source: str = "system"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FinancialAnalyticsSchema(BaseModel):
    tenant_id: Optional[str] = None
    period_start: datetime
    period_end: datetime
    total_revenue: Decimal
    mrr: Decimal
    arr: Decimal
    subscription_revenue: Decimal
    setup_revenue: Decimal
    addon_revenue: Decimal
    custom_service_revenue: Decimal
    outstanding_payments: Decimal
    failed_payments_amount: Decimal
    successful_payments_amount: Decimal
    refunds_amount: Decimal
    arpc: Decimal  # Average Revenue Per Client / Customer
    revenue_growth_pct: float
    revenue_by_plan: Dict[str, Decimal]
    revenue_by_type: Dict[str, Decimal]
    revenue_by_tenant: Optional[Dict[str, Decimal]] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClientAnalyticsSchema(BaseModel):
    total_clients: int
    active_clients: int
    new_clients: int
    churned_clients: int
    reactivated_clients: int
    trial_clients: int
    active_subscriptions: int
    suspended_clients: int
    expired_clients: int
    at_risk_clients: int
    clients_by_plan: Dict[str, int]
    clients_by_lifecycle: Dict[str, int]
    client_growth_pct: float
    health_summary: Dict[str, Any]  # Reused ClientHealth score distribution
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SalesFunnelStageSchema(BaseModel):
    stage_name: str
    count: int
    conversion_rate: float  # Percentage from previous stage
    drop_off_count: int
    drop_off_rate: float


class SalesAnalyticsSchema(BaseModel):
    total_leads: int
    qualified_leads: int
    consultations: int
    proposals: int
    payments: int
    onboardings: int
    active_clients: int
    overall_conversion_rate: float
    average_deal_value: Decimal
    sales_cycle_days: float
    revenue_by_source: Dict[str, Decimal]
    funnel_stages: List[SalesFunnelStageSchema]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CustomerAnalyticsSchema(BaseModel):
    total_customers: int
    active_customers: int
    new_customers: int
    returning_customers: int
    inactive_customers: int
    customer_growth_pct: float
    order_frequency: float
    average_order_value: Decimal
    total_customer_revenue: Decimal
    repeat_purchase_rate: float
    customer_segments: Dict[str, int]  # Only deterministic criteria supported
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AIAnalyticsSchema(BaseModel):
    total_requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    ai_credits_used: int
    ai_credits_remaining: Optional[int] = None
    ai_cost: Decimal
    success_rate: float
    failure_rate: float
    average_latency_ms: float
    requests_by_tenant: Optional[Dict[str, int]] = None
    requests_by_agent: Dict[str, int]
    requests_by_model: Dict[str, str | int]
    cost_trend: str
    usage_trend: str
    usage_vs_entitlement_pct: float
    ai_business_value: Dict[str, Any]  # Attributed, assisted, correlated metrics
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AutomationAnalyticsSchema(BaseModel):
    workflow_executions: int
    successful_executions: int
    failed_executions: int
    retries: int
    average_execution_duration_ms: float
    success_rate: float
    failure_rate: float
    runs_by_workflow: Dict[str, int]
    runs_by_tenant: Optional[Dict[str, int]] = None
    automation_usage_vs_entitlement_pct: float
    most_active_workflows: List[Dict[str, Any]]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SubscriptionAnalyticsSchema(BaseModel):
    active_subscriptions: int
    trial_subscriptions: int
    trial_conversion_rate: float
    upgrades_count: int
    downgrades_count: int
    cancellations_count: int
    expired_subscriptions: int
    suspended_subscriptions: int
    renewals_count: int
    failed_renewals_count: int
    churn_rate: float
    retention_rate: float
    subscription_distribution_by_plan: Dict[str, int]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrendSchema(BaseModel):
    metric_key: str
    metric_name: str
    direction: str  # INCREASING, DECREASING, STABLE, INSUFFICIENT_DATA
    period_comparison: str  # e.g., "30d vs prior 30d"
    current_value: Decimal | float | int
    previous_value: Decimal | float | int
    change_pct: float
    explanation: str


class AnomalySchema(BaseModel):
    metric: str
    observed_value: Decimal | float | int
    expected_baseline_value: Decimal | float | int
    deviation_pct: float
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    time_period: str
    explanation: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ForecastSchema(BaseModel):
    metric: str
    predicted_value: Optional[Decimal | float | int] = None
    period: str  # Next 30d, Next Month, Next Quarter
    confidence_indicator: str  # HIGH, MEDIUM, LOW, INSUFFICIENT_DATA
    methodology: str  # Rolling Linear Trend / Exponential Smoothing / Baseline
    data_sufficiency: str  # SUFFICIENT / INSUFFICIENT_DATA
    explanation: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DailyBusinessBriefSchema(BaseModel):
    summary: str
    key_numbers: Dict[str, Any]
    what_changed: List[str]
    what_needs_attention: List[str]
    opportunities: List[str]
    recommendations: List[Dict[str, Any]]
    business_health_score: float
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WeeklyStrategicReviewSchema(BaseModel):
    summary: str
    weekly_revenue: Decimal
    revenue_growth_pct: float
    client_growth_pct: float
    churn_rate: float
    sales_funnel_summary: Dict[str, Any]
    ai_usage_and_cost: Dict[str, Any]
    automation_performance: Dict[str, Any]
    client_health_summary: Dict[str, Any]
    business_health_score: float
    trends: List[TrendSchema]
    anomalies: List[AnomalySchema]
    forecast: List[ForecastSchema]
    recommendations: List[Dict[str, Any]]
    recommendation_outcomes: Dict[str, Any]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

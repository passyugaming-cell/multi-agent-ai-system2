from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional, Union
from datetime import datetime, timezone
from app.analytics.schemas import MetricValueSchema, KPISchema


def safe_decimal(val: Any) -> Decimal:
    """Convert value safely to Decimal."""
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0.00")


def calculate_change_pct(current: Decimal, previous: Decimal) -> float:
    """Calculate percentage change between previous and current value."""
    if previous == Decimal("0") or previous is None:
        if current > Decimal("0"):
            return 100.0
        elif current < Decimal("0"):
            return -100.0
        return 0.0

    diff = current - previous
    pct = (diff / abs(previous)) * Decimal("100")
    return float(pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def determine_trend_direction(
    current: Decimal,
    previous: Decimal,
    threshold_pct: float = 1.0,
) -> str:
    """Determine trend direction (UP, DOWN, STABLE)."""
    if previous is None or (previous == Decimal("0") and current == Decimal("0")):
        return "STABLE"

    pct = calculate_change_pct(current, previous)
    if pct >= threshold_pct:
        return "UP"
    elif pct <= -threshold_pct:
        return "DOWN"
    return "STABLE"


def determine_kpi_status(
    value: Decimal,
    target: Optional[Decimal] = None,
    warning_threshold: Optional[Decimal] = None,
    critical_threshold: Optional[Decimal] = None,
    lower_is_better: bool = False,
) -> str:
    """Determine status for a KPI (HEALTHY, WARNING, CRITICAL, NO_DATA)."""
    if value is None:
        return "NO_DATA"

    if lower_is_better:
        if critical_threshold is not None and value >= critical_threshold:
            return "CRITICAL"
        if warning_threshold is not None and value >= warning_threshold:
            return "WARNING"
        return "HEALTHY"
    else:
        if critical_threshold is not None and value <= critical_threshold:
            return "CRITICAL"
        if warning_threshold is not None and value <= warning_threshold:
            return "WARNING"
        return "HEALTHY"


def build_metric(
    key: str,
    name: str,
    current_val: Union[Decimal, int, float],
    previous_val: Optional[Union[Decimal, int, float]] = None,
    unit: str = "count",
    target: Optional[Union[Decimal, int, float]] = None,
    lower_is_better: bool = False,
) -> MetricValueSchema:
    curr_dec = safe_decimal(current_val)
    prev_dec = safe_decimal(previous_val) if previous_val is not None else None

    abs_change = (curr_dec - prev_dec) if prev_dec is not None else None
    change_pct = calculate_change_pct(curr_dec, prev_dec) if prev_dec is not None else None
    trend_dir = determine_trend_direction(curr_dec, prev_dec) if prev_dec is not None else "STABLE"

    status = determine_kpi_status(curr_dec, lower_is_better=lower_is_better)

    return MetricValueSchema(
        key=key,
        name=name,
        current_value=curr_dec,
        previous_value=prev_dec,
        change_absolute=abs_change,
        change_percentage=change_pct,
        trend_direction=trend_dir,
        unit=unit,
        status=status,
        target=safe_decimal(target) if target is not None else None,
        generated_at=datetime.now(timezone.utc),
    )

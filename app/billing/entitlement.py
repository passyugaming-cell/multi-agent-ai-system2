import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.billing import (
    Subscription,
    Plan,
    PlanFeature,
    PlanLimit,
    TenantAddon,
    Addon,
)
from app.billing.plans import TRIAL_FEATURES, TRIAL_LIMITS
from app.billing.state_machine import SubscriptionStatus


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class AccessState:
    AVAILABLE = "AVAILABLE"
    ENABLED = "ENABLED"
    CONFIGURED = "CONFIGURED"
    LIMITED = "LIMITED"
    BLOCKED = "BLOCKED"


@dataclass
class FeatureAccessResult:
    allowed: bool
    state: str
    feature_key: str
    reason: str | None = None
    limit: int | None = None
    current_usage: int | None = None


class EntitlementResolver:
    """Deterministic central entitlement and feature access resolver."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_tenant_subscription(self, tenant_id: uuid.UUID) -> Subscription | None:
        stmt = select(Subscription).where(Subscription.tenant_id == tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def check_subscription_temporal_validity(self, sub: Subscription) -> tuple[bool, str | None]:
        """Validates status and period start/end timestamps deterministically."""
        now = datetime.now(timezone.utc)

        if sub.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.ARCHIVED, SubscriptionStatus.SUSPENDED):
            return False, f"Subscription status is {sub.status}."

        if sub.status == SubscriptionStatus.TRIALING:
            trial_end = _ensure_utc(sub.trial_end) or _ensure_utc(sub.current_period_end)
            if trial_end and now >= trial_end:
                return False, "Trial period has expired."
            return True, None

        if sub.status == SubscriptionStatus.CANCELLED_PENDING_EXPIRY:
            period_end = _ensure_utc(sub.current_period_end)
            if period_end and now >= period_end:
                return False, "Cancelled subscription effective period has expired."
            return True, None

        # ACTIVE, PAST_DUE, GRACE_PERIOD, RESTRICTED
        period_end = _ensure_utc(sub.current_period_end)
        if period_end and now >= period_end:
            return False, f"Subscription period ended on {period_end.isoformat()}."

        return True, None

    async def get_active_tenant_addons(self, tenant_id: uuid.UUID) -> list[Addon]:
        """Returns add-ons that are active, provider-enabled, and within valid temporal periods."""
        stmt = (
            select(Addon, TenantAddon)
            .join(TenantAddon, TenantAddon.addon_id == Addon.id)
            .where(
                and_(
                    TenantAddon.tenant_id == tenant_id,
                    TenantAddon.status == "ACTIVE",
                    Addon.is_active == True,
                )
            )
        )
        res = await self.session.execute(stmt)
        now = datetime.now(timezone.utc)
        valid_addons: list[Addon] = []

        for addon, tenant_addon in res.all():
            start = _ensure_utc(tenant_addon.current_period_start)
            end = _ensure_utc(tenant_addon.current_period_end)

            if start and now < start:
                continue
            if end and now >= end:
                continue

            valid_addons.append(addon)

        return valid_addons

    async def has_feature(self, tenant_id: uuid.UUID, feature_key: str) -> bool:
        res = await self.can_use(tenant_id, feature_key)
        return res.allowed

    async def get_limit(self, tenant_id: uuid.UUID, metric: str) -> int:
        """Returns effective limit for a metric considering plan + trial + add-ons + temporal validity."""
        sub = await self.get_tenant_subscription(tenant_id)
        if not sub:
            return 0

        is_valid, _ = self.check_subscription_temporal_validity(sub)
        if not is_valid:
            return 0

        # Base limit from plan or trial
        base_limit = 0
        if sub.status == SubscriptionStatus.TRIALING:
            base_limit = TRIAL_LIMITS.get(metric, 0)
        else:
            stmt = select(PlanLimit.limit_value).where(
                and_(PlanLimit.plan_id == sub.plan_id, PlanLimit.metric == metric)
            )
            val = (await self.session.execute(stmt)).scalar_one_or_none()
            base_limit = val if val is not None else 0

        if base_limit == -1:
            return -1

        # Add-on bonus limits
        addons = await self.get_active_tenant_addons(tenant_id)
        for addon in addons:
            if addon.limit_grant and metric in addon.limit_grant:
                addon_lim = addon.limit_grant[metric]
                if addon_lim == -1:
                    return -1
                base_limit += int(addon_lim)

        return base_limit

    async def can_use(self, tenant_id: uuid.UUID, feature_key: str) -> FeatureAccessResult:
        sub = await self.get_tenant_subscription(tenant_id)
        if not sub:
            return FeatureAccessResult(
                allowed=False,
                state=AccessState.BLOCKED,
                feature_key=feature_key,
                reason="No active subscription or trial found.",
            )

        is_valid, invalid_reason = self.check_subscription_temporal_validity(sub)
        if not is_valid:
            return FeatureAccessResult(
                allowed=False,
                state=AccessState.BLOCKED,
                feature_key=feature_key,
                reason=invalid_reason,
            )

        if sub.status == SubscriptionStatus.RESTRICTED:
            allowed_restricted = {"admin_inbox", "ai_customer_service", "human_handoff"}
            if feature_key not in allowed_restricted:
                return FeatureAccessResult(
                    allowed=False,
                    state=AccessState.BLOCKED,
                    feature_key=feature_key,
                    reason="Subscription is RESTRICTED due to payment issues.",
                )

        feature_enabled = False

        if sub.status == SubscriptionStatus.TRIALING:
            feature_enabled = feature_key in TRIAL_FEATURES
        else:
            stmt = select(PlanFeature.is_enabled).where(
                and_(
                    PlanFeature.plan_id == sub.plan_id,
                    PlanFeature.feature_key == feature_key,
                )
            )
            val = (await self.session.execute(stmt)).scalar_one_or_none()
            feature_enabled = bool(val)

        if not feature_enabled:
            addons = await self.get_active_tenant_addons(tenant_id)
            for addon in addons:
                if addon.feature_grant and addon.feature_grant.get(feature_key) is True:
                    feature_enabled = True
                    break

        if not feature_enabled:
            return FeatureAccessResult(
                allowed=False,
                state=AccessState.BLOCKED,
                feature_key=feature_key,
                reason="Feature is not included in tenant plan or active add-ons.",
            )

        return FeatureAccessResult(
            allowed=True,
            state=AccessState.ENABLED,
            feature_key=feature_key,
            reason="Feature is available.",
        )

    async def evaluate_metric_access(self, tenant_id: uuid.UUID, metric: str, current_usage: int) -> FeatureAccessResult:
        """Evaluates access state for a resource metric based on current usage vs limit."""
        limit = await self.get_limit(tenant_id, metric)

        if limit == -1:
            return FeatureAccessResult(
                allowed=True,
                state=AccessState.AVAILABLE,
                feature_key=metric,
                reason="Metric usage is unlimited.",
                limit=-1,
                current_usage=current_usage,
            )

        if limit == 0:
            return FeatureAccessResult(
                allowed=False,
                state=AccessState.BLOCKED,
                feature_key=metric,
                reason=f"Metric '{metric}' limit is 0 for current entitlement.",
                limit=0,
                current_usage=current_usage,
            )

        if current_usage >= limit:
            return FeatureAccessResult(
                allowed=False,
                state=AccessState.LIMITED,
                feature_key=metric,
                reason=f"Metric '{metric}' usage ({current_usage}) has reached or exceeded limit ({limit}).",
                limit=limit,
                current_usage=current_usage,
            )

        return FeatureAccessResult(
            allowed=True,
            state=AccessState.AVAILABLE,
            feature_key=metric,
            reason="Metric usage is within allowed limit.",
            limit=limit,
            current_usage=current_usage,
        )

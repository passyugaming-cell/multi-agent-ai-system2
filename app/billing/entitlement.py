import uuid
from dataclasses import dataclass
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

    async def get_active_tenant_addons(self, tenant_id: uuid.UUID) -> list[Addon]:
        stmt = (
            select(Addon)
            .join(TenantAddon, TenantAddon.addon_id == Addon.id)
            .where(
                and_(
                    TenantAddon.tenant_id == tenant_id,
                    TenantAddon.status == "ACTIVE",
                    Addon.is_active == True,
                )
            )
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def has_feature(self, tenant_id: uuid.UUID, feature_key: str) -> bool:
        res = await self.can_use(tenant_id, feature_key)
        return res.allowed

    async def get_limit(self, tenant_id: uuid.UUID, metric: str) -> int:
        """Returns effective limit for a metric considering plan + trial + add-ons."""
        sub = await self.get_tenant_subscription(tenant_id)
        if not sub or sub.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.ARCHIVED, SubscriptionStatus.SUSPENDED):
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

        if sub.status in (SubscriptionStatus.EXPIRED, SubscriptionStatus.ARCHIVED, SubscriptionStatus.SUSPENDED):
            return FeatureAccessResult(
                allowed=False,
                state=AccessState.BLOCKED,
                feature_key=feature_key,
                reason=f"Subscription status is {sub.status}.",
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

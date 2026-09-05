import uuid
from datetime import datetime, timezone, timedelta
from typing import Sequence, Any
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.billing import Subscription, SubscriptionHistory
from app.billing.plans import PlanService, calculate_billed_amount
from app.billing.state_machine import SubscriptionStatus, validate_subscription_transition
from app.billing.exceptions import SubscriptionNotFoundError, PlanNotFoundError
from app.billing.events import publish_billing_event


class SubscriptionService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session
        self.plan_service = PlanService(db_session)

    async def get_subscription(self, tenant_id: uuid.UUID) -> Subscription:
        stmt = select(Subscription).options(joinedload(Subscription.plan)).where(Subscription.tenant_id == tenant_id)
        sub = (await self.session.execute(stmt)).scalar_one_or_none()
        if not sub:
            raise SubscriptionNotFoundError(str(tenant_id))
        return sub

    async def get_subscription_or_none(self, tenant_id: uuid.UUID) -> Subscription | None:
        stmt = select(Subscription).options(joinedload(Subscription.plan)).where(Subscription.tenant_id == tenant_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_trial_subscription(self, tenant_id: uuid.UUID, trial_days: int = 7) -> Subscription:
        existing = await self.get_subscription_or_none(tenant_id)
        if existing:
            return existing

        try:
            starter_plan = await self.plan_service.get_plan_by_code("starter")
        except PlanNotFoundError:
            await self.plan_service.seed_plans()
            starter_plan = await self.plan_service.get_plan_by_code("starter")

        now = datetime.now(timezone.utc)
        trial_end = now + timedelta(days=trial_days)

        sub = Subscription(
            tenant_id=tenant_id,
            plan_id=starter_plan.id,
            plan=starter_plan,
            status=SubscriptionStatus.TRIALING,
            billing_cycle="MONTHLY",
            currency="IDR",
            amount=starter_plan.price_monthly,
            started_at=now,
            current_period_start=now,
            current_period_end=trial_end,
            trial_start=now,
            trial_end=trial_end,
            metadata_={"is_trial": True},
        )
        self.session.add(sub)
        await self.session.flush()

        history = SubscriptionHistory(
            subscription_id=sub.id,
            tenant_id=tenant_id,
            previous_plan_id=None,
            new_plan_id=starter_plan.id,
            previous_status=None,
            new_status=SubscriptionStatus.TRIALING,
            actor="SYSTEM",
            reason="Created 7-day trial subscription",
        )
        self.session.add(history)
        await self.session.flush()

        # Emit event
        await publish_billing_event(
            event_type="subscription.created",
            tenant_id=tenant_id,
            payload={
                "subscription_id": str(sub.id),
                "plan_code": starter_plan.code,
                "status": sub.status,
                "trial_end": trial_end.isoformat(),
            },
            source="subscription_service",
        )

        return sub

    async def check_and_update_trial_expiration(self, tenant_id: uuid.UUID) -> Subscription:
        sub = await self.get_subscription(tenant_id)
        if sub.status == SubscriptionStatus.TRIALING and sub.trial_end:
            now = datetime.now(timezone.utc)
            if now >= sub.trial_end:
                await self._transition_subscription_status(
                    sub=sub,
                    target_status=SubscriptionStatus.EXPIRED,
                    actor="SYSTEM",
                    reason="Trial period expired",
                )
        return sub

    async def activate_subscription(
        self,
        tenant_id: uuid.UUID,
        plan_code: str,
        billing_cycle: str = "MONTHLY",
        actor: str = "SYSTEM",
    ) -> Subscription:
        sub = await self.get_subscription_or_none(tenant_id)
        try:
            plan = await self.plan_service.get_plan_by_code(plan_code)
        except PlanNotFoundError:
            await self.plan_service.seed_plans()
            plan = await self.plan_service.get_plan_by_code(plan_code)

        now = datetime.now(timezone.utc)
        period_days = 365 if billing_cycle.upper() == "YEARLY" else 30
        period_end = now + timedelta(days=period_days)
        billed_amount = calculate_billed_amount(plan.price_monthly, billing_cycle)

        if not sub:
            sub = Subscription(
                tenant_id=tenant_id,
                plan_id=plan.id,
                plan=plan,
                status=SubscriptionStatus.ACTIVE,
                billing_cycle=billing_cycle.upper(),
                currency="IDR",
                amount=billed_amount,
                started_at=now,
                current_period_start=now,
                current_period_end=period_end,
            )
            self.session.add(sub)
            await self.session.flush()

            history = SubscriptionHistory(
                subscription_id=sub.id,
                tenant_id=tenant_id,
                previous_plan_id=None,
                new_plan_id=plan.id,
                previous_status=None,
                new_status=SubscriptionStatus.ACTIVE,
                actor=actor,
                reason=f"Activated paid {plan_code} subscription",
            )
            self.session.add(history)
        else:
            prev_status = sub.status
            prev_plan_id = sub.plan_id
            validate_subscription_transition(prev_status, SubscriptionStatus.ACTIVE)

            sub.plan_id = plan.id
            sub.plan = plan
            sub.status = SubscriptionStatus.ACTIVE
            sub.billing_cycle = billing_cycle.upper()
            sub.amount = billed_amount
            sub.current_period_start = now
            sub.current_period_end = period_end

            history = SubscriptionHistory(
                subscription_id=sub.id,
                tenant_id=tenant_id,
                previous_plan_id=prev_plan_id,
                new_plan_id=plan.id,
                previous_status=prev_status,
                new_status=SubscriptionStatus.ACTIVE,
                actor=actor,
                reason=f"Activated paid {plan_code} subscription",
            )
            self.session.add(history)

        await self.session.flush()

        await publish_billing_event(
            event_type="subscription.activated",
            tenant_id=tenant_id,
            payload={
                "subscription_id": str(sub.id),
                "plan_code": plan.code,
                "status": sub.status,
                "amount": str(sub.amount),
                "current_period_end": period_end.isoformat(),
            },
            source="subscription_service",
        )

        return sub

    async def change_plan(
        self,
        tenant_id: uuid.UUID,
        new_plan_code: str,
        billing_cycle: str | None = None,
        actor: str = "USER",
    ) -> Subscription:
        sub = await self.get_subscription(tenant_id)
        try:
            new_plan = await self.plan_service.get_plan_by_code(new_plan_code)
        except PlanNotFoundError:
            await self.plan_service.seed_plans()
            new_plan = await self.plan_service.get_plan_by_code(new_plan_code)

        cycle = billing_cycle.upper() if billing_cycle else sub.billing_cycle
        billed_amount = calculate_billed_amount(new_plan.price_monthly, cycle)

        prev_plan_id = sub.plan_id
        prev_status = sub.status

        sub.plan_id = new_plan.id
        sub.plan = new_plan
        sub.billing_cycle = cycle
        sub.amount = billed_amount

        history = SubscriptionHistory(
            subscription_id=sub.id,
            tenant_id=tenant_id,
            previous_plan_id=prev_plan_id,
            new_plan_id=new_plan.id,
            previous_status=prev_status,
            new_status=sub.status,
            actor=actor,
            reason=f"Changed plan to {new_plan_code}",
        )
        self.session.add(history)
        await self.session.flush()

        await publish_billing_event(
            event_type="subscription.updated",
            tenant_id=tenant_id,
            payload={
                "subscription_id": str(sub.id),
                "new_plan_code": new_plan.code,
                "billing_cycle": cycle,
                "amount": str(sub.amount),
            },
            source="subscription_service",
        )

        return sub

    async def cancel_subscription(
        self,
        tenant_id: uuid.UUID,
        reason: str | None = None,
        actor: str = "USER",
    ) -> Subscription:
        sub = await self.get_subscription(tenant_id)
        now = datetime.now(timezone.utc)

        target_status = SubscriptionStatus.CANCELLED_PENDING_EXPIRY
        validate_subscription_transition(sub.status, target_status)

        sub.cancelled_at = now
        sub.cancellation_reason = reason
        await self._transition_subscription_status(
            sub=sub,
            target_status=target_status,
            actor=actor,
            reason=reason or "Subscription cancelled by user",
        )

        await publish_billing_event(
            event_type="subscription.cancelled",
            tenant_id=tenant_id,
            payload={
                "subscription_id": str(sub.id),
                "effective_expiry": sub.current_period_end.isoformat(),
                "reason": reason,
            },
            source="subscription_service",
        )

        return sub

    async def update_payment_failure_status(
        self,
        tenant_id: uuid.UUID,
        days_past_due: int,
    ) -> Subscription:
        sub = await self.get_subscription(tenant_id)
        now = datetime.now(timezone.utc)

        target_status = sub.status
        if days_past_due >= 30:
            target_status = SubscriptionStatus.EXPIRED
            sub.expired_at = now
        elif days_past_due >= 14:
            target_status = SubscriptionStatus.SUSPENDED
            if not sub.suspended_at:
                sub.suspended_at = now
        elif days_past_due >= 8:
            target_status = SubscriptionStatus.RESTRICTED
        elif days_past_due >= 4:
            target_status = SubscriptionStatus.GRACE_PERIOD
        elif days_past_due >= 0:
            target_status = SubscriptionStatus.PAST_DUE

        if target_status != sub.status:
            await self._transition_subscription_status(
                sub=sub,
                target_status=target_status,
                actor="SYSTEM",
                reason=f"Payment failure policy applied ({days_past_due} days past due)",
            )

        return sub

    async def _transition_subscription_status(
        self,
        sub: Subscription,
        target_status: str,
        actor: str,
        reason: str | None,
    ) -> None:
        prev_status = sub.status
        validate_subscription_transition(prev_status, target_status)
        sub.status = target_status

        history = SubscriptionHistory(
            subscription_id=sub.id,
            tenant_id=sub.tenant_id,
            previous_plan_id=sub.plan_id,
            new_plan_id=sub.plan_id,
            previous_status=prev_status,
            new_status=target_status,
            actor=actor,
            reason=reason,
        )
        self.session.add(history)
        await self.session.flush()

        event_name = f"subscription.{target_status.lower()}"
        await publish_billing_event(
            event_type=event_name,
            tenant_id=sub.tenant_id,
            payload={
                "subscription_id": str(sub.id),
                "previous_status": prev_status,
                "new_status": target_status,
                "reason": reason,
            },
            source="subscription_service",
        )

    async def get_subscription_history(self, tenant_id: uuid.UUID) -> Sequence[SubscriptionHistory]:
        stmt = select(SubscriptionHistory).where(SubscriptionHistory.tenant_id == tenant_id).order_by(SubscriptionHistory.created_at.desc())
        return (await self.session.execute(stmt)).scalars().all()

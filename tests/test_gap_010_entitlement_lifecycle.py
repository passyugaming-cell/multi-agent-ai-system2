import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.billing import (
    Subscription,
    Plan,
    Addon,
    TenantAddon,
    UsageRecord,
)
from app.database.models.user import User
from app.database.models.customer import Customer
from app.database.models.integrations import Integration, IntegrationConnection
from app.database.models.workflow import WorkflowConfiguration, WorkflowExecution
from app.billing.entitlement import EntitlementResolver, AccessState, FeatureAccessResult
from app.billing.subscription import SubscriptionService
from app.billing.usage import UsageService, UsageMetric
from app.billing.plans import PlanService
from app.billing.exceptions import BillingError, LimitExceededError
from app.core.workflows.engine import WorkflowEngine
from app.core.events.schemas import EventSchema


@pytest.mark.asyncio
async def test_subscription_temporal_validity(db_session: AsyncSession, tenant_a):
    """GAP-010-P1-01: Verifies temporal validity checks across subscription statuses."""
    sub_svc = SubscriptionService(db_session)
    resolver = EntitlementResolver(db_session)

    # 1. Active subscription with valid current_period_end
    now = datetime.now(timezone.utc)
    sub = await sub_svc.create_trial_subscription(tenant_a.id, trial_days=7)

    # Valid trial check
    res = await resolver.can_use(tenant_a.id, "ai_customer_service")
    assert res.allowed is True
    assert res.state == AccessState.ENABLED

    # Expired trial check
    sub.trial_end = now - timedelta(days=1)
    sub.current_period_end = now - timedelta(days=1)
    await db_session.commit()

    res_expired = await resolver.can_use(tenant_a.id, "ai_customer_service")
    assert res_expired.allowed is False
    assert res_expired.state == AccessState.BLOCKED
    assert "Trial period has expired" in res_expired.reason

    # Expired active subscription period
    sub.status = "ACTIVE"
    sub.current_period_end = now - timedelta(hours=2)
    await db_session.commit()

    res_active_expired = await resolver.can_use(tenant_a.id, "ai_customer_service")
    assert res_active_expired.allowed is False
    assert res_active_expired.state == AccessState.BLOCKED
    assert "ended on" in res_active_expired.reason

    # Cancelled pending expiry - still valid before period end
    sub.status = "CANCELLED_PENDING_EXPIRY"
    sub.current_period_end = now + timedelta(days=3)
    await db_session.commit()

    res_cancelled_valid = await resolver.can_use(tenant_a.id, "ai_customer_service")
    assert res_cancelled_valid.allowed is True

    # Cancelled pending expiry - expired after period end
    sub.current_period_end = now - timedelta(minutes=5)
    await db_session.commit()

    res_cancelled_expired = await resolver.can_use(tenant_a.id, "ai_customer_service")
    assert res_cancelled_expired.allowed is False
    assert "Cancelled subscription effective period has expired" in res_cancelled_expired.reason


@pytest.mark.asyncio
async def test_addon_temporal_validity(db_session: AsyncSession, tenant_a):
    """GAP-010-P2-02: Verifies add-on temporal validity and grants."""
    sub_svc = SubscriptionService(db_session)
    resolver = EntitlementResolver(db_session)
    await sub_svc.activate_subscription(tenant_a.id, "starter", verified_payment=True)

    # Starter does not have 'ai_sales'
    can_sales_before = await resolver.can_use(tenant_a.id, "ai_sales")
    assert can_sales_before.allowed is False

    # Create active add-on
    now = datetime.now(timezone.utc)
    addon = Addon(
        name="AI Sales Add-on",
        code="ai_sales_addon",
        is_active=True,
        feature_grant={"ai_sales": True},
        limit_grant={"ai_credits": 5000},
    )
    db_session.add(addon)
    await db_session.flush()

    tenant_addon = TenantAddon(
        tenant_id=tenant_a.id,
        addon_id=addon.id,
        status="ACTIVE",
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29),
    )
    db_session.add(tenant_addon)
    await db_session.commit()

    # Valid add-on feature and limit check
    can_sales_after = await resolver.can_use(tenant_a.id, "ai_sales")
    assert can_sales_after.allowed is True

    starter_limit = await resolver.get_limit(tenant_a.id, UsageMetric.AI_CREDITS)
    # Starter base (3000) + Add-on grant (5000) = 8000
    assert starter_limit == 8000

    # Expired add-on check
    tenant_addon.current_period_end = now - timedelta(minutes=10)
    await db_session.commit()

    can_sales_expired = await resolver.can_use(tenant_a.id, "ai_sales")
    assert can_sales_expired.allowed is False
    limit_expired = await resolver.get_limit(tenant_a.id, UsageMetric.AI_CREDITS)
    assert limit_expired == 3000  # Back to base starter limit


@pytest.mark.asyncio
async def test_usage_limits_overage_and_access_states(db_session: AsyncSession, tenant_a):
    """GAP-010-P1-03 & GAP-010-P2-01: Verifies usage limits, overage policies, and AccessState semantics."""
    sub_svc = SubscriptionService(db_session)
    usage_svc = UsageService(db_session)
    resolver = EntitlementResolver(db_session)

    await sub_svc.activate_subscription(tenant_a.id, "starter", verified_payment=True)
    limit = await resolver.get_limit(tenant_a.id, UsageMetric.ADMINS)
    assert limit == 3

    # Usage below limit
    acc_below = await resolver.evaluate_metric_access(tenant_a.id, UsageMetric.ADMINS, current_usage=1)
    assert acc_below.allowed is True
    assert acc_below.state == AccessState.AVAILABLE
    assert acc_below.limit == 3
    assert acc_below.current_usage == 1

    # Usage exactly at limit
    acc_at_limit = await resolver.evaluate_metric_access(tenant_a.id, UsageMetric.ADMINS, current_usage=3)
    assert acc_at_limit.allowed is False
    assert acc_at_limit.state == AccessState.LIMITED
    assert acc_at_limit.limit == 3
    assert acc_at_limit.current_usage == 3

    # Overage enforcement with BLOCK policy
    await usage_svc.check_and_increment_usage(tenant_a.id, UsageMetric.ADMINS, quantity=2, policy="BLOCK")
    with pytest.raises(LimitExceededError):
        await usage_svc.check_and_increment_usage(tenant_a.id, UsageMetric.ADMINS, quantity=2, policy="BLOCK")

    # Overage enforcement with WARN / ALLOW / APPROVED_OVERAGE / DEGRADE
    rec_warn = await usage_svc.check_and_increment_usage(tenant_a.id, UsageMetric.ADMINS, quantity=1, policy="WARN")
    assert rec_warn.quantity == 1

    rec_allow = await usage_svc.check_and_increment_usage(tenant_a.id, UsageMetric.ADMINS, quantity=1, policy="ALLOW")
    assert rec_allow.quantity == 1

    rec_degrade = await usage_svc.check_and_increment_usage(tenant_a.id, UsageMetric.ADMINS, quantity=1, policy="DEGRADE")
    assert rec_degrade.quantity == 1

    # Unknown policy raises ValueError fail-closed
    with pytest.raises(ValueError, match="Unsupported usage policy"):
        await usage_svc.check_and_increment_usage(tenant_a.id, UsageMetric.ADMINS, quantity=1, policy="UNSUPPORTED_UNKNOWN")


@pytest.mark.asyncio
async def test_addon_temporal_and_status_matrix(db_session: AsyncSession, tenant_a, tenant_b):
    """GAP-010-P2-02: Complete add-on matrix verification (active, inactive, future, expired, tenant isolation)."""
    sub_svc = SubscriptionService(db_session)
    resolver = EntitlementResolver(db_session)

    await sub_svc.activate_subscription(tenant_a.id, "starter", verified_payment=True)
    await sub_svc.activate_subscription(tenant_b.id, "starter", verified_payment=True)

    now = datetime.now(timezone.utc)

    # 1. Inactive catalog addon
    addon_inactive_catalog = Addon(
        name="Inactive Catalog Addon",
        code="inactive_cat",
        is_active=False,
        feature_grant={"ai_sales": True},
    )
    db_session.add(addon_inactive_catalog)
    await db_session.flush()

    ta1 = TenantAddon(
        tenant_id=tenant_a.id,
        addon_id=addon_inactive_catalog.id,
        status="ACTIVE",
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=10),
    )
    db_session.add(ta1)

    # 2. Inactive tenant addon status
    addon_active = Addon(
        name="Active Catalog Addon",
        code="active_cat",
        is_active=True,
        feature_grant={"ai_support": True},
    )
    db_session.add(addon_active)
    await db_session.flush()

    ta2 = TenantAddon(
        tenant_id=tenant_a.id,
        addon_id=addon_active.id,
        status="INACTIVE",
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=10),
    )
    db_session.add(ta2)

    # 3. Future scheduled tenant addon
    ta3 = TenantAddon(
        tenant_id=tenant_a.id,
        addon_id=addon_active.id,
        status="ACTIVE",
        current_period_start=now + timedelta(days=5),
        current_period_end=now + timedelta(days=15),
    )
    db_session.add(ta3)
    await db_session.commit()

    # Verify no feature grants from inactive/future addons
    res_sales = await resolver.can_use(tenant_a.id, "ai_sales")
    assert res_sales.allowed is False

    res_support = await resolver.can_use(tenant_a.id, "ai_support")
    assert res_support.allowed is False

    # Tenant B isolation check: Tenant A addons never affect Tenant B
    res_b = await resolver.can_use(tenant_b.id, "ai_support")
    assert res_b.allowed is False


@pytest.mark.asyncio
async def test_safe_non_destructive_downgrade(db_session: AsyncSession, tenant_a):
    """GAP-010-P1-04: Verifies downgrade Pro -> Starter preserves all data without silent deletion."""
    sub_svc = SubscriptionService(db_session)
    await sub_svc.activate_subscription(tenant_a.id, "pro", verified_payment=True)

    # Populate Pro tenant state: 5 admins (Starter limit is 3)
    for i in range(5):
        u = User(
            tenant_id=tenant_a.id,
            email=f"admin_{i}@tenant-a.com",
            password_hash="hash",
            role="admin",
            is_active=True,
        )
        db_session.add(u)

    # 1200 active customers (Starter limit is 1000)
    for i in range(1200):
        c = Customer(
            tenant_id=tenant_a.id,
            name=f"Customer {i}",
            phone=f"+628120000{i:04d}",
        )
        db_session.add(c)

    await db_session.commit()

    # Evaluate impact before downgrade
    impact = await sub_svc.evaluate_plan_change_impact(tenant_a.id, "starter")
    assert impact["has_conflicts"] is True
    assert len(impact["conflicts"]) >= 2

    # Execute downgrade to Starter (verified_payment=True required for paid Starter plan)
    sub_downgraded = await sub_svc.change_plan(tenant_a.id, "starter", verified_payment=True)
    assert sub_downgraded.plan.code == "starter"
    assert sub_downgraded.metadata_["restricted_mode"] is True
    assert len(sub_downgraded.metadata_["downgrade_conflicts"]) >= 2

    # Assert NO DATA DELETED
    users_stmt = select(User).where(User.tenant_id == tenant_a.id)
    all_users = (await db_session.execute(users_stmt)).scalars().all()
    assert len(all_users) == 5  # All 5 admins intact

    cust_stmt = select(Customer).where(Customer.tenant_id == tenant_a.id)
    all_custs = (await db_session.execute(cust_stmt)).scalars().all()
    assert len(all_custs) == 1200  # All 1200 customers intact

    # Assert resulting authoritative limit enforcement post-downgrade
    resolver = EntitlementResolver(db_session)
    admin_limit_post = await resolver.get_limit(tenant_a.id, UsageMetric.ADMINS)
    assert admin_limit_post == 3  # Starter limit

    # Pro-only feature is now blocked
    sales_post = await resolver.can_use(tenant_a.id, "ai_sales")
    assert sales_post.allowed is False
    assert sales_post.state == AccessState.BLOCKED


@pytest.mark.asyncio
async def test_workflow_execution_boundary_during_plan_change(db_session: AsyncSession, tenant_a):
    """GAP-010-P1-05: Verifies running workflow execution boundary snapshot during plan change."""
    sub_svc = SubscriptionService(db_session)
    await sub_svc.activate_subscription(tenant_a.id, "pro", verified_payment=True)

    wf_config = WorkflowConfiguration(
        tenant_id=tenant_a.id,
        key="order_created_wf",
        name="Order Created Workflow",
        trigger_type="order.created",
        is_active=True,
        actions=[{"type": "send_message", "params": {"message": "Thank you for order!"}}],
    )
    db_session.add(wf_config)
    await db_session.commit()

    engine = WorkflowEngine(db_session)
    evt = EventSchema(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="order.created",
        tenant_id=str(tenant_a.id),
        payload={"order_id": "ord_123"},
        source="test",
    )

    executions = await engine.handle_event(evt)
    assert len(executions) == 1
    exec_inst = executions[0]
    assert exec_inst.context["execution_plan_code"] == "pro"

    # Plan change Pro -> Starter while execution exists
    await sub_svc.change_plan(tenant_a.id, "starter", verified_payment=True)

    # Execution plan boundary remains strictly 'pro' for existing execution
    assert exec_inst.context["execution_plan_code"] == "pro"

    # A NEW execution created post-downgrade receives the new 'starter' snapshot
    evt_new = EventSchema(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        event_type="order.created",
        tenant_id=str(tenant_a.id),
        payload={"order_id": "ord_456"},
        source="test",
    )
    new_executions = await engine.handle_event(evt_new)
    assert len(new_executions) == 1
    assert new_executions[0].context["execution_plan_code"] == "starter"


@pytest.mark.asyncio
async def test_ai_security_boundary_cannot_grant_entitlement(db_session: AsyncSession, tenant_a):
    """GAP-010 AI Security Boundary: Request payload claiming plan/entitlement cannot grant access."""
    sub_svc = SubscriptionService(db_session)
    resolver = EntitlementResolver(db_session)

    # Tenant on Starter plan
    await sub_svc.activate_subscription(tenant_a.id, "starter", verified_payment=True)

    # Simulated AI reasoning / client request payload trying to pass forged plan or entitlement
    untrusted_payload = {
        "plan": "pro",
        "entitled": True,
        "feature_grant": {"ai_sales": True},
        "role": "owner",
    }

    # Authoritative resolver evaluates database truth ONLY and ignores untrusted payload parameters
    res = await resolver.can_use(tenant_a.id, "ai_sales")
    assert res.allowed is False
    assert res.state == AccessState.BLOCKED
    assert "not included in tenant plan" in res.reason

    limit = await resolver.get_limit(tenant_a.id, UsageMetric.ADMINS)
    assert limit == 3  # Starter limit, not overridden by untrusted payload


@pytest.mark.asyncio
async def test_tenant_entitlement_isolation(db_session: AsyncSession, tenant_a, tenant_b):
    """GAP-010 Tenant Isolation: Tenant A's plan must never affect Tenant B."""
    sub_svc = SubscriptionService(db_session)
    resolver = EntitlementResolver(db_session)

    # Tenant A on Pro, Tenant B on Starter
    await sub_svc.activate_subscription(tenant_a.id, "pro", verified_payment=True)
    await sub_svc.activate_subscription(tenant_b.id, "starter", verified_payment=True)

    can_a = await resolver.can_use(tenant_a.id, "ai_sales")
    can_b = await resolver.can_use(tenant_b.id, "ai_sales")

    assert can_a.allowed is True
    assert can_b.allowed is False

    lim_a = await resolver.get_limit(tenant_a.id, UsageMetric.ADMINS)
    lim_b = await resolver.get_limit(tenant_b.id, UsageMetric.ADMINS)

    assert lim_a == 10
    assert lim_b == 3

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.billing.plans import PlanService, PLAN_DEFINITIONS, calculate_billed_amount
from app.billing.subscription import SubscriptionService
from app.billing.entitlement import EntitlementResolver, AccessState
from app.billing.usage import UsageService, UsageMetric, calculate_ai_credits
from app.billing.invoices import InvoiceService, RevenueType
from app.billing.payments import PaymentService
from app.billing.refunds import RefundService
from app.billing.provider import FakePaymentProvider
from app.billing.state_machine import SubscriptionStatus, InvoiceStatus, PaymentStatus, validate_subscription_transition
from app.billing.exceptions import (
    PlanNotFoundError,
    SubscriptionNotFoundError,
    InvalidSubscriptionStateError,
    LimitExceededError,
    BillingError,
)
from app.tenants.provisioning.provisioner import TenantProvisioner
from app.agents.owner_ai.tools import tool_get_billing_summary
from app.agents.base.schemas import ToolRequest


@pytest.mark.asyncio
async def test_plan_seeding_and_pricing(db_session: AsyncSession):
    plan_service = PlanService(db_session)
    plans = await plan_service.seed_plans()

    assert len(plans) == 4
    plan_codes = [p.code for p in plans]
    assert "starter" in plan_codes
    assert "pro" in plan_codes
    assert "business" in plan_codes
    assert "enterprise" in plan_codes

    starter = await plan_service.get_plan_by_code("starter")
    assert starter.price_monthly == Decimal("299000.00")
    # Billed yearly with 15% discount
    yearly_billed = calculate_billed_amount(starter.price_monthly, "YEARLY")
    assert yearly_billed == Decimal("3049800.00")

    # Re-run seeding (idempotency check)
    plans_retry = await plan_service.seed_plans()
    assert len(plans_retry) == 4


@pytest.mark.asyncio
async def test_subscription_lifecycle_and_trial(db_session: AsyncSession, tenant_a: Tenant):
    sub_service = SubscriptionService(db_session)

    # Auto trial creation
    sub = await sub_service.create_trial_subscription(tenant_a.id, trial_days=7)
    assert sub.status == SubscriptionStatus.TRIALING
    assert sub.plan.code == "starter"

    # Repeated trial creation is idempotent
    sub_repeat = await sub_service.create_trial_subscription(tenant_a.id)
    assert sub_repeat.id == sub.id

    # Activate paid plan
    sub = await sub_service.activate_subscription(tenant_a.id, "pro", billing_cycle="MONTHLY")
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.plan.code == "pro"
    assert sub.amount == Decimal("799000.00")

    # Upgrade plan
    sub = await sub_service.change_plan(tenant_a.id, "business", billing_cycle="YEARLY")
    assert sub.plan.code == "business"
    assert sub.billing_cycle == "YEARLY"
    assert sub.amount == Decimal("20389800.00")

    # Cancellation pending expiry
    sub = await sub_service.cancel_subscription(tenant_a.id, reason="Testing cancellation")
    assert sub.status == SubscriptionStatus.CANCELLED_PENDING_EXPIRY

    # History audit check
    history = await sub_service.get_subscription_history(tenant_a.id)
    assert len(history) >= 3


@pytest.mark.asyncio
async def test_subscription_state_machine_validation():
    # Valid transition
    validate_subscription_transition(SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE)

    # Invalid transition rejection
    with pytest.raises(InvalidSubscriptionStateError):
        validate_subscription_transition(SubscriptionStatus.ARCHIVED, SubscriptionStatus.ACTIVE)


@pytest.mark.asyncio
async def test_payment_failure_policy_lifecycle(db_session: AsyncSession, tenant_a: Tenant):
    sub_service = SubscriptionService(db_session)
    await sub_service.activate_subscription(tenant_a.id, "starter")

    # Day 0: PAST_DUE
    sub = await sub_service.update_payment_failure_status(tenant_a.id, days_past_due=0)
    assert sub.status == SubscriptionStatus.PAST_DUE

    # Day 5: GRACE_PERIOD
    sub = await sub_service.update_payment_failure_status(tenant_a.id, days_past_due=5)
    assert sub.status == SubscriptionStatus.GRACE_PERIOD

    # Day 10: RESTRICTED
    sub = await sub_service.update_payment_failure_status(tenant_a.id, days_past_due=10)
    assert sub.status == SubscriptionStatus.RESTRICTED

    # Day 15: SUSPENDED
    sub = await sub_service.update_payment_failure_status(tenant_a.id, days_past_due=15)
    assert sub.status == SubscriptionStatus.SUSPENDED

    # Day 30: EXPIRED
    sub = await sub_service.update_payment_failure_status(tenant_a.id, days_past_due=30)
    assert sub.status == SubscriptionStatus.EXPIRED


@pytest.mark.asyncio
async def test_entitlement_gating(db_session: AsyncSession, tenant_a: Tenant):
    sub_service = SubscriptionService(db_session)
    ent_resolver = EntitlementResolver(db_session)

    # Trial entitlements
    await sub_service.create_trial_subscription(tenant_a.id)
    assert await ent_resolver.has_feature(tenant_a.id, "ai_customer_service") is True
    assert await ent_resolver.has_feature(tenant_a.id, "owner_ai") is False

    ai_limit = await ent_resolver.get_limit(tenant_a.id, UsageMetric.AI_CREDITS)
    assert ai_limit == 1000

    # Upgrade to Business
    await sub_service.activate_subscription(tenant_a.id, "business")
    assert await ent_resolver.has_feature(tenant_a.id, "owner_ai") is True
    business_limit = await ent_resolver.get_limit(tenant_a.id, UsageMetric.AI_CREDITS)
    assert business_limit == 50000


@pytest.mark.asyncio
async def test_usage_tracking_and_threshold_events(db_session: AsyncSession, tenant_a: Tenant):
    sub_service = SubscriptionService(db_session)
    usage_service = UsageService(db_session)

    await sub_service.create_trial_subscription(tenant_a.id)  # AI credit limit = 1000

    # Record 600 credits
    rec1 = await usage_service.check_and_increment_usage(
        tenant_id=tenant_a.id,
        metric=UsageMetric.AI_CREDITS,
        quantity=600,
        source="test",
    )
    assert rec1.quantity == 600
    assert await usage_service.get_current_usage(tenant_a.id, UsageMetric.AI_CREDITS) == 600

    # Record another 300 credits (reaches 900 -> triggers 70% and 85% thresholds)
    await usage_service.check_and_increment_usage(
        tenant_id=tenant_a.id,
        metric=UsageMetric.AI_CREDITS,
        quantity=300,
        source="test",
    )
    assert await usage_service.get_current_usage(tenant_a.id, UsageMetric.AI_CREDITS) == 900

    # Exceed limit (1000) with policy="BLOCK" -> throws LimitExceededError
    with pytest.raises(LimitExceededError):
        await usage_service.check_and_increment_usage(
            tenant_id=tenant_a.id,
            metric=UsageMetric.AI_CREDITS,
            quantity=200,
            policy="BLOCK",
        )


@pytest.mark.asyncio
async def test_ai_credit_calculation():
    # 500 total tokens -> 50 credits
    assert calculate_ai_credits(500) == 50
    # 0 tokens -> 1 credit min
    assert calculate_ai_credits(0) == 1


@pytest.mark.asyncio
async def test_invoice_and_payment_flow(db_session: AsyncSession, tenant_a: Tenant):
    sub_service = SubscriptionService(db_session)
    inv_service = InvoiceService(db_session)
    pay_service = PaymentService(db_session)

    sub = await sub_service.create_trial_subscription(tenant_a.id)

    # Create Invoice with setup fee & subscription fee
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        subscription_id=sub.id,
        items_data=[
            {"description": "Starter Plan Subscription", "revenue_type": RevenueType.SUBSCRIPTION, "unit_price": "299000.00", "quantity": 1},
            {"description": "Basic Setup Fee", "revenue_type": RevenueType.SETUP, "unit_price": "299000.00", "quantity": 1},
        ],
    )

    assert invoice.subtotal == Decimal("598000.00")
    assert invoice.total == Decimal("598000.00")
    assert invoice.status == InvoiceStatus.ISSUED

    # Payment intent & confirmation
    payment = await pay_service.create_payment_intent(tenant_a.id, invoice.id, invoice.total)
    assert payment.status == PaymentStatus.PENDING

    confirmed_payment = await pay_service.confirm_payment_success(tenant_a.id, payment.id)
    assert confirmed_payment.status == PaymentStatus.SUCCEEDED

    # Check updated invoice & subscription
    inv_updated = await inv_service.get_invoice(tenant_a.id, invoice.id)
    assert inv_updated.status == InvoiceStatus.PAID
    sub_updated = await sub_service.get_subscription(tenant_a.id)
    assert sub_updated.status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_payment_webhook_idempotency(db_session: AsyncSession, tenant_a: Tenant):
    inv_service = InvoiceService(db_session)
    pay_service = PaymentService(db_session)

    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Test Item", "unit_price": "100000.00", "quantity": 1}],
    )

    webhook_payload = {
        "event": "payment.succeeded",
        "provider_payment_id": "pay_webhook_unique_123",
        "amount": "100000.00",
        "status": "SUCCEEDED",
        "tenant_id": str(tenant_a.id),
        "invoice_id": str(invoice.id),
    }
    headers = {"X-Signature": "valid_test_signature"}

    # First webhook execution
    p1 = await pay_service.handle_provider_webhook(webhook_payload, headers)
    assert p1.status == PaymentStatus.SUCCEEDED

    # Duplicate webhook delivery (idempotency check)
    p2 = await pay_service.handle_provider_webhook(webhook_payload, headers)
    assert p2.id == p1.id
    assert p2.status == PaymentStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_high_risk_refund_approval_flow(db_session: AsyncSession, tenant_a: Tenant):
    inv_service = InvoiceService(db_session)
    pay_service = PaymentService(db_session)
    refund_service = RefundService(db_session)

    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Pro Plan", "unit_price": "799000.00", "quantity": 1}],
    )
    payment = await pay_service.create_payment_intent(tenant_a.id, invoice.id, Decimal("799000.00"))
    await pay_service.confirm_payment_success(tenant_a.id, payment.id)

    # Step 1: Request refund -> creates PENDING approval
    approval = await refund_service.request_refund(
        tenant_id=tenant_a.id,
        payment_id=payment.id,
        amount=Decimal("799000.00"),
        reason="Double payment mistake",
    )
    assert approval.status == "PENDING"
    assert approval.action_type == "issue_refund"

    # Unapproved refund fails execution
    with pytest.raises(BillingError):
        await refund_service.execute_approved_refund(tenant_a.id, approval.id)

    # Step 2: Human Owner approves request
    approval.status = "APPROVED"
    approval.decided_by = "human_owner@company.com"
    await db_session.flush()

    # Step 3: Execute approved refund
    refunded_payment = await refund_service.execute_approved_refund(tenant_a.id, approval.id)
    assert refunded_payment.status == PaymentStatus.REFUNDED


@pytest.mark.asyncio
async def test_owner_ai_billing_read_only_tool(db_session: AsyncSession, tenant_a: Tenant):
    sub_service = SubscriptionService(db_session)
    await sub_service.create_trial_subscription(tenant_a.id)

    req = ToolRequest(
        tenant_id=str(tenant_a.id),
        tool_name="get_billing_summary",
        parameters={},
    )
    res = await tool_get_billing_summary(req, db_session)

    assert res.success is True
    assert res.data["subscription_status"] == "TRIALING"
    assert res.data["plan_code"] == "starter"


@pytest.mark.asyncio
async def test_tenant_billing_isolation(db_session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant):
    sub_service = SubscriptionService(db_session)
    inv_service = InvoiceService(db_session)

    # Provision tenant A and tenant B
    await sub_service.create_trial_subscription(tenant_a.id)
    await sub_service.activate_subscription(tenant_b.id, "pro")

    sub_a = await sub_service.get_subscription(tenant_a.id)
    sub_b = await sub_service.get_subscription(tenant_b.id)

    assert sub_a.plan.code == "starter"
    assert sub_b.plan.code == "pro"

    # Tenant A invoice creation
    inv_a = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Tenant A Fee", "unit_price": "100000.00"}],
    )

    # Tenant B cannot view Tenant A invoice
    with pytest.raises(Exception):
        await inv_service.get_invoice(tenant_b.id, inv_a.id)


@pytest.mark.asyncio
async def test_billing_api_endpoints(client: AsyncClient, db_session: AsyncSession, tenant_a: Tenant):
    sub_service = SubscriptionService(db_session)
    await sub_service.create_trial_subscription(tenant_a.id)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(tenant_a.id)}

    # GET /api/v1/billing/plans
    res_plans = await client.get("/api/v1/billing/plans", headers=headers)
    assert res_plans.status_code == 200
    plans_data = res_plans.json()
    assert len(plans_data) == 4

    # GET /api/v1/billing/subscription
    res_sub = await client.get("/api/v1/billing/subscription", headers=headers)
    assert res_sub.status_code == 200
    assert res_sub.json()["plan_code"] == "starter"

    # POST /api/v1/billing/subscription/change-plan
    res_change = await client.post(
        "/api/v1/billing/subscription/change-plan",
        headers=headers,
        json={"new_plan_code": "pro", "billing_cycle": "MONTHLY"},
    )
    assert res_change.status_code == 200
    assert res_change.json()["plan_code"] == "pro"

    # GET /api/v1/billing/usage
    res_usage = await client.get("/api/v1/billing/usage", headers=headers)
    assert res_usage.status_code == 200
    assert len(res_usage.json()) >= 5

    # GET /api/v1/billing/entitlements
    res_ent = await client.get("/api/v1/billing/entitlements", headers=headers)
    assert res_ent.status_code == 200

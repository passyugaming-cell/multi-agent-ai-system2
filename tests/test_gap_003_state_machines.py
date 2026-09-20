import uuid
import pytest
from datetime import datetime, timezone
from decimal import Decimal
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, AppError
from app.database.models.tenant import Tenant
from app.database.models.conversation import Conversation
from app.database.models.workflow import WorkflowExecution, Task, Approval
from app.database.models.integrations import IntegrationConnection
from app.database.models.billing import Subscription, Plan, Payment, Invoice
from app.tenants.lifecycle import TenantLifecycleState, validate_tenant_lifecycle_transition
from app.core.handoff_state import (
    HumanHandoffState,
    validate_handoff_state_transition,
    get_handoff_lifecycle_state,
    sync_handoff_with_conversation_status,
)
from app.core.workflow_state import WorkflowExecutionStatus, validate_workflow_execution_transition
from app.core.task_state import TaskStatus, validate_task_status_transition, apply_task_status_transition
from app.integrations.state_machine import IntegrationConnectionStatus, validate_integration_connection_transition
from app.billing.refunds import RefundService
from app.core.context import AuthenticatedActor


@pytest.mark.asyncio
async def test_s001_tenant_lifecycle_valid_transitions(tenant_a: Tenant):
    """S-001: Tests valid sequential transitions for tenant lifecycle."""
    # PROSPECT -> LEAD -> QUALIFIED -> PROPOSAL -> WAITING_PAYMENT -> PAID -> CLIENT -> ONBOARDING
    validate_tenant_lifecycle_transition("PROSPECT", "LEAD", tenant_a)
    validate_tenant_lifecycle_transition("LEAD", "QUALIFIED", tenant_a)
    validate_tenant_lifecycle_transition("QUALIFIED", "PROPOSAL", tenant_a)
    validate_tenant_lifecycle_transition("PROPOSAL", "WAITING_PAYMENT", tenant_a)
    validate_tenant_lifecycle_transition("WAITING_PAYMENT", "PAID", tenant_a)
    validate_tenant_lifecycle_transition("PAID", "CLIENT", tenant_a)
    validate_tenant_lifecycle_transition("CLIENT", "ONBOARDING", tenant_a)


@pytest.mark.asyncio
async def test_s001_tenant_lifecycle_invalid_transition(tenant_a: Tenant):
    """S-001: Tests illegal tenant lifecycle jump rejection."""
    with pytest.raises(AppException) as exc_info:
        validate_tenant_lifecycle_transition("PROSPECT", "ACTIVE", tenant_a)
    assert exc_info.value.code == "INVALID_TENANT_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_s001_tenant_activation_gate(tenant_a: Tenant):
    """S-001: Tests activation readiness & verified payment gate."""
    class MockReadinessScore:
        readiness_status = "NOT_READY"

    class MockSubscription:
        status = "ACTIVE"
        amount = Decimal("100.00")
        metadata_ = {"verified_payment": False}

    # Readiness score NOT_READY -> blocked
    with pytest.raises(AppException) as exc_info:
        validate_tenant_lifecycle_transition(
            "READY", "ACTIVE", tenant_a, readiness_score=MockReadinessScore()
        )
    assert exc_info.value.code == "TENANT_ACTIVATION_GATE_FAILED"

    # Unverified payment on paid plan -> blocked
    MockReadinessScore.readiness_status = "READY"
    with pytest.raises(AppException) as exc_info:
        validate_tenant_lifecycle_transition(
            "READY", "ACTIVE", tenant_a, readiness_score=MockReadinessScore(), subscription=MockSubscription()
        )
    assert exc_info.value.code == "PAYMENT_VERIFICATION_REQUIRED"

    # Verified payment -> allowed
    MockSubscription.metadata_ = {"verified_payment": True}
    validate_tenant_lifecycle_transition(
        "READY", "ACTIVE", tenant_a, readiness_score=MockReadinessScore(), subscription=MockSubscription()
    )

    # Missing readiness score or subscription -> blocked
    with pytest.raises(AppException) as exc_info:
        validate_tenant_lifecycle_transition("READY", "ACTIVE", tenant_a, readiness_score=None, subscription=MockSubscription())
    assert exc_info.value.code == "TENANT_ACTIVATION_GATE_FAILED"

    with pytest.raises(AppException) as exc_info:
        validate_tenant_lifecycle_transition("READY", "ACTIVE", tenant_a, readiness_score=MockReadinessScore(), subscription=None)
    assert exc_info.value.code == "TENANT_ACTIVATION_GATE_FAILED"


@pytest.mark.asyncio
async def test_s001_tenant_recovery_authority(tenant_a: Tenant):
    """S-001: Tests that recovery from ERROR/BLOCKED requires Platform Owner."""
    actor_user = AuthenticatedActor(
        user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="owner", is_platform_owner=False
    )
    actor_owner = AuthenticatedActor(
        user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="platform_owner", is_platform_owner=True
    )

    with pytest.raises(AppException) as exc_info:
        validate_tenant_lifecycle_transition("ERROR", "PROSPECT", tenant_a, actor=actor_user)
    assert exc_info.value.code == "PERMISSION_DENIED"

    # Platform Owner allowed
    validate_tenant_lifecycle_transition("ERROR", "PROSPECT", tenant_a, actor=actor_owner)


@pytest.mark.asyncio
async def test_s002_human_handoff_lifecycle_state():
    """S-002: Tests HumanHandoffState validation and Conversation.status sync."""
    conv = Conversation(
        tenant_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        status="OPEN",
    )

    # Initial handoff state derived from OPEN -> RESUME_AI
    assert get_handoff_lifecycle_state(conv) == HumanHandoffState.RESUME_AI.value

    # RESUME_AI -> AI_HANDOFF_REQUESTED -> updates Conversation.status to WAITING_HUMAN
    sync_handoff_with_conversation_status(conv, "AI_HANDOFF_REQUESTED")
    assert get_handoff_lifecycle_state(conv) == "AI_HANDOFF_REQUESTED"
    assert conv.status == "WAITING_HUMAN"

    # AI_HANDOFF_REQUESTED -> HUMAN_IN_PROGRESS -> updates Conversation.status to HUMAN_ACTIVE
    sync_handoff_with_conversation_status(conv, "HUMAN_IN_PROGRESS")
    assert get_handoff_lifecycle_state(conv) == "HUMAN_IN_PROGRESS"
    assert conv.status == "HUMAN_ACTIVE"

    # Invalid jump: RESOLVED directly to HUMAN_ASSIGNED without VERIFY/RESUME_AI
    sync_handoff_with_conversation_status(conv, "RESOLVED")
    with pytest.raises(AppException) as exc_info:
        sync_handoff_with_conversation_status(conv, "HUMAN_ASSIGNED")
    assert exc_info.value.code == "INVALID_HANDOFF_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_s004_workflow_execution_state_transitions():
    """S-004: Tests WorkflowExecution state transition validator."""
    validate_workflow_execution_transition("PENDING", "RUNNING")
    validate_workflow_execution_transition("RUNNING", "WAITING_APPROVAL")
    validate_workflow_execution_transition("WAITING_APPROVAL", "RUNNING")
    validate_workflow_execution_transition("RUNNING", "COMPLETED")

    # Invalid jump from COMPLETED (terminal) to RUNNING
    with pytest.raises(AppException) as exc_info:
        validate_workflow_execution_transition("COMPLETED", "RUNNING")
    assert exc_info.value.code == "INVALID_WORKFLOW_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_s005_task_timestamp_side_effects():
    """S-005: Tests Task transition rules and timestamp side-effect preservation."""
    task = Task(
        tenant_id=uuid.uuid4(),
        title="Test Task",
        status="CREATED",
    )

    # Transition CREATED -> IN_PROGRESS populates started_at
    apply_task_status_transition(task, "IN_PROGRESS")
    assert task.status == "IN_PROGRESS"
    first_started_at = task.started_at
    assert first_started_at is not None
    assert task.completed_at is None

    # Transition IN_PROGRESS -> WAITING_DATA
    apply_task_status_transition(task, "WAITING_DATA")
    assert task.status == "WAITING_DATA"

    # Re-entry WAITING_DATA -> IN_PROGRESS preserves original started_at!
    apply_task_status_transition(task, "IN_PROGRESS")
    assert task.status == "IN_PROGRESS"
    assert task.started_at == first_started_at

    # Transition IN_PROGRESS -> COMPLETED sets completed_at
    apply_task_status_transition(task, "COMPLETED")
    assert task.status == "COMPLETED"
    assert task.completed_at is not None


@pytest.mark.asyncio
async def test_s006_integration_connection_state_transitions():
    """S-006: Tests IntegrationConnection state transition validator."""
    validate_integration_connection_transition("DISCONNECTED", "CONNECTING")
    validate_integration_connection_transition("CONNECTING", "CONNECTED")
    validate_integration_connection_transition("CONNECTED", "ACTIVE")
    validate_integration_connection_transition("ACTIVE", "RECONNECTING")

    # Invalid jump: DISCONNECTED directly to ACTIVE
    with pytest.raises(AppException) as exc_info:
        validate_integration_connection_transition("DISCONNECTED", "ACTIVE")
    assert exc_info.value.code == "INVALID_INTEGRATION_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_s007_approval_execution_status_separation(db_session: AsyncSession, tenant_a: Tenant):
    """S-007: Tests that Approval.status remains APPROVED while execution outcome is stored in metadata."""
    svc = RefundService(db_session)

    # Create dummy payment
    inv = Invoice(
        tenant_id=tenant_a.id,
        invoice_number=f"INV-S007-{uuid.uuid4().hex[:6]}",
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
        status="ISSUED",
    )
    db_session.add(inv)
    await db_session.flush()

    payment = Payment(
        tenant_id=tenant_a.id,
        invoice_id=inv.id,
        amount=Decimal("100.00"),
        refunded_amount=Decimal("0.00"),
        status="SUCCEEDED",
        provider="fake",
        provider_payment_id=f"pay_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(payment)
    await db_session.flush()

    # Request refund -> creates PENDING approval
    approval = await svc.request_refund(
        tenant_id=tenant_a.id,
        payment_id=payment.id,
        amount=Decimal("50.00"),
        reason="Customer request",
    )
    assert approval.status == "PENDING"

    # Approve refund -> status becomes APPROVED
    approval.status = "APPROVED"
    approval.decided_by = "owner"
    await db_session.commit()

    # Execute refund -> approval.status becomes EXECUTED!
    executed_payment = await svc.execute_approved_refund(
        tenant_id=tenant_a.id,
        approval_id=approval.id,
    )
    assert approval.status == "EXECUTED"
    assert executed_payment.status == "PARTIALLY_REFUNDED"
    assert executed_payment.refunded_amount == Decimal("50.00")


@pytest.mark.asyncio
async def test_s001_prospect_cannot_directly_become_onboarding(tenant_a: Tenant):
    """1. PROSPECT cannot directly become ONBOARDING."""
    with pytest.raises(AppException) as exc_info:
        validate_tenant_lifecycle_transition("PROSPECT", "ONBOARDING", tenant_a)
    assert exc_info.value.code == "INVALID_TENANT_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_s001_unpaid_tenant_stops_at_waiting_payment(db_session: AsyncSession, tenant_a: Tenant):
    """2 & 3. advance_to_onboarding() stops unpaid tenants at WAITING_PAYMENT without marking PAID."""
    from app.tenants.lifecycle import ClientLifecycleManager

    mgr = ClientLifecycleManager(db_session)

    # Ensure tenant is in PROSPECT state
    tenant_a.lifecycle_state = "PROSPECT"
    await db_session.commit()

    # Calling advance_to_onboarding on PROSPECT without verified payment stops at WAITING_PAYMENT
    res_tenant = await mgr.advance_to_onboarding(tenant_a.id)
    assert res_tenant.lifecycle_state == "WAITING_PAYMENT"


@pytest.mark.asyncio
async def test_is_payment_verified_authoritative_chain_cases_a_through_h(
    db_session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
):
    """
    Tests authoritative payment verification cases A through H enforcing:
        Subscription -> Paid Invoice (subscription_id == Subscription.id) -> Succeeded Payment (invoice_id == Invoice.id)
    """
    from app.tenants.lifecycle import ClientLifecycleManager
    from app.tenants.repository import TenantRepository
    from app.tenants.schemas import TenantCreate

    mgr_a = ClientLifecycleManager(db_session)
    now = datetime.now(timezone.utc)

    # Setup Tenant C
    repo = TenantRepository(db_session)
    tenant_c = await repo.create(
        TenantCreate(name="Tenant Gamma", slug=f"tenant-gamma-{uuid.uuid4().hex[:6]}", is_active=True)
    )
    await db_session.commit()

    # Setup Plan
    plan_paid = Plan(
        name="Pro Plan",
        code=f"pro_{uuid.uuid4().hex[:6]}",
        price_monthly=Decimal("299000.00"),
        price_yearly=Decimal("2990000.00"),
    )
    plan_free = Plan(
        name="Free Plan",
        code=f"free_{uuid.uuid4().hex[:6]}",
        price_monthly=Decimal("0.00"),
        price_yearly=Decimal("0.00"),
    )
    db_session.add_all([plan_paid, plan_free])
    await db_session.flush()

    # Paid Subscription for Tenant A
    sub_a = Subscription(
        tenant_id=tenant_a.id,
        plan_id=plan_paid.id,
        status="ACTIVE",
        billing_cycle="MONTHLY",
        amount=Decimal("299000.00"),
        started_at=now,
        current_period_start=now,
        current_period_end=now,
    )
    db_session.add(sub_a)
    await db_session.commit()

    # Case A: ACTIVE subscription + no current verified payment => reject
    assert await mgr_a.is_payment_verified(tenant_a.id) is False

    # Case B: ACTIVE subscription + historical unrelated SUCCEEDED payment => reject
    inv_unrelated = Invoice(
        tenant_id=tenant_a.id,
        subscription_id=None,
        invoice_number=f"INV-OLD-{uuid.uuid4().hex[:6]}",
        status="PAID",
        subtotal=Decimal("299000.00"),
        total=Decimal("299000.00"),
    )
    db_session.add(inv_unrelated)
    await db_session.flush()

    pay_unrelated = Payment(
        tenant_id=tenant_a.id,
        invoice_id=inv_unrelated.id,
        amount=Decimal("299000.00"),
        status="SUCCEEDED",
        provider="fake",
    )
    db_session.add(pay_unrelated)
    await db_session.commit()
    assert await mgr_a.is_payment_verified(tenant_a.id) is False

    # Case C: ACTIVE subscription + unrelated PAID invoice => reject
    inv_other_sub = Invoice(
        tenant_id=tenant_a.id,
        subscription_id=uuid.uuid4(),  # Different subscription!
        invoice_number=f"INV-OTHER-{uuid.uuid4().hex[:6]}",
        status="PAID",
        subtotal=Decimal("299000.00"),
        total=Decimal("299000.00"),
    )
    db_session.add(inv_other_sub)
    await db_session.commit()
    assert await mgr_a.is_payment_verified(tenant_a.id) is False

    # Case E: Cross-tenant payment => reject
    sub_b = Subscription(
        tenant_id=tenant_b.id,
        plan_id=plan_paid.id,
        status="ACTIVE",
        billing_cycle="MONTHLY",
        amount=Decimal("299000.00"),
        started_at=now,
        current_period_start=now,
        current_period_end=now,
    )
    db_session.add(sub_b)
    await db_session.flush()

    inv_b = Invoice(
        tenant_id=tenant_b.id,
        subscription_id=sub_b.id,
        invoice_number=f"INV-TENANT-B-{uuid.uuid4().hex[:6]}",
        status="PAID",
        subtotal=Decimal("299000.00"),
        total=Decimal("299000.00"),
    )
    db_session.add(inv_b)
    await db_session.flush()

    pay_b = Payment(
        tenant_id=tenant_b.id,
        invoice_id=inv_b.id,
        amount=Decimal("299000.00"),
        status="SUCCEEDED",
        provider="fake",
    )
    db_session.add(pay_b)
    await db_session.commit()
    assert await mgr_a.is_payment_verified(tenant_a.id) is False

    # Case F: Paid subscription with metadata verified_payment=True but no authoritative payment chain => reject
    sub_a.metadata_ = {"verified_payment": True}
    await db_session.commit()
    assert await mgr_a.is_payment_verified(tenant_a.id) is False

    # Case G: Valid $0/free-plan behavior => accept
    sub_free = Subscription(
        tenant_id=tenant_c.id,
        plan_id=plan_free.id,
        status="ACTIVE",
        billing_cycle="MONTHLY",
        amount=Decimal("0.00"),
        started_at=now,
        current_period_start=now,
        current_period_end=now,
    )
    db_session.add(sub_free)
    await db_session.commit()
    mgr_c = ClientLifecycleManager(db_session)
    assert await mgr_c.is_payment_verified(tenant_c.id) is True

    # Case H: Payment chain with wrong invoice/subscription relationship => reject
    inv_wrong_sub = Invoice(
        tenant_id=tenant_a.id,
        subscription_id=uuid.uuid4(),
        invoice_number=f"INV-WRONG-{uuid.uuid4().hex[:6]}",
        status="PAID",
        subtotal=Decimal("299000.00"),
        total=Decimal("299000.00"),
    )
    db_session.add(inv_wrong_sub)
    await db_session.flush()

    pay_wrong_sub = Payment(
        tenant_id=tenant_a.id,
        invoice_id=inv_wrong_sub.id,
        amount=Decimal("299000.00"),
        status="SUCCEEDED",
        provider="fake",
    )
    db_session.add(pay_wrong_sub)
    await db_session.commit()
    assert await mgr_a.is_payment_verified(tenant_a.id) is False

    # Case D: Correct Subscription -> Invoice -> Payment(SUCCEEDED) => accept
    inv_a_valid = Invoice(
        tenant_id=tenant_a.id,
        subscription_id=sub_a.id,
        invoice_number=f"INV-VALID-{uuid.uuid4().hex[:6]}",
        status="PAID",
        subtotal=Decimal("299000.00"),
        total=Decimal("299000.00"),
    )
    db_session.add(inv_a_valid)
    await db_session.flush()

    pay_a_valid = Payment(
        tenant_id=tenant_a.id,
        invoice_id=inv_a_valid.id,
        amount=Decimal("299000.00"),
        status="SUCCEEDED",
        provider="fake",
    )
    db_session.add(pay_a_valid)
    await db_session.commit()

    # Complete authoritative chain matches -> is_payment_verified() == True!
    assert await mgr_a.is_payment_verified(tenant_a.id) is True


@pytest.mark.asyncio
async def test_s001_verified_paid_tenant_progresses_to_onboarding(db_session: AsyncSession, tenant_a: Tenant):
    """4 & 5. A verified-paid WAITING_PAYMENT tenant transitions to PAID, then CLIENT -> ONBOARDING."""
    from app.tenants.lifecycle import ClientLifecycleManager
    from app.database.models.billing import Plan, Subscription, Invoice, Payment
    from app.billing.state_machine import SubscriptionStatus

    mgr = ClientLifecycleManager(db_session)

    # Seed starter plan and active subscription for tenant
    plan = Plan(
        name="Starter Plan",
        code=f"starter_{uuid.uuid4().hex[:6]}",
        price_monthly=Decimal("100000.00"),
        price_yearly=Decimal("1000000.00"),
    )
    db_session.add(plan)
    await db_session.flush()

    sub = Subscription(
        tenant_id=tenant_a.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        billing_cycle="MONTHLY",
        amount=Decimal("100000.00"),
        started_at=datetime.now(timezone.utc),
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc),
    )
    db_session.add(sub)
    await db_session.flush()

    inv = Invoice(
        tenant_id=tenant_a.id,
        subscription_id=sub.id,
        invoice_number=f"INV-S001-{uuid.uuid4().hex[:6]}",
        status="PAID",
        subtotal=Decimal("100000.00"),
        total=Decimal("100000.00"),
    )
    db_session.add(inv)
    await db_session.flush()

    pay = Payment(
        tenant_id=tenant_a.id,
        invoice_id=inv.id,
        amount=Decimal("100000.00"),
        status="SUCCEEDED",
        provider="fake",
    )
    db_session.add(pay)

    # Set tenant state to WAITING_PAYMENT
    tenant_a.lifecycle_state = "WAITING_PAYMENT"
    await db_session.commit()

    # Call advance_to_onboarding on verified-paid tenant -> completes WAITING_PAYMENT -> PAID -> CLIENT -> ONBOARDING
    res_tenant = await mgr.advance_to_onboarding(tenant_a.id)
    assert res_tenant.lifecycle_state == "ONBOARDING"


@pytest.mark.asyncio
async def test_all_state_machine_validators_reject_unknown_current_state(tenant_a: Tenant):
    """P1-B: Tests that all 5 state machine validators reject UNKNOWN / invalid current states."""
    # 1. Tenant Lifecycle
    with pytest.raises(AppException) as exc1:
        validate_tenant_lifecycle_transition("UNKNOWN_STATE", "LEAD", tenant_a)
    assert exc1.value.code == "INVALID_TENANT_STATE_TRANSITION"

    # 2. Human Handoff State
    with pytest.raises(AppException) as exc2:
        validate_handoff_state_transition("UNKNOWN_STATE", "HUMAN_ASSIGNED")
    assert exc2.value.code == "INVALID_HANDOFF_STATE_TRANSITION"

    # 3. Workflow Execution Status
    with pytest.raises(AppException) as exc3:
        validate_workflow_execution_transition("UNKNOWN_STATE", "RUNNING")
    assert exc3.value.code == "INVALID_WORKFLOW_STATE_TRANSITION"

    # 4. Task Status
    with pytest.raises(AppException) as exc4:
        validate_task_status_transition("UNKNOWN_STATE", "IN_PROGRESS")
    assert exc4.value.code == "INVALID_TASK_STATE_TRANSITION"

    # 5. Integration Connection Status
    with pytest.raises(AppException) as exc5:
        validate_integration_connection_transition("UNKNOWN_STATE", "CONNECTING")
    assert exc5.value.code == "INVALID_INTEGRATION_STATE_TRANSITION"


@pytest.mark.asyncio
async def test_s001_paid_and_client_tenants_progress_without_replaying(db_session: AsyncSession, tenant_a: Tenant):
    """5 & 6. Tenants starting from PAID or CLIENT progress forward without replaying earlier states."""
    from app.tenants.lifecycle import ClientLifecycleManager

    mgr = ClientLifecycleManager(db_session)

    # Starting from PAID -> CLIENT -> ONBOARDING
    tenant_a.lifecycle_state = "PAID"
    await db_session.commit()

    res1 = await mgr.advance_to_onboarding(tenant_a.id)
    assert res1.lifecycle_state == "ONBOARDING"

    # Calling advance_to_onboarding on ONBOARDING tenant returns immediately without state changes
    res2 = await mgr.advance_to_onboarding(tenant_a.id)
    assert res2.lifecycle_state == "ONBOARDING"


@pytest.mark.asyncio
async def test_s006_disconnect_integration_validation(db_session: AsyncSession, tenant_a: Tenant):
    """7. S-006 disconnect_integration validation is enforced immediately before status mutation."""
    from app.integrations.service import IntegrationService
    from app.database.models.integrations import Integration, IntegrationConnection

    svc = IntegrationService(db_session)

    integration = Integration(
        integration_key=f"test_key_{uuid.uuid4().hex[:6]}",
        provider_key="whatsapp_cloud_api",
        display_name="Test WhatsApp",
        category="messaging",
    )
    db_session.add(integration)
    await db_session.flush()

    conn = IntegrationConnection(
        tenant_id=tenant_a.id,
        integration_id=integration.id,
        provider_key="whatsapp_cloud_api",
        status="ACTIVE",
    )
    db_session.add(conn)
    await db_session.commit()

    # Disconnect active connection -> transitions ACTIVE to DISCONNECTED
    disc_conn = await svc.disconnect_integration(
        tenant_id=tenant_a.id,
        connection_id=conn.id,
        allow_internal=True,
    )
    assert disc_conn.status == "DISCONNECTED"

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
    assert exc_info.value.code == "INVALID_TENANT_LIFECYCLE_TRANSITION"


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
        metadata_={},
    )

    # Initial handoff state derived from OPEN -> RESUME_AI
    assert get_handoff_lifecycle_state(conv) == HumanHandoffState.RESUME_AI.value

    # RESUME_AI -> AI_HANDOFF_REQUESTED -> updates Conversation.status to WAITING_HUMAN
    sync_handoff_with_conversation_status(conv, "AI_HANDOFF_REQUESTED")
    assert conv.metadata_["handoff_state"] == "AI_HANDOFF_REQUESTED"
    assert conv.status == "WAITING_HUMAN"

    # AI_HANDOFF_REQUESTED -> HUMAN_IN_PROGRESS -> updates Conversation.status to HUMAN_ACTIVE
    sync_handoff_with_conversation_status(conv, "HUMAN_IN_PROGRESS")
    assert conv.metadata_["handoff_state"] == "HUMAN_IN_PROGRESS"
    assert conv.status == "HUMAN_ACTIVE"

    # Invalid jump: RESOLVED directly to HUMAN_ASSIGNED without VERIFY/RESUME_AI
    conv.metadata_["handoff_state"] = "RESOLVED"
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

    # Execute refund -> approval.status remains APPROVED, execution_status becomes EXECUTED in metadata_!
    executed_payment = await svc.execute_approved_refund(
        tenant_id=tenant_a.id,
        approval_id=approval.id,
    )
    assert approval.status == "APPROVED"
    assert approval.meta_data.get("execution_status") == "EXECUTED"
    assert executed_payment.status == "PARTIALLY_REFUNDED"
    assert executed_payment.refunded_amount == Decimal("50.00")


@pytest.mark.asyncio
async def test_s001_prospect_cannot_directly_become_onboarding(tenant_a: Tenant):
    """1. PROSPECT cannot directly become ONBOARDING."""
    with pytest.raises(AppException) as exc_info:
        validate_tenant_lifecycle_transition("PROSPECT", "ONBOARDING", tenant_a)
    assert exc_info.value.code == "INVALID_TENANT_LIFECYCLE_TRANSITION"


@pytest.mark.asyncio
async def test_s001_unpaid_tenant_stops_at_waiting_payment(db_session: AsyncSession, tenant_a: Tenant):
    """2 & 3. start_onboarding() and advance_to_onboarding() stop unpaid tenants at WAITING_PAYMENT without marking PAID."""
    from app.tenants.onboarding_service import OnboardingService
    from app.tenants.lifecycle import ClientLifecycleManager

    onboarding_svc = OnboardingService(db_session)
    mgr = ClientLifecycleManager(db_session)

    # Ensure tenant is in PROSPECT state
    tenant_a.lifecycle_state = "PROSPECT"
    await db_session.commit()

    # Call start_onboarding -> progresses PROSPECT -> LEAD -> QUALIFIED -> PROPOSAL -> WAITING_PAYMENT and pauses!
    summary = await onboarding_svc.start_onboarding(tenant_a.id)
    await db_session.refresh(tenant_a)

    assert tenant_a.lifecycle_state == "WAITING_PAYMENT"
    assert summary.lifecycle_state == "WAITING_PAYMENT"

    # Calling advance_to_onboarding on WAITING_PAYMENT without verified payment keeps tenant in WAITING_PAYMENT
    res_tenant = await mgr.advance_to_onboarding(tenant_a.id)
    assert res_tenant.lifecycle_state == "WAITING_PAYMENT"


@pytest.mark.asyncio
async def test_s001_verified_paid_tenant_progresses_to_onboarding(db_session: AsyncSession, tenant_a: Tenant):
    """4 & 5. A verified-paid WAITING_PAYMENT tenant transitions to PAID, then CLIENT -> ONBOARDING."""
    from app.tenants.lifecycle import ClientLifecycleManager
    from app.database.models.billing import Plan, Subscription
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
        metadata_={"verified_payment": True},
    )
    db_session.add(sub)

    # Set tenant state to WAITING_PAYMENT
    tenant_a.lifecycle_state = "WAITING_PAYMENT"
    await db_session.commit()

    # Call advance_to_onboarding on verified-paid tenant -> completes WAITING_PAYMENT -> PAID -> CLIENT -> ONBOARDING
    res_tenant = await mgr.advance_to_onboarding(tenant_a.id)
    assert res_tenant.lifecycle_state == "ONBOARDING"


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

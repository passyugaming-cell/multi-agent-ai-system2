import uuid
import pytest
from app.core.tasks.service import TaskService
from app.core.approvals.service import ApprovalService
from app.core.events.schemas import EventSchema
from app.core.workflows.engine import WorkflowEngine
from app.database.models.workflow import WorkflowConfiguration, Approval
from app.core.exceptions import AppError
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context


@pytest.mark.asyncio
async def test_task_lifecycle_transitions(db_session, tenant_a):
    service = TaskService(db_session)

    # Create task
    task = await service.create_task(
        tenant_id=tenant_a.id,
        title="Manual Audit Task",
        description="Verify high-value customer order",
    )
    assert task.status == "CREATED"

    # Transition to IN_PROGRESS
    task = await service.update_status(tenant_a.id, task.id, "IN_PROGRESS")
    assert task.status == "IN_PROGRESS"
    assert task.started_at is not None

    # Complete task
    task = await service.update_status(tenant_a.id, task.id, "COMPLETED", result={"approved_audit": True})
    assert task.status == "COMPLETED"
    assert task.completed_at is not None

    # Attempt invalid transition from COMPLETED to IN_PROGRESS
    with pytest.raises(AppError, match="Invalid task status transition"):
        await service.update_status(tenant_a.id, task.id, "IN_PROGRESS")


@pytest.mark.asyncio
async def test_approval_workflow_pause_and_resume(db_session, tenant_a):
    tenant_uuid = tenant_a.id

    # Create high risk workflow
    wf = WorkflowConfiguration(
        tenant_id=tenant_uuid,
        key="PRICE_CHANGE_WF",
        name="Price Change Workflow",
        trigger_type="price.update_requested",
        actions=[
            {
                "action": "change_product_price",
                "target": "product_123",
                "reason": "Market rate adjustment",
            }
        ],
        is_active=True,
    )
    db_session.add(wf)
    await db_session.commit()

    # Emit event
    event = EventSchema(
        event_id=f"evt_{uuid.uuid4().hex[:10]}",
        tenant_id=str(tenant_uuid),
        event_type="price.update_requested",
        payload={"product_id": "product_123", "new_price": 250},
        source="pricing_service",
    )

    engine = WorkflowEngine(db_session)
    executions = await engine.handle_event(event)

    assert len(executions) == 1
    exec_inst = executions[0]
    # Execution should be paused in WAITING_APPROVAL state
    assert exec_inst.status == "WAITING_APPROVAL"

    # Verify approval record created
    appr_service = ApprovalService(db_session)
    approvals = await appr_service.list_approvals(tenant_uuid, status="PENDING")
    assert len(approvals) == 1
    appr = approvals[0]
    assert appr.risk_level == "HIGH"

    # Approve request with Human Platform Owner actor context
    token = set_actor_context(
        AuthenticatedActor(
            user_id=uuid.uuid4(),
            tenant_id=tenant_uuid,
            role="owner",
            permissions={"business.read", "product.read", "knowledge.read"},
            is_platform_owner=True,
        )
    )
    try:
        approved = await appr_service.approve(tenant_uuid, appr.id, decided_by="owner@company.com")
    finally:
        reset_actor_context(token)
    assert approved.status == "APPROVED"

    # Refresh execution, now should be COMPLETED
    await db_session.refresh(exec_inst)
    assert exec_inst.status == "COMPLETED"


@pytest.mark.asyncio
async def test_approval_rejection_cancels_workflow(db_session, tenant_a):
    tenant_uuid = tenant_a.id

    wf = WorkflowConfiguration(
        tenant_id=tenant_uuid,
        key="REFUND_WF",
        name="Refund Processing Workflow",
        trigger_type="refund.requested",
        actions=[
            {
                "action": "issue_refund",
                "target": "order_456",
                "reason": "Customer request",
            }
        ],
        is_active=True,
    )
    db_session.add(wf)
    await db_session.commit()

    event = EventSchema(
        event_id=f"evt_{uuid.uuid4().hex[:10]}",
        tenant_id=str(tenant_uuid),
        event_type="refund.requested",
        payload={"order_id": "order_456", "amount": 500},
        source="support_service",
    )

    engine = WorkflowEngine(db_session)
    executions = await engine.handle_event(event)
    exec_inst = executions[0]

    appr_service = ApprovalService(db_session)
    approvals = await appr_service.list_approvals(tenant_uuid, status="PENDING")
    appr = approvals[0]

    # Reject approval
    rejected = await appr_service.reject(
        tenant_uuid, appr.id, decided_by="owner@company.com", reason="Refund policy not met"
    )
    assert rejected.status == "REJECTED"

    # Refresh execution, should be CANCELLED
    await db_session.refresh(exec_inst)
    assert exec_inst.status == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_approval_authorization_scenarios(db_session, tenant_a, tenant_b):
    """Verify approval cancellation authorization matrix:
    1. Requester can cancel pending approval.
    2. Actor with business.write can cancel pending approval of another user.
    3. Ordinary tenant member without business.write cannot cancel another user's approval.
    4. Cross-tenant actor cannot cancel approval.
    5. Unauthenticated actor fails closed.
    6. Terminal states (APPROVED, REJECTED, CANCELLED) cannot be cancelled.
    """
    approval_service = ApprovalService(db_session)
    user_requester_id = uuid.uuid4()

    # Create pending approval
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by=str(user_requester_id),
        action_type="update_customer",
        target="customer_123",
        reason="Update details",
        risk_level="MEDIUM",
        status="PENDING",
    )
    db_session.add(appr)
    await db_session.commit()

    # 1. Unauthenticated actor -> fails closed 403
    with pytest.raises(AppError) as exc_info:
        await approval_service.cancel(tenant_a.id, appr.id)
    assert exc_info.value.status_code == 403

    # 2. Cross-tenant actor -> fails closed 403 / 404
    actor_tenant_b = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_b.id,
        role="owner",
        permissions={"business.write"},
    )
    token = set_actor_context(actor_tenant_b)
    try:
        with pytest.raises(AppError) as exc_info:
            await approval_service.cancel(tenant_a.id, appr.id)
        assert exc_info.value.status_code in (403, 404)
    finally:
        reset_actor_context(token)

    # 3. Ordinary tenant member without business.write -> 403
    actor_member = AuthenticatedActor(
        user_id=uuid.uuid4(), # Different user ID!
        tenant_id=tenant_a.id,
        role="member",
        permissions={"business.read"},
    )
    token = set_actor_context(actor_member)
    try:
        with pytest.raises(AppError) as exc_info:
            await approval_service.cancel(tenant_a.id, appr.id)
        assert exc_info.value.status_code == 403
        assert "PERMISSION_DENIED" in exc_info.value.message
    finally:
        reset_actor_context(token)

    # 4. Requester cancelling their own pending approval -> SUCCESS
    actor_requester = AuthenticatedActor(
        user_id=user_requester_id,
        tenant_id=tenant_a.id,
        role="member",
        permissions={"business.read"},
    )
    token = set_actor_context(actor_requester)
    try:
        cancelled_appr = await approval_service.cancel(tenant_a.id, appr.id, reason="Requester cancelled")
        assert cancelled_appr.status == "CANCELLED"
    finally:
        reset_actor_context(token)

    # 5. Already CANCELLED approval cannot be cancelled again -> 400
    token = set_actor_context(actor_requester)
    try:
        with pytest.raises(AppError) as exc_info:
            await approval_service.cancel(tenant_a.id, appr.id)
        assert exc_info.value.status_code == 400
        assert "must be PENDING" in exc_info.value.message
    finally:
        reset_actor_context(token)

    # 6. Actor with business.write cancelling another user's pending approval -> SUCCESS
    appr2 = Approval(
        tenant_id=tenant_a.id,
        requested_by=str(uuid.uuid4()),
        action_type="update_order",
        target="order_456",
        reason="Update order",
        risk_level="MEDIUM",
        status="PENDING",
    )
    db_session.add(appr2)
    await db_session.commit()

    actor_admin = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="admin",
        permissions={"business.write"},
    )
    token = set_actor_context(actor_admin)
    try:
        cancelled2 = await approval_service.cancel(tenant_a.id, appr2.id, reason="Admin cancelled")
        assert cancelled2.status == "CANCELLED"
    finally:
        reset_actor_context(token)

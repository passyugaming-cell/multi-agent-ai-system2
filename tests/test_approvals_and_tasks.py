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
async def test_approval_cancellation_authorization_and_lifecycle(db_session, tenant_a, tenant_b):
    appr_service = ApprovalService(db_session)
    user_req_id = uuid.uuid4()
    user_other_id = uuid.uuid4()

    # 1. Original requester can cancel pending approval
    appr1 = Approval(
        tenant_id=tenant_a.id,
        requested_by=str(user_req_id),
        action_type="change_product_price",
        target="product_1",
        reason="Price adjustment",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr1)
    await db_session.commit()

    token = set_actor_context(
        AuthenticatedActor(
            user_id=user_req_id,
            tenant_id=tenant_a.id,
            role="member",
            permissions={"business.read"},
        )
    )
    try:
        cancelled1 = await appr_service.cancel(tenant_a.id, appr1.id)
        assert cancelled1.status == "CANCELLED"
    finally:
        reset_actor_context(token)

    # 2. Actor with business.write can cancel pending approval created by another user
    appr2 = Approval(
        tenant_id=tenant_a.id,
        requested_by=str(user_req_id),
        action_type="change_product_price",
        target="product_2",
        reason="Price adjustment 2",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr2)
    await db_session.commit()

    token = set_actor_context(
        AuthenticatedActor(
            user_id=user_other_id,
            tenant_id=tenant_a.id,
            role="admin",
            permissions={"business.write"},
        )
    )
    try:
        cancelled2 = await appr_service.cancel(tenant_a.id, appr2.id)
        assert cancelled2.status == "CANCELLED"
    finally:
        reset_actor_context(token)

    # 3. Ordinary tenant member without business.write cannot cancel another user's approval
    appr3 = Approval(
        tenant_id=tenant_a.id,
        requested_by=str(user_req_id),
        action_type="change_product_price",
        target="product_3",
        reason="Price adjustment 3",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr3)
    await db_session.commit()

    token = set_actor_context(
        AuthenticatedActor(
            user_id=user_other_id,
            tenant_id=tenant_a.id,
            role="member",
            permissions={"business.read"},  # No business.write
        )
    )
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.cancel(tenant_a.id, appr3.id)
        assert exc_info.value.status_code == 403
        assert "PERMISSION_DENIED" in exc_info.value.message
    finally:
        reset_actor_context(token)

    # 4. Cross-tenant actor cannot cancel approval
    token = set_actor_context(
        AuthenticatedActor(
            user_id=user_other_id,
            tenant_id=tenant_b.id,  # Cross-tenant actor context
            role="admin",
            permissions={"business.write"},
        )
    )
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.cancel(tenant_a.id, appr3.id)
        assert exc_info.value.status_code == 404
    finally:
        reset_actor_context(token)

    # 5. Unauthenticated actor fails closed
    with pytest.raises(AppError) as exc_info:
        await appr_service.cancel(tenant_a.id, appr3.id)
    assert exc_info.value.status_code == 403
    assert "Authentication required" in exc_info.value.message

    # 6. Already approved approval cannot be cancelled
    appr_approved = Approval(
        tenant_id=tenant_a.id,
        requested_by=str(user_req_id),
        action_type="change_product_price",
        target="product_4",
        reason="Price adjustment 4",
        risk_level="MEDIUM",
        status="APPROVED",
    )
    db_session.add(appr_approved)
    await db_session.commit()

    token = set_actor_context(
        AuthenticatedActor(
            user_id=user_req_id,
            tenant_id=tenant_a.id,
            role="member",
            permissions={"business.read"},
        )
    )
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.cancel(tenant_a.id, appr_approved.id)
        assert exc_info.value.status_code == 400
        assert "Cannot cancel non-pending approval" in exc_info.value.message
    finally:
        reset_actor_context(token)

    # 7. Already rejected approval cannot be cancelled
    appr_rejected = Approval(
        tenant_id=tenant_a.id,
        requested_by=str(user_req_id),
        action_type="change_product_price",
        target="product_5",
        reason="Price adjustment 5",
        risk_level="MEDIUM",
        status="REJECTED",
    )
    db_session.add(appr_rejected)
    await db_session.commit()

    token = set_actor_context(
        AuthenticatedActor(
            user_id=user_req_id,
            tenant_id=tenant_a.id,
            role="member",
            permissions={"business.read"},
        )
    )
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.cancel(tenant_a.id, appr_rejected.id)
        assert exc_info.value.status_code == 400
        assert "Cannot cancel non-pending approval" in exc_info.value.message
    finally:
        reset_actor_context(token)

    # 8. Already cancelled approval cannot be cancelled
    token = set_actor_context(
        AuthenticatedActor(
            user_id=user_req_id,
            tenant_id=tenant_a.id,
            role="member",
            permissions={"business.read"},
        )
    )
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.cancel(tenant_a.id, appr1.id)  # appr1 was cancelled in step 1
        assert exc_info.value.status_code == 400
        assert "Cannot cancel non-pending approval" in exc_info.value.message
    finally:
        reset_actor_context(token)

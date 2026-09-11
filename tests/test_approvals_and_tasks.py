import uuid
import pytest
from app.core.tasks.service import TaskService
from app.core.approvals.service import ApprovalService
from app.core.events.schemas import EventSchema
from app.core.workflows.engine import WorkflowEngine
from app.database.models.workflow import Approval, WorkflowExecution, WorkflowConfiguration
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
async def test_approval_cancel_authorization_scenarios(db_session, tenant_a, tenant_b):
    appr_service = ApprovalService(db_session)
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()

    # Scenario A: Same user_id + no business.write -> ALLOW
    appr_a = Approval(
        tenant_id=tenant_a.id,
        requested_by=str(user_a_id),
        action_type="change_product_price",
        target="prod_a",
        reason="Test cancel A",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr_a)
    await db_session.commit()

    token_a = set_actor_context(
        AuthenticatedActor(
            user_id=user_a_id,
            tenant_id=tenant_a.id,
            role="member",
            permissions={"business.read"},  # No business.write
            is_platform_owner=False,
        )
    )
    try:
        cancelled_a = await appr_service.cancel(tenant_a.id, appr_a.id)
        assert cancelled_a.status == "CANCELLED"
    finally:
        reset_actor_context(token_a)

    # Scenario B: Critical regression - Different user_id + role matching requested_by string -> DENY
    # approval.requested_by = User A
    # actor.user_id = User B
    # actor.role = value matching requested_by (str(user_a_id))
    appr_b = Approval(
        tenant_id=tenant_a.id,
        requested_by=str(user_a_id),
        action_type="change_product_price",
        target="prod_b",
        reason="Test cancel B",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr_b)
    await db_session.commit()

    token_b_role_match = set_actor_context(
        AuthenticatedActor(
            user_id=user_b_id,  # User B identity
            tenant_id=tenant_a.id,
            role=str(user_a_id),  # Role matches requested_by string!
            permissions={"business.read"},  # NO business.write!
            is_platform_owner=False,
        )
    )
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.cancel(tenant_a.id, appr_b.id)
        assert exc_info.value.status_code == 403
        assert "PERMISSION_DENIED" in exc_info.value.message
    finally:
        reset_actor_context(token_b_role_match)

    # Scenario C: Different user_id + business.write -> ALLOW
    token_b_with_write = set_actor_context(
        AuthenticatedActor(
            user_id=user_b_id,
            tenant_id=tenant_a.id,
            role="admin",
            permissions={"business.read", "business.write"},
            is_platform_owner=False,
        )
    )
    try:
        cancelled_b = await appr_service.cancel(tenant_a.id, appr_b.id)
        assert cancelled_b.status == "CANCELLED"
    finally:
        reset_actor_context(token_b_with_write)

    # Scenario D: Cross-tenant actor -> DENY
    appr_d = Approval(
        tenant_id=tenant_a.id,
        requested_by=str(user_a_id),
        action_type="change_product_price",
        target="prod_d",
        reason="Test cancel D",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr_d)
    await db_session.commit()

    token_cross_tenant = set_actor_context(
        AuthenticatedActor(
            user_id=user_b_id,
            tenant_id=tenant_b.id,  # Cross-tenant actor
            role="admin",
            permissions={"business.read", "business.write"},
            is_platform_owner=False,
        )
    )
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.cancel(tenant_a.id, appr_d.id)
        assert exc_info.value.status_code == 403
        assert "PERMISSION_DENIED" in exc_info.value.message
    finally:
        reset_actor_context(token_cross_tenant)

    # Scenario E: No actor context -> 403
    with pytest.raises(AppError) as exc_info:
        await appr_service.cancel(tenant_a.id, appr_d.id)
    assert exc_info.value.status_code == 403
    assert "Authentication required" in exc_info.value.message

    # Scenario F: Non-pending statuses (APPROVED / REJECTED / CANCELLED) -> 400
    for status in ["APPROVED", "REJECTED", "CANCELLED"]:
        appr_non_pending = Approval(
            tenant_id=tenant_a.id,
            requested_by=str(user_a_id),
            action_type="change_product_price",
            target=f"prod_non_pending_{status}",
            reason=f"Test non pending {status}",
            risk_level="HIGH",
            status=status,
        )
        db_session.add(appr_non_pending)
        await db_session.commit()

        token_a_cancel = set_actor_context(
            AuthenticatedActor(
                user_id=user_a_id,
                tenant_id=tenant_a.id,
                role="member",
                permissions={"business.read", "business.write"},
                is_platform_owner=False,
            )
        )
        try:
            with pytest.raises(AppError) as exc_info:
                await appr_service.cancel(tenant_a.id, appr_non_pending.id)
            assert exc_info.value.status_code == 400
            assert "Cannot cancel non-pending approval" in exc_info.value.message
        finally:
            reset_actor_context(token_a_cancel)


@pytest.mark.asyncio
async def test_approval_cancel_cancels_associated_workflow_execution(db_session, tenant_a):
    # Scenario G: Pending approval with associated workflow execution -> approval CANCELLED, workflow execution CANCELLED
    user_a_id = uuid.uuid4()
    appr_service = ApprovalService(db_session)

    wf = WorkflowConfiguration(
        tenant_id=tenant_a.id,
        key="CANCEL_WF_TEST",
        name="Cancel WF Test",
        trigger_type="test.event",
        actions=[{"action": "test_action"}],
        is_active=True,
    )
    db_session.add(wf)
    await db_session.commit()

    execution = WorkflowExecution(
        tenant_id=tenant_a.id,
        workflow_id=wf.id,
        event_id="evt_test_cancel",
        status="WAITING_APPROVAL",
        current_step=0,
        context={},
    )
    db_session.add(execution)
    await db_session.commit()

    approval = Approval(
        tenant_id=tenant_a.id,
        workflow_execution_id=execution.id,
        requested_by=str(user_a_id),
        action_type="test_action",
        target="target_x",
        reason="Cancel wf test",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(approval)
    await db_session.commit()

    token_a = set_actor_context(
        AuthenticatedActor(
            user_id=user_a_id,
            tenant_id=tenant_a.id,
            role="member",
            permissions={"business.read"},
            is_platform_owner=False,
        )
    )
    try:
        cancelled_appr = await appr_service.cancel(tenant_a.id, approval.id)
        assert cancelled_appr.status == "CANCELLED"

        await db_session.refresh(execution)
        assert execution.status == "CANCELLED"
        assert f"approval cancelled by {user_a_id}" in execution.error
    finally:
        reset_actor_context(token_a)

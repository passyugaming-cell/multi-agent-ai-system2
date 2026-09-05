import uuid
import pytest
from app.core.tasks.service import TaskService
from app.core.approvals.service import ApprovalService
from app.core.events.schemas import EventSchema
from app.core.workflows.engine import WorkflowEngine
from app.database.models.workflow import WorkflowConfiguration
from app.core.exceptions import AppError


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

    # Approve request
    approved = await appr_service.approve(tenant_uuid, appr.id, decided_by="owner@company.com")
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

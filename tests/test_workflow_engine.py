import uuid
import pytest
from app.core.workflows.conditions import ConditionEvaluator
from app.core.workflows.actions import ActionExecutor, RiskLevel, get_action_risk_level
from app.core.workflows.engine import WorkflowEngine
from app.database.models.workflow import WorkflowConfiguration, WorkflowExecution
from app.core.events.schemas import EventSchema


@pytest.mark.asyncio
async def test_condition_evaluator():
    context = {
        "order": {"total": 150000, "status": "PENDING"},
        "customer": {"is_new": True, "name": "Alice"},
    }

    # Test greater_or_equal and equals
    cond_1 = {"field": "order.total", "operator": "greater_or_equal", "value": 100000}
    assert ConditionEvaluator.evaluate_condition(cond_1, context) is True

    # Test AND logic
    cond_and = {
        "AND": [
            {"field": "order.total", "operator": "greater_or_equal", "value": 100000},
            {"field": "customer.is_new", "operator": "equals", "value": True},
        ]
    }
    assert ConditionEvaluator.evaluate_condition(cond_and, context) is True

    # Test condition false
    cond_false = {"field": "order.total", "operator": "less_than", "value": 50000}
    assert ConditionEvaluator.evaluate_condition(cond_false, context) is False


@pytest.mark.asyncio
async def test_action_risk_classification():
    assert get_action_risk_level("send_message", {}) == RiskLevel.LOW
    assert get_action_risk_level("update_order", {}) == RiskLevel.MEDIUM
    assert get_action_risk_level("change_product_price", {}) == RiskLevel.HIGH
    assert get_action_risk_level("delete_customer", {}) == RiskLevel.CRITICAL


@pytest.mark.asyncio
async def test_workflow_engine_event_matching_and_execution(db_session, tenant_a):
    tenant_uuid = tenant_a.id

    # Create Workflow Configuration
    wf = WorkflowConfiguration(
        tenant_id=tenant_uuid,
        key="TEST_NEW_ORDER",
        name="Test New Order Workflow",
        trigger_type="order.created",
        conditions=[
            {"field": "payload.total", "operator": "greater_than", "value": 50}
        ],
        actions=[
            {"action": "send_message", "message": "Thank you for your order!"},
            {"action": "add_tag", "tag": "vip_order"},
        ],
        is_active=True,
    )
    db_session.add(wf)
    await db_session.commit()

    # Emit order.created event
    event = EventSchema(
        event_id=f"evt_{uuid.uuid4().hex[:10]}",
        tenant_id=str(tenant_uuid),
        event_type="order.created",
        payload={"order_id": "ord_100", "total": 100},
        source="order_service",
    )

    engine = WorkflowEngine(db_session)
    executions = await engine.handle_event(event)

    assert len(executions) == 1
    exec_inst = executions[0]
    assert exec_inst.status == "COMPLETED"
    assert exec_inst.current_step == 2
    assert exec_inst.context.get("tags") == ["vip_order"]


@pytest.mark.asyncio
async def test_workflow_engine_idempotency(db_session, tenant_a):
    tenant_uuid = tenant_a.id

    wf = WorkflowConfiguration(
        tenant_id=tenant_uuid,
        key="TEST_IDEMPOTENCY",
        name="Test Idempotency Workflow",
        trigger_type="customer.created",
        actions=[{"action": "send_message", "message": "Welcome!"}],
        is_active=True,
    )
    db_session.add(wf)
    await db_session.commit()

    event = EventSchema(
        event_id="evt_duplicate_id_001",
        tenant_id=str(tenant_uuid),
        event_type="customer.created",
        payload={"customer_id": "cust_123"},
        source="customer_service",
    )

    engine = WorkflowEngine(db_session)
    execs_1 = await engine.handle_event(event)
    execs_2 = await engine.handle_event(event)

    assert len(execs_1) == 1
    assert len(execs_2) == 1
    # Second execution returns identical existing execution record without duplication
    assert execs_1[0].id == execs_2[0].id

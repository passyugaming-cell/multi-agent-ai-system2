import uuid
import pytest
from httpx import AsyncClient
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context


@pytest.mark.asyncio
async def test_events_api(client: AsyncClient, tenant_a):
    headers = {"X-Tenant-ID": str(tenant_a.id)}

    res = await client.post(
        "/api/v1/events",
        json={
            "event_type": "customer.created",
            "payload": {"customer_id": "cust_999"},
            "source": "api_test",
        },
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["event_type"] == "customer.created"
    assert data["tenant_id"] == str(tenant_a.id)


@pytest.mark.asyncio
async def test_workflows_api(client: AsyncClient, tenant_a):
    headers = {"X-Tenant-ID": str(tenant_a.id)}

    # Create workflow
    res = await client.post(
        "/api/v1/workflows",
        json={
            "key": "ORDER_ALERT",
            "name": "Order Alert Workflow",
            "trigger_type": "order.created",
            "actions": [{"action": "send_message", "message": "Order received!"}],
        },
        headers=headers,
    )
    assert res.status_code == 201
    wf_data = res.json()
    wf_id = wf_data["id"]

    # List workflows
    res_list = await client.get("/api/v1/workflows", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    # Disable workflow
    res_dis = await client.post(f"/api/v1/workflows/{wf_id}/disable", headers=headers)
    assert res_dis.status_code == 200
    assert res_dis.json()["is_active"] is False


@pytest.mark.asyncio
async def test_tasks_api(client: AsyncClient, tenant_a):
    headers = {"X-Tenant-ID": str(tenant_a.id)}

    # Create task
    res = await client.post(
        "/api/v1/tasks",
        json={
            "title": "Review Customer Document",
            "priority": "HIGH",
        },
        headers=headers,
    )
    assert res.status_code == 201
    task_id = res.json()["id"]

    # Assign task
    res_assign = await client.post(
        f"/api/v1/tasks/{task_id}/assign?assigned_to=agent_bob", headers=headers
    )
    assert res_assign.status_code == 200
    assert res_assign.json()["assigned_to"] == "agent_bob"

    # Complete task
    res_comp = await client.post(f"/api/v1/tasks/{task_id}/complete", headers=headers)
    assert res_comp.status_code == 200
    assert res_comp.json()["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_approvals_api(client: AsyncClient, tenant_a):
    headers = {"X-Tenant-ID": str(tenant_a.id)}

    # Trigger high risk workflow
    await client.post(
        "/api/v1/workflows",
        json={
            "key": "PRODUCT_PRICE_WF",
            "name": "Product Price Workflow",
            "trigger_type": "price.change_requested",
            "actions": [{"action": "change_product_price", "new_price": 500}],
        },
        headers=headers,
    )

    await client.post(
        "/api/v1/events",
        json={
            "event_type": "price.change_requested",
            "payload": {"product_id": "p_1"},
            "source": "api_test",
        },
        headers=headers,
    )

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read", "product.read", "knowledge.read"},
    )
    token = set_actor_context(actor)
    try:
        # Get pending approvals
        res_appr = await client.get("/api/v1/approvals?status=PENDING", headers=headers)
        assert res_appr.status_code == 200
        approvals = res_appr.json()
        assert len(approvals) == 1
        appr_id = approvals[0]["id"]

        # Approve request
        res_decision = await client.post(
            f"/api/v1/approvals/{appr_id}/approve",
            json={"decided_by": "owner@tenant.com", "reason": "Approved market update"},
            headers=headers,
        )
        assert res_decision.status_code == 200
        assert res_decision.json()["status"] == "APPROVED"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_api_tenant_isolation(client: AsyncClient, tenant_a, tenant_b):
    headers_a = {"X-Tenant-ID": str(tenant_a.id)}
    headers_b = {"X-Tenant-ID": str(tenant_b.id)}

    # Tenant A creates task
    res = await client.post(
        "/api/v1/tasks",
        json={"title": "Secret Task Tenant A"},
        headers=headers_a,
    )
    task_id = res.json()["id"]

    # Tenant B attempts to access Tenant A's task
    res_b = await client.get(f"/api/v1/tasks/{task_id}", headers=headers_b)
    assert res_b.status_code == 404

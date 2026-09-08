import pytest
from decimal import Decimal
import uuid
from httpx import AsyncClient

from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.core.auth import ROLE_PERMISSIONS
from app.database.models import Tenant, User, Product, Customer, Conversation, Order
from app.repositories.domain import ProductRepository, CustomerRepository, OrderRepository


@pytest.mark.asyncio
async def test_tenant_isolation_products(async_client: AsyncClient, test_session):
    # 1. Create Tenant A and Tenant B
    tenant_a = Tenant(name="Tenant A", slug="tenant-a-iso", is_active=True)
    tenant_b = Tenant(name="Tenant B", slug="tenant-b-iso", is_active=True)
    test_session.add_all([tenant_a, tenant_b])
    await test_session.commit()

    # 1b. Create User for Tenant A and Tenant B
    user_a = User(tenant_id=tenant_a.id, email="owner_a@test.com", password_hash="hash_a", is_active=True)
    user_b = User(tenant_id=tenant_b.id, email="owner_b@test.com", password_hash="hash_b", is_active=True)
    test_session.add_all([user_a, user_b])
    await test_session.commit()

    # 2. Create Product owned by Tenant A
    product_a = Product(
        tenant_id=tenant_a.id,
        name="Tenant A Product",
        price=Decimal("100000.00"),
        stock=10,
    )
    test_session.add(product_a)
    await test_session.commit()

    headers_a = {"X-Tenant-ID": str(tenant_a.id)}
    headers_b = {"X-Tenant-ID": str(tenant_b.id)}

    # 3. Tenant A can read product_a with trusted actor context
    token_a = set_actor_context(AuthenticatedActor(user_id=user_a.id, tenant_id=tenant_a.id, role="owner", permissions=set(ROLE_PERMISSIONS["owner"])))
    try:
        res_a = await async_client.get(f"/api/v1/products/{product_a.id}", headers=headers_a)
        assert res_a.status_code == 200
        assert res_a.json()["name"] == "Tenant A Product"
    finally:
        reset_actor_context(token_a)

    # 4. Tenant B CANNOT read product_a
    token_b = set_actor_context(AuthenticatedActor(user_id=user_b.id, tenant_id=tenant_b.id, role="owner", permissions=set(ROLE_PERMISSIONS["owner"])))
    try:
        res_b = await async_client.get(f"/api/v1/products/{product_a.id}", headers=headers_b)
        assert res_b.status_code == 404

        # 5. Tenant B listing products returns empty
        res_b_list = await async_client.get("/api/v1/products", headers=headers_b)
        assert res_b_list.status_code == 200
        assert len(res_b_list.json()) == 0
    finally:
        reset_actor_context(token_b)


@pytest.mark.asyncio
async def test_cross_tenant_update_and_delete_prevention(test_session):
    tenant_a = Tenant(name="Tenant A Mut", slug="tenant-a-mut", is_active=True)
    tenant_b = Tenant(name="Tenant B Mut", slug="tenant-b-mut", is_active=True)
    test_session.add_all([tenant_a, tenant_b])
    await test_session.commit()

    product_a = Product(
        tenant_id=tenant_a.id,
        name="Product A",
        price=Decimal("50000.00"),
        stock=5,
    )
    test_session.add(product_a)
    await test_session.commit()

    repo = ProductRepository(test_session)

    # Tenant B tries to update Tenant A's product
    updated = await repo.update(
        tenant_id=tenant_b.id,
        entity_id=product_a.id,
        name="Hacked Name",
    )
    assert updated is None

    # Tenant B tries to delete Tenant A's product
    deleted = await repo.delete(
        tenant_id=tenant_b.id,
        entity_id=product_a.id,
    )
    assert deleted is False


@pytest.mark.asyncio
async def test_cross_tenant_foreign_key_prevention(async_client: AsyncClient, test_session):
    # Create Tenant A and Tenant B
    tenant_a = Tenant(name="Tenant A FK", slug="tenant-a-fk", is_active=True)
    tenant_b = Tenant(name="Tenant B FK", slug="tenant-b-fk", is_active=True)
    test_session.add_all([tenant_a, tenant_b])
    await test_session.commit()

    # Customer owned by Tenant A
    customer_a = Customer(
        tenant_id=tenant_a.id,
        name="Customer A",
        phone="08123456789",
    )
    test_session.add(customer_a)
    await test_session.commit()

    headers_b = {"X-Tenant-ID": str(tenant_b.id)}

    # Tenant B attempts to create order using Customer A's ID
    order_payload = {
        "customer_id": str(customer_a.id),
        "currency": "IDR",
        "items": [],
    }
    res = await async_client.post("/api/v1/orders", json=order_payload, headers=headers_b)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation_customers_and_orders(async_client: AsyncClient, test_session):
    # 1. Create Tenants
    tenant_a = Tenant(name="Tenant Alpha Customers", slug="tenant-a-cust", is_active=True)
    tenant_b = Tenant(name="Tenant Beta Customers", slug="tenant-b-cust", is_active=True)
    test_session.add_all([tenant_a, tenant_b])
    await test_session.commit()

    # 2. Create Customer in Tenant A
    customer_a = Customer(
        tenant_id=tenant_a.id,
        name="Customer Alpha",
        phone="0811111111",
        email="alpha@customer.com",
    )
    test_session.add(customer_a)
    await test_session.commit()

    # 3. Create Product in Tenant A
    product_a = Product(
        tenant_id=tenant_a.id,
        name="Product Alpha",
        price=Decimal("50000.00"),
        stock=20,
    )
    test_session.add(product_a)
    await test_session.commit()

    # 4. Create Order in Tenant A
    order_repo = OrderRepository(test_session)
    order_a = await order_repo.create_order_with_items(
        tenant_id=tenant_a.id,
        customer_id=customer_a.id,
        currency="IDR",
        items_data=[{"product": product_a, "quantity": 2}],
    )
    await test_session.commit()

    headers_a = {"X-Tenant-ID": str(tenant_a.id)}
    headers_b = {"X-Tenant-ID": str(tenant_b.id)}

    # Verify Tenant A can see customer & order
    res_cust_a = await async_client.get("/api/v1/customers", headers=headers_a)
    assert res_cust_a.status_code == 200
    assert len(res_cust_a.json()) == 1
    assert res_cust_a.json()[0]["name"] == "Customer Alpha"

    res_order_a = await async_client.get("/api/v1/orders", headers=headers_a)
    assert res_order_a.status_code == 200
    assert len(res_order_a.json()) == 1
    assert res_order_a.json()[0]["id"] == str(order_a.id)

    # Verify Tenant B sees EMPTY customers and orders (Strict Tenant Isolation)
    res_cust_b = await async_client.get("/api/v1/customers", headers=headers_b)
    assert res_cust_b.status_code == 200
    assert len(res_cust_b.json()) == 0

    res_order_b = await async_client.get("/api/v1/orders", headers=headers_b)
    assert res_order_b.status_code == 200
    assert len(res_order_b.json()) == 0

    # Tenant B direct GET customer_a by ID returns 404
    res_get_cust_b = await async_client.get(f"/api/v1/customers/{customer_a.id}", headers=headers_b)
    assert res_get_cust_b.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_integration_connections_isolation(async_client: AsyncClient, test_session):
    from app.database.models.integrations import Integration, IntegrationConnection

    # Create Tenant A and Tenant B
    tenant_a = Tenant(name="Tenant Int Iso A", slug="tenant-int-iso-a", is_active=True)
    tenant_b = Tenant(name="Tenant Int Iso B", slug="tenant-int-iso-b", is_active=True)
    test_session.add_all([tenant_a, tenant_b])
    await test_session.commit()

    user_a = User(tenant_id=tenant_a.id, email="owner_int_a@test.com", password_hash="hash_a", is_active=True)
    user_b = User(tenant_id=tenant_b.id, email="owner_int_b@test.com", password_hash="hash_b", is_active=True)
    test_session.add_all([user_a, user_b])
    await test_session.commit()

    # Create Catalog Integration
    integration = Integration(
        integration_key="rest_api",
        provider_key="rest_api",
        display_name="REST API Connector",
        category="api",
        is_enabled=True,
    )
    test_session.add(integration)
    await test_session.commit()

    # Create Connection owned by Tenant A
    conn_a = IntegrationConnection(
        tenant_id=tenant_a.id,
        integration_id=integration.id,
        integration_key="rest_api",
        provider_key="rest_api",
        status="ACTIVE",
        auth_type="api_key",
    )
    test_session.add(conn_a)
    await test_session.commit()

    headers_a = {"X-Tenant-ID": str(tenant_a.id)}
    headers_b = {"X-Tenant-ID": str(tenant_b.id)}

    # 1. Tenant B calls GET /api/v1/integrations/connections -> Tenant A's connection is NOT in list
    token_b = set_actor_context(AuthenticatedActor(user_id=user_b.id, tenant_id=tenant_b.id, role="owner", permissions=set(ROLE_PERMISSIONS["owner"])))
    try:
        res_b = await async_client.get("/api/v1/integrations/connections", headers=headers_b)
        assert res_b.status_code == 200
        conns_b = res_b.json()
        assert not any(c["id"] == str(conn_a.id) for c in conns_b)

        # Tenant B attempts to disconnect Tenant A's connection -> HTTP 404 or 403
        res_disc_b = await async_client.post(f"/api/v1/integrations/connections/{conn_a.id}/disconnect", headers=headers_b)
        assert res_disc_b.status_code in (404, 403)

        # Explicit assertion: Verify response does NOT leak Tenant A sensitive data or connection metadata
        res_text = res_disc_b.text.lower()
        assert str(conn_a.id).lower() not in res_text
        assert str(tenant_a.id).lower() not in res_text
        assert "api_key" not in res_text
        assert "token" not in res_text
        assert "secret" not in res_text
        assert "password" not in res_text

        if res_disc_b.headers.get("content-type", "").startswith("application/json"):
            body = res_disc_b.json()
            assert isinstance(body, dict)
            # Ensure detail message does not expose tenant_a details or connection metadata
            detail_str = str(body.get("detail", "")).lower()
            assert str(conn_a.id).lower() not in detail_str
            assert str(tenant_a.id).lower() not in detail_str
    finally:
        reset_actor_context(token_b)

    # 2. Tenant A calls GET /api/v1/integrations/connections -> Sees its connection
    token_a = set_actor_context(AuthenticatedActor(user_id=user_a.id, tenant_id=tenant_a.id, role="owner", permissions=set(ROLE_PERMISSIONS["owner"])))
    try:
        res_a = await async_client.get("/api/v1/integrations/connections", headers=headers_a)
        assert res_a.status_code == 200
        conns_a = res_a.json()
        assert any(c["id"] == str(conn_a.id) for c in conns_a)
    finally:
        reset_actor_context(token_a)

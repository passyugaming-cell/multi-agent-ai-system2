import pytest
from decimal import Decimal
import uuid
from httpx import AsyncClient

from app.database.models import Tenant, Product, Customer, Conversation, Order
from app.repositories.domain import ProductRepository


@pytest.mark.asyncio
async def test_tenant_isolation_products(async_client: AsyncClient, test_session):
    # 1. Create Tenant A and Tenant B
    tenant_a = Tenant(name="Tenant A", slug="tenant-a-iso", is_active=True)
    tenant_b = Tenant(name="Tenant B", slug="tenant-b-iso", is_active=True)
    test_session.add_all([tenant_a, tenant_b])
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

    headers_a = {"X-Tenant-ID": str(tenant_a.id), "X-Actor-Permissions": "product.read,product.write"}
    headers_b = {"X-Tenant-ID": str(tenant_b.id), "X-Actor-Permissions": "product.read,product.write"}

    # 3. Tenant A can read product_a
    res_a = await async_client.get(f"/api/v1/products/{product_a.id}", headers=headers_a)
    assert res_a.status_code == 200
    assert res_a.json()["name"] == "Tenant A Product"

    # 4. Tenant B CANNOT read product_a
    res_b = await async_client.get(f"/api/v1/products/{product_a.id}", headers=headers_b)
    assert res_b.status_code == 404

    # 5. Tenant B listing products returns empty
    res_b_list = await async_client.get("/api/v1/products", headers=headers_b)
    assert res_b_list.status_code == 200
    assert len(res_b_list.json()) == 0


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

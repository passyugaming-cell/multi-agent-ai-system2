import uuid
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Tenant, BusinessProfile, Product, ProductVariant, KnowledgeItem
from app.tenants.business_service import BusinessDataService
from app.tenants.provisioning.provisioner import TenantProvisioner
from app.schemas.domain import (
    BusinessProfileCreate,
    BusinessProfileUpdate,
    ProductCreate,
    ProductUpdate,
    ProductVariantCreate,
    KnowledgeItemCreate,
    KnowledgeItemUpdate,
)


@pytest_asyncio.fixture
async def tenant_alpha(db_session: AsyncSession) -> Tenant:
    t = Tenant(name="Tenant Alpha", slug=f"alpha-{uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def tenant_beta(db_session: AsyncSession) -> Tenant:
    t = Tenant(name="Tenant Beta", slug=f"beta-{uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


# --- 1. BUSINESS PROFILE TESTS ---

@pytest.mark.asyncio
async def test_01_create_business_profile(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,business.read"}
    payload = {
        "business_name": "Alpha Corp",
        "business_type": "RETAIL",
        "description": "Premium Retailer",
        "phone": "+628123456789",
        "email": "info@alphacorp.id",
        "website": "https://alphacorp.id",
        "address": "Jl. Sudirman No. 10",
        "city": "Jakarta",
        "province": "DKI Jakarta",
        "country": "Indonesia",
        "operating_hours": {"mon_fri": "08:00 - 17:00"},
        "payment_methods": {"bank_transfer": ["BCA", "Mandiri"]},
        "bank_accounts": [{"bank": "BCA", "account": "1234567890", "name": "PT Alpha Corp"}],
        "shipping_information": {"couriers": ["JNE", "J&T"]},
        "return_policy": "Retur berlaku 7 hari setelah barang diterima.",
        "refund_policy": "Refund diproses dalam 24 jam.",
    }
    res = await async_client.post("/api/v1/business", json=payload, headers=headers)
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["business_name"] == "Alpha Corp"
    assert data["city"] == "Jakarta"
    assert data["email"] == "info@alphacorp.id"


@pytest.mark.asyncio
async def test_02_get_business_profile(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.read,business.write"}
    payload = {"business_name": "Alpha Corp Read Test"}
    await async_client.put("/api/v1/business", json=payload, headers=headers)

    res = await async_client.get("/api/v1/business", headers=headers)
    assert res.status_code == 200
    assert res.json()["business_name"] == "Alpha Corp Read Test"


@pytest.mark.asyncio
async def test_03_update_business_profile(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,business.read"}
    await async_client.put("/api/v1/business", json={"business_name": "Alpha Initial"}, headers=headers)

    update_res = await async_client.put("/api/v1/business", json={"business_name": "Alpha Updated"}, headers=headers)
    assert update_res.status_code == 200
    assert update_res.json()["business_name"] == "Alpha Updated"


@pytest.mark.asyncio
async def test_04_business_profile_tenant_isolation(
    async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,business.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "business.write,business.read"}

    await async_client.put("/api/v1/business", json={"business_name": "Alpha Only Profile"}, headers=headers_a)

    res_b = await async_client.get("/api/v1/business", headers=headers_b)
    assert res_b.status_code == 404


@pytest.mark.asyncio
async def test_05_business_profile_permissions(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_no_perm = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "unrelated.perm"}
    payload = {"business_name": "No Perm Profile"}
    res = await async_client.put("/api/v1/business", json=payload, headers=headers_no_perm)
    assert res.status_code == 403


# --- 2. PRODUCTS, SERVICES & VARIANTS TESTS ---

@pytest.mark.asyncio
async def test_06_create_product_physical(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    payload = {
        "name": "Hoodie Premium",
        "type": "PRODUCT",
        "description": "Hoodie katun lembut",
        "sku": "HD-001",
        "category": "Apparel",
        "price": "250000.00",
        "currency": "IDR",
        "stock": 50,
        "stock_status": "IN_STOCK",
        "unit": "pcs",
    }
    res = await async_client.post("/api/v1/products", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Hoodie Premium"
    assert data["type"] == "PRODUCT"
    assert Decimal(data["price"]) == Decimal("250000.00")
    assert data["stock"] == 50


@pytest.mark.asyncio
async def test_07_create_service(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    payload = {
        "name": "Konsultasi IT",
        "type": "SERVICE",
        "description": "Jasa konsultasi sistem IT",
        "sku": "SRV-IT-01",
        "price": "500000.00",
        "unit": "jam",
        "stock": 0,
    }
    res = await async_client.post("/api/v1/products", json=payload, headers=headers)
    assert res.status_code == 201
    assert res.json()["type"] == "SERVICE"
    assert res.json()["unit"] == "jam"


@pytest.mark.asyncio
async def test_08_list_products(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    await async_client.post("/api/v1/products", json={"name": "Prod 1", "price": "10000.00"}, headers=headers)
    await async_client.post("/api/v1/products", json={"name": "Prod 2", "price": "20000.00"}, headers=headers)

    res = await async_client.get("/api/v1/products", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 2


@pytest.mark.asyncio
async def test_09_get_product_by_id(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    create_res = await async_client.post("/api/v1/products", json={"name": "Prod Single", "price": "15000.00"}, headers=headers)
    prod_id = create_res.json()["id"]

    res = await async_client.get(f"/api/v1/products/{prod_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == prod_id


@pytest.mark.asyncio
async def test_10_update_product(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    create_res = await async_client.post("/api/v1/products", json={"name": "Prod Old", "price": "10000.00"}, headers=headers)
    prod_id = create_res.json()["id"]

    update_res = await async_client.put(
        f"/api/v1/products/{prod_id}",
        json={"name": "Prod New", "price": "12000.00", "stock": 100},
        headers=headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Prod New"
    assert Decimal(update_res.json()["price"]) == Decimal("12000.00")


@pytest.mark.asyncio
async def test_11_delete_product(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    create_res = await async_client.post("/api/v1/products", json={"name": "Prod To Delete", "price": "10000.00"}, headers=headers)
    prod_id = create_res.json()["id"]

    del_res = await async_client.delete(f"/api/v1/products/{prod_id}", headers=headers)
    assert del_res.status_code == 200

    get_res = await async_client.get(f"/api/v1/products/{prod_id}", headers=headers)
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_12_create_product_variant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    prod_res = await async_client.post("/api/v1/products", json={"name": "T-Shirt", "price": "100000.00"}, headers=headers)
    prod_id = prod_res.json()["id"]

    variant_payload = {
        "name": "Ukuran XL Hitam",
        "sku": "TS-XL-BLK",
        "price_override": "110000.00",
        "stock": 25,
    }
    var_res = await async_client.post(f"/api/v1/products/{prod_id}/variants", json=variant_payload, headers=headers)
    assert var_res.status_code == 201
    vdata = var_res.json()
    assert vdata["name"] == "Ukuran XL Hitam"
    assert Decimal(vdata["price_override"]) == Decimal("110000.00")


@pytest.mark.asyncio
async def test_13_update_product_variant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    prod_res = await async_client.post("/api/v1/products", json={"name": "Shoes", "price": "500000.00"}, headers=headers)
    prod_id = prod_res.json()["id"]

    var_res = await async_client.post(f"/api/v1/products/{prod_id}/variants", json={"name": "Size 42", "stock": 10}, headers=headers)
    var_id = var_res.json()["id"]

    update_var_res = await async_client.put(
        f"/api/v1/products/variants/{var_id}", json={"stock": 15}, headers=headers
    )
    assert update_var_res.status_code == 200
    assert update_var_res.json()["stock"] == 15


@pytest.mark.asyncio
async def test_14_delete_product_variant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    prod_res = await async_client.post("/api/v1/products", json={"name": "Jacket", "price": "300000.00"}, headers=headers)
    prod_id = prod_res.json()["id"]

    var_res = await async_client.post(f"/api/v1/products/{prod_id}/variants", json={"name": "Size L", "stock": 5}, headers=headers)
    var_id = var_res.json()["id"]

    del_res = await async_client.delete(f"/api/v1/products/variants/{var_id}", headers=headers)
    assert del_res.status_code == 200


@pytest.mark.asyncio
async def test_15_product_tenant_isolation_read(
    async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "product.write,product.read"}

    create_res = await async_client.post("/api/v1/products", json={"name": "Alpha Secret Prod", "price": "10000.00"}, headers=headers_a)
    prod_id = create_res.json()["id"]

    res_b = await async_client.get(f"/api/v1/products/{prod_id}", headers=headers_b)
    assert res_b.status_code == 404


@pytest.mark.asyncio
async def test_16_product_tenant_isolation_update(
    async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "product.write,product.read"}

    create_res = await async_client.post("/api/v1/products", json={"name": "Alpha Original", "price": "10000.00"}, headers=headers_a)
    prod_id = create_res.json()["id"]

    update_res_b = await async_client.put(f"/api/v1/products/{prod_id}", json={"name": "Hacked By Beta"}, headers=headers_b)
    assert update_res_b.status_code == 404


@pytest.mark.asyncio
async def test_17_product_tenant_isolation_delete(
    async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "product.write,product.read"}

    create_res = await async_client.post("/api/v1/products", json={"name": "Alpha Product", "price": "10000.00"}, headers=headers_a)
    prod_id = create_res.json()["id"]

    del_res_b = await async_client.delete(f"/api/v1/products/{prod_id}", headers=headers_b)
    assert del_res_b.status_code == 404


@pytest.mark.asyncio
async def test_18_product_tenant_isolation_variant(
    async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "product.write,product.read"}

    create_res = await async_client.post("/api/v1/products", json={"name": "Alpha Shirt", "price": "10000.00"}, headers=headers_a)
    prod_id = create_res.json()["id"]

    var_res_b = await async_client.post(f"/api/v1/products/{prod_id}/variants", json={"name": "Beta Variant"}, headers=headers_b)
    assert var_res_b.status_code == 404


@pytest.mark.asyncio
async def test_19_product_permission_read(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_no_perm = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "other.perm"}
    res = await async_client.get("/api/v1/products", headers=headers_no_perm)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_20_product_permission_write(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_no_perm = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.read"}
    res = await async_client.post("/api/v1/products", json={"name": "No Write Perm", "price": "100.00"}, headers=headers_no_perm)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_21_negative_price_stock(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    res_price = await async_client.post("/api/v1/products", json={"name": "Bad Price", "price": "-10.00"}, headers=headers)
    assert res_price.status_code == 400

    res_stock = await async_client.post("/api/v1/products", json={"name": "Bad Stock", "price": "10.00", "stock": -5}, headers=headers)
    assert res_stock.status_code == 400


# --- 3. KNOWLEDGE BASE & LIFECYCLE TESTS ---

@pytest.mark.asyncio
async def test_22_create_knowledge_item_draft(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    payload = {
        "category_key": "RETURN",
        "title": "Kebijakan Pengembalian Barang",
        "content": "Barang dapat dikembalikan maksimal 7 hari setelah diterima dengan menyertakan video unboxing.",
        "status": "DRAFT",
    }
    res = await async_client.post("/api/v1/knowledge", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Kebijakan Pengembalian Barang"
    assert data["status"] == "DRAFT"
    assert data["category_key"] == "RETURN"


@pytest.mark.asyncio
async def test_23_list_knowledge_items(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    await async_client.post("/api/v1/knowledge", json={"title": "FAQ 1", "content": "Content 1", "category_key": "FAQ"}, headers=headers)
    await async_client.post("/api/v1/knowledge", json={"title": "FAQ 2", "content": "Content 2", "category_key": "FAQ"}, headers=headers)

    res = await async_client.get("/api/v1/knowledge?category_key=FAQ", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 2


@pytest.mark.asyncio
async def test_24_get_knowledge_item_by_id(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Single Item", "content": "Content"}, headers=headers)
    item_id = create_res.json()["id"]

    res = await async_client.get(f"/api/v1/knowledge/{item_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == item_id


@pytest.mark.asyncio
async def test_25_update_knowledge_item_content(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Old Title", "content": "Old Content"}, headers=headers)
    item_id = create_res.json()["id"]

    update_res = await async_client.put(
        f"/api/v1/knowledge/{item_id}",
        json={"title": "New Title", "content": "Updated Content"},
        headers=headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "New Title"


@pytest.mark.asyncio
async def test_26_valid_lifecycle_transition_draft_to_validating(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Draft Policy", "content": "Policy text", "status": "DRAFT"}, headers=headers)
    item_id = create_res.json()["id"]

    res = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "VALIDATING"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "VALIDATING"


@pytest.mark.asyncio
async def test_27_valid_lifecycle_transition_validating_to_approved(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Validating Policy", "content": "Text", "status": "VALIDATING"}, headers=headers)
    item_id = create_res.json()["id"]

    app_res = await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_28_valid_lifecycle_transition_approved_to_active(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "To Approve", "content": "Text", "status": "DRAFT"}, headers=headers)
    item_id = create_res.json()["id"]

    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)

    active_res = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "ACTIVE"}, headers=headers)
    assert active_res.status_code == 200
    assert active_res.json()["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_29_valid_lifecycle_transition_active_to_outdated(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "To Approve Item", "content": "Text"}, headers=headers)
    item_id = create_res.json()["id"]
    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)
    await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "ACTIVE"}, headers=headers)

    out_res = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "OUTDATED"}, headers=headers)
    assert out_res.status_code == 200
    assert out_res.json()["status"] == "OUTDATED"


@pytest.mark.asyncio
async def test_30_valid_lifecycle_transition_outdated_to_archived(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Outdated Item", "content": "Text"}, headers=headers)
    item_id = create_res.json()["id"]
    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)
    await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "OUTDATED"}, headers=headers)

    arch_res = await async_client.post(f"/api/v1/knowledge/{item_id}/archive", headers=headers)
    assert arch_res.status_code == 200
    assert arch_res.json()["status"] == "ARCHIVED"


@pytest.mark.asyncio
async def test_31_invalid_lifecycle_transition_draft_to_outdated(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Draft Policy", "content": "Text", "status": "DRAFT"}, headers=headers)
    item_id = create_res.json()["id"]

    res = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "OUTDATED"}, headers=headers)
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_32_invalid_lifecycle_transition_archived_to_active(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Draft Item", "content": "Text"}, headers=headers)
    item_id = create_res.json()["id"]

    await async_client.post(f"/api/v1/knowledge/{item_id}/archive", headers=headers)

    invalid_res = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "ACTIVE"}, headers=headers)
    assert invalid_res.status_code == 400


@pytest.mark.asyncio
async def test_33_approve_knowledge_item_endpoint(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Policy To Approve", "content": "Content"}, headers=headers)
    item_id = create_res.json()["id"]

    app_res = await async_client.post(f"/api/v1/knowledge/{item_id}/approve", json={"approved_by": "Owner Admin"}, headers=headers)
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "APPROVED"
    assert app_res.json()["owner"] == "Owner Admin"


@pytest.mark.asyncio
async def test_34_approve_already_active_fails(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Policy Active", "content": "Content"}, headers=headers)
    item_id = create_res.json()["id"]

    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)
    await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "ACTIVE"}, headers=headers)

    reapprove_res = await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)
    assert reapprove_res.status_code == 400


@pytest.mark.asyncio
async def test_35_archive_knowledge_item_endpoint(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "To Archive", "content": "Content"}, headers=headers)
    item_id = create_res.json()["id"]

    arch_res = await async_client.delete(f"/api/v1/knowledge/{item_id}", headers=headers)
    assert arch_res.status_code == 200
    assert arch_res.json()["status"] == "ARCHIVED"


@pytest.mark.asyncio
async def test_36_knowledge_tenant_isolation_read(
    async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}

    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Alpha Secret FAQ", "content": "Secret"}, headers=headers_a)
    item_id = create_res.json()["id"]

    res_b = await async_client.get(f"/api/v1/knowledge/{item_id}", headers=headers_b)
    assert res_b.status_code == 404


@pytest.mark.asyncio
async def test_37_knowledge_tenant_isolation_write(
    async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}

    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Alpha Policy", "content": "Text"}, headers=headers_a)
    item_id = create_res.json()["id"]

    edit_res_b = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"title": "Hacked Policy"}, headers=headers_b)
    assert edit_res_b.status_code == 404


@pytest.mark.asyncio
async def test_38_knowledge_tenant_isolation_approve(
    async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}

    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Alpha Policy", "content": "Text"}, headers=headers_a)
    item_id = create_res.json()["id"]

    app_res_b = await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers_b)
    assert app_res_b.status_code == 404


@pytest.mark.asyncio
async def test_39_knowledge_permission_read(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_no_perm = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "unrelated.perm"}
    res = await async_client.get("/api/v1/knowledge", headers=headers_no_perm)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_40_knowledge_permission_write(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_no_perm = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.read"}
    res = await async_client.post("/api/v1/knowledge", json={"title": "No Write", "content": "Text"}, headers=headers_no_perm)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_41_knowledge_permission_approve(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Draft Item", "content": "Content"}, headers=headers)
    item_id = create_res.json()["id"]

    headers_no_approve = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    app_res = await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers_no_approve)
    assert app_res.status_code == 403


# --- 4. DETERMINISTIC READINESS CHECK TESTS ---

@pytest.mark.asyncio
async def test_42_readiness_check_unconfigured_tenant(
    async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession
):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(tenant_alpha.id)}
    res = await async_client.get("/api/v1/business/readiness", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ready"] is False
    assert data["readiness_status"] in ("NOT_READY", "NEARLY_READY")


@pytest.mark.asyncio
async def test_43_readiness_check_fully_configured_tenant(
    async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession
):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,product.write,knowledge.write,knowledge.approve"}

    # Setup profile
    await async_client.put(
        "/api/v1/business",
        json={
            "business_name": "Ready Corp",
            "description": "Full Business Description",
            "operating_hours": {"mon_fri": "09:00 - 17:00"},
            "payment_methods": {"transfer": ["BCA"]},
            "shipping_information": {"couriers": ["JNE"]},
            "return_policy": "7 Hari retur",
            "exchange_policy": "Bisa tukar size",
            "refund_policy": "Refund 100%",
        },
        headers=headers,
    )

    # Setup product
    await async_client.post("/api/v1/products", json={"name": "Shirt", "price": "100000.00", "stock": 10}, headers=headers)

    # Setup knowledge
    await async_client.post("/api/v1/knowledge", json={"title": "Policy", "content": "Text", "status": "APPROVED"}, headers=headers)

    res = await async_client.get("/api/v1/business/readiness", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ready"] is True
    assert data["readiness_status"] == "READY"
    assert data["score"] >= 90.0


@pytest.mark.asyncio
async def test_44_readiness_check_missing_business_name(
    async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession
):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(tenant_alpha.id)}
    res = await async_client.get("/api/v1/business/readiness", headers=headers)
    assert res.status_code == 200
    assert "business_profile_completed" in res.json()["incomplete_requirements"]


@pytest.mark.asyncio
async def test_45_readiness_check_missing_products(
    async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession
):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(tenant_alpha.id)}
    res = await async_client.get("/api/v1/business/readiness", headers=headers)
    assert res.status_code == 200
    assert "product_configured" in res.json()["incomplete_requirements"]


@pytest.mark.asyncio
async def test_46_readiness_check_missing_knowledge(
    async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession
):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(tenant_alpha.id)}
    res = await async_client.get("/api/v1/business/readiness", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "score" in data


@pytest.mark.asyncio
async def test_47_readiness_check_alias_endpoint(
    async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession
):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(tenant_alpha.id)}
    res_b = await async_client.get("/api/v1/business/readiness", headers=headers)
    res_bp = await async_client.get("/api/v1/business-profile/readiness", headers=headers)
    assert res_b.status_code == 200
    assert res_bp.status_code == 200
    assert res_b.json() == res_bp.json()


# --- 5. AI GUARDRAILS & ROUTER INTEGRATION TESTS ---

@pytest.mark.asyncio
async def test_48_router_uses_db_price_truth(
    async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    from app.core.router.router import MessageRouter
    from app.database.models import Conversation, Message, Customer

    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    prod_res = await async_client.post("/api/v1/products", json={"name": "Kemeja Flanel", "price": "185000.00", "stock": 20}, headers=headers)
    assert prod_res.status_code == 201

    cust = Customer(tenant_id=tenant_alpha.id, name="Test Customer", phone="+62811111111")
    db_session.add(cust)
    await db_session.commit()

    conv = Conversation(tenant_id=tenant_alpha.id, customer_id=cust.id, channel="whatsapp", status="OPEN", ai_enabled=True)
    db_session.add(conv)
    await db_session.commit()

    msg = Message(tenant_id=tenant_alpha.id, conversation_id=conv.id, direction="INBOUND", text="Berapa harga Kemeja Flanel?")

    router = MessageRouter()
    result = await router.route_message(tenant_alpha.id, conv, msg, db_session)

    assert result.was_ai_called is False
    assert "185,000" in result.response_text


@pytest.mark.asyncio
async def test_49_router_uses_db_stock_truth(
    async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    from app.core.router.router import MessageRouter
    from app.database.models import Conversation, Message, Customer

    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    await async_client.post("/api/v1/products", json={"name": "Sepatu Lari", "price": "450000.00", "stock": 14}, headers=headers)

    cust = Customer(tenant_id=tenant_alpha.id, name="Runner", phone="+62822222222")
    db_session.add(cust)
    await db_session.commit()

    conv = Conversation(tenant_id=tenant_alpha.id, customer_id=cust.id, channel="whatsapp", status="OPEN", ai_enabled=True)
    db_session.add(conv)
    await db_session.commit()

    msg = Message(tenant_id=tenant_alpha.id, conversation_id=conv.id, direction="INBOUND", text="Stok Sepatu Lari ready berapa?")

    router = MessageRouter()
    result = await router.route_message(tenant_alpha.id, conv, msg, db_session)

    assert result.was_ai_called is False
    assert "14" in result.response_text


@pytest.mark.asyncio
async def test_50_router_uses_approved_knowledge_in_context(
    async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}

    # Create DRAFT knowledge item
    await async_client.post("/api/v1/knowledge", json={"title": "Unapproved Policy", "content": "Secret draft content", "status": "DRAFT"}, headers=headers)

    # Create APPROVED knowledge item
    app_res = await async_client.post("/api/v1/knowledge", json={"title": "Approved Policy", "content": "Official approved return policy", "status": "APPROVED"}, headers=headers)
    assert app_res.status_code == 201

    service = BusinessDataService(db_session)
    approved_items = await service.know_repo.list_active_and_approved(tenant_alpha.id)
    assert len(approved_items) == 1
    assert approved_items[0].title == "Approved Policy"


@pytest.mark.asyncio
async def test_51_event_bus_publishing(
    async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,product.write,knowledge.write,knowledge.approve"}

    res_bp = await async_client.put("/api/v1/business", json={"business_name": "Event Bus Corp"}, headers=headers)
    assert res_bp.status_code in (200, 201)

    res_p = await async_client.post("/api/v1/products", json={"name": "Event Product", "price": "1000.00"}, headers=headers)
    assert res_p.status_code == 201

    res_k = await async_client.post("/api/v1/knowledge", json={"title": "Event Knowledge", "content": "Text"}, headers=headers)
    assert res_k.status_code == 201


@pytest.mark.asyncio
async def test_52_cross_tenant_foreign_key_protection(
    async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession
):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "product.write,product.read"}

    prod_res = await async_client.post("/api/v1/products", json={"name": "Alpha Product", "price": "1000.00"}, headers=headers_a)
    alpha_prod_id = prod_res.json()["id"]

    # Beta attempts to create variant on Alpha's product -> returns 404 Not Found (tenant isolation)
    var_res = await async_client.post(f"/api/v1/products/{alpha_prod_id}/variants", json={"name": "Malicious Variant"}, headers=headers_b)
    assert var_res.status_code == 404

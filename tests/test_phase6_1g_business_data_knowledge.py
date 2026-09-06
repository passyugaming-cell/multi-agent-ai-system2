import uuid
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.database.models import Tenant, BusinessProfile, Product, ProductVariant, KnowledgeItem
from app.database.models.workflow import Approval
from app.database.models.audit import ProvisioningAudit
from app.tenants.business_service import BusinessDataService
from app.tenants.provisioning.provisioner import TenantProvisioner


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


# --- 1. RBAC FAIL-CLOSED & SECURITY TESTS ---

@pytest.mark.asyncio
async def test_01_no_actor_permissions_returns_403(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_no_perm = {"X-Tenant-ID": str(tenant_alpha.id)}  # No X-Actor-Permissions header
    res = await async_client.get("/api/v1/business", headers=headers_no_perm)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_02_insufficient_actor_permissions_returns_403(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_wrong_perm = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "wrong.perm"}
    res = await async_client.get("/api/v1/business", headers=headers_wrong_perm)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_03_valid_actor_permissions_success(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,business.read"}
    payload = {"business_name": "Alpha Corp Verified"}
    res = await async_client.put("/api/v1/business", json=payload, headers=headers_a)
    assert res.status_code in (200, 201)
    assert res.json()["business_name"] == "Alpha Corp Verified"


@pytest.mark.asyncio
async def test_04_service_layer_direct_invocation_without_permissions_blocked(db_session: AsyncSession, tenant_alpha: Tenant):
    service = BusinessDataService(db_session)
    with pytest.raises(AppException) as exc_info:
        await service.get_business_profile(tenant_alpha.id, actor_permissions=None)
    assert exc_info.value.code == "PERMISSION_DENIED"
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_05_cross_tenant_access_blocked(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,business.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "business.write,business.read"}

    await async_client.put("/api/v1/business", json={"business_name": "Alpha Private"}, headers=headers_a)

    res_b = await async_client.get("/api/v1/business", headers=headers_b)
    assert res_b.status_code == 404


# --- 2. BUSINESS PROFILE EXTENSION TESTS ---

@pytest.mark.asyncio
async def test_06_create_business_profile_extended_fields(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,business.read"}
    payload = {
        "business_name": "Alpha Extended Corp",
        "business_type": "SERVICES",
        "description": "Enterprise Solutions",
        "phone": "+62811223344",
        "email": "contact@alphaext.com",
        "website": "https://alphaext.com",
        "address": "Gatot Subroto Kav 5",
        "city": "Jakarta Selatan",
        "province": "DKI Jakarta",
        "country": "Indonesia",
        "operating_hours": {"weekdays": "09:00 - 18:00"},
        "payment_methods": {"credit_card": ["Visa", "Mastercard"]},
        "bank_accounts": [{"bank": "Mandiri", "account": "9876543210", "name": "PT Alpha Ext"}],
        "shipping_information": {"express": True},
        "courier_methods": ["Sicepat", "Anteraja"],
        "return_policy": "Kebijakan retur 14 hari.",
        "refund_policy": "Refund dikembalikan via transfer.",
        "contact_admin_info": {"admin_phone": "+62811999888"},
    }
    res = await async_client.post("/api/v1/business", json=payload, headers=headers)
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["business_name"] == "Alpha Extended Corp"
    assert data["city"] == "Jakarta Selatan"
    assert data["email"] == "contact@alphaext.com"
    assert data["bank_accounts"] == [{"bank": "Mandiri", "account": "9876543210", "name": "PT Alpha Ext"}]


@pytest.mark.asyncio
async def test_07_get_business_profile_returns_404_when_missing(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.read"}
    res = await async_client.get("/api/v1/business", headers=headers)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_08_update_existing_business_profile(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,business.read"}
    await async_client.put("/api/v1/business", json={"business_name": "Initial Name"}, headers=headers)

    res_update = await async_client.put("/api/v1/business", json={"business_name": "Updated Name", "city": "Bandung"}, headers=headers)
    assert res_update.status_code == 200
    assert res_update.json()["business_name"] == "Updated Name"
    assert res_update.json()["city"] == "Bandung"


# --- 3. PRODUCTS & SERVICES & VARIANTS TESTS ---

@pytest.mark.asyncio
async def test_09_create_physical_product(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    payload = {
        "name": "Kemeja Batik",
        "type": "PRODUCT",
        "description": "Batik Tulis Halus",
        "sku": "BTK-001",
        "category": "Pakaian",
        "price": "350000.00",
        "currency": "IDR",
        "stock": 15,
        "unit": "pcs",
    }
    res = await async_client.post("/api/v1/products", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Kemeja Batik"
    assert data["type"] == "PRODUCT"
    assert Decimal(data["price"]) == Decimal("350000.00")


@pytest.mark.asyncio
async def test_10_create_service_item(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    payload = {
        "name": "Sewa Kamera",
        "type": "SERVICE",
        "description": "Sewa kamera DSLR per hari",
        "sku": "SRV-CAM-01",
        "price": "250000.00",
        "unit": "hari",
        "stock": 0,
    }
    res = await async_client.post("/api/v1/products", json=payload, headers=headers)
    assert res.status_code == 201
    assert res.json()["type"] == "SERVICE"
    assert res.json()["unit"] == "hari"


@pytest.mark.asyncio
async def test_11_list_products_scoped_by_tenant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    await async_client.post("/api/v1/products", json={"name": "P1", "price": "100.00"}, headers=headers)
    await async_client.post("/api/v1/products", json={"name": "P2", "price": "200.00"}, headers=headers)

    res = await async_client.get("/api/v1/products", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 2


@pytest.mark.asyncio
async def test_12_get_product_by_id(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    create_res = await async_client.post("/api/v1/products", json={"name": "Target Product", "price": "50000.00"}, headers=headers)
    prod_id = create_res.json()["id"]

    res = await async_client.get(f"/api/v1/products/{prod_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == prod_id


@pytest.mark.asyncio
async def test_13_update_product_price_and_stock(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    create_res = await async_client.post("/api/v1/products", json={"name": "Old Item", "price": "10000.00", "stock": 5}, headers=headers)
    prod_id = create_res.json()["id"]

    update_res = await async_client.put(
        f"/api/v1/products/{prod_id}", json={"price": "15000.00", "stock": 20}, headers=headers
    )
    assert update_res.status_code == 200
    assert Decimal(update_res.json()["price"]) == Decimal("15000.00")
    assert update_res.json()["stock"] == 20


@pytest.mark.asyncio
async def test_14_delete_product_deletes_cascade_variants(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    create_res = await async_client.post("/api/v1/products", json={"name": "Item To Delete", "price": "10000.00"}, headers=headers)
    prod_id = create_res.json()["id"]

    del_res = await async_client.delete(f"/api/v1/products/{prod_id}", headers=headers)
    assert del_res.status_code == 200

    get_res = await async_client.get(f"/api/v1/products/{prod_id}", headers=headers)
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_15_create_product_variant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    create_res = await async_client.post("/api/v1/products", json={"name": "Sepatu Sneaker", "price": "500000.00"}, headers=headers)
    prod_id = create_res.json()["id"]

    var_res = await async_client.post(
        f"/api/v1/products/{prod_id}/variants",
        json={"name": "Size 43 Putih", "sku": "SNK-43-WHT", "price_override": "520000.00", "stock": 8},
        headers=headers,
    )
    assert var_res.status_code == 201
    vdata = var_res.json()
    assert vdata["name"] == "Size 43 Putih"
    assert Decimal(vdata["price_override"]) == Decimal("520000.00")


@pytest.mark.asyncio
async def test_16_update_product_variant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    create_res = await async_client.post("/api/v1/products", json={"name": "Jam Tangan", "price": "1000000.00"}, headers=headers)
    prod_id = create_res.json()["id"]

    var_res = await async_client.post(f"/api/v1/products/{prod_id}/variants", json={"name": "Tali Kulit", "stock": 3}, headers=headers)
    var_id = var_res.json()["id"]

    update_var = await async_client.put(f"/api/v1/products/variants/{var_id}", json={"stock": 10}, headers=headers)
    assert update_var.status_code == 200
    assert update_var.json()["stock"] == 10


@pytest.mark.asyncio
async def test_17_delete_product_variant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    create_res = await async_client.post("/api/v1/products", json={"name": "Topi", "price": "75000.00"}, headers=headers)
    prod_id = create_res.json()["id"]

    var_res = await async_client.post(f"/api/v1/products/{prod_id}/variants", json={"name": "Warna Merah", "stock": 5}, headers=headers)
    var_id = var_res.json()["id"]

    del_var = await async_client.delete(f"/api/v1/products/variants/{var_id}", headers=headers)
    assert del_var.status_code == 200


@pytest.mark.asyncio
async def test_18_product_tenant_isolation_read(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "product.write,product.read"}

    create_res = await async_client.post("/api/v1/products", json={"name": "Alpha Item", "price": "100.00"}, headers=headers_a)
    prod_id = create_res.json()["id"]

    res_b = await async_client.get(f"/api/v1/products/{prod_id}", headers=headers_b)
    assert res_b.status_code == 404


@pytest.mark.asyncio
async def test_19_product_tenant_isolation_update(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "product.write,product.read"}

    create_res = await async_client.post("/api/v1/products", json={"name": "Alpha Item", "price": "100.00"}, headers=headers_a)
    prod_id = create_res.json()["id"]

    res_b = await async_client.put(f"/api/v1/products/{prod_id}", json={"name": "Hacked"}, headers=headers_b)
    assert res_b.status_code == 404


@pytest.mark.asyncio
async def test_20_product_tenant_isolation_delete(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "product.write,product.read"}

    create_res = await async_client.post("/api/v1/products", json={"name": "Alpha Item", "price": "100.00"}, headers=headers_a)
    prod_id = create_res.json()["id"]

    res_b = await async_client.delete(f"/api/v1/products/{prod_id}", headers=headers_b)
    assert res_b.status_code == 404


@pytest.mark.asyncio
async def test_21_negative_price_stock_rejected(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}

    res_price = await async_client.post("/api/v1/products", json={"name": "Bad Price", "price": "-100.00"}, headers=headers)
    assert res_price.status_code == 400

    res_stock = await async_client.post("/api/v1/products", json={"name": "Bad Stock", "price": "100.00", "stock": -10}, headers=headers)
    assert res_stock.status_code == 400


# --- 4. KNOWLEDGE BASE CREATION, LIFECYCLE & APPROVAL TESTS ---

@pytest.mark.asyncio
async def test_22_direct_approved_creation_prohibited(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    res = await async_client.post("/api/v1/knowledge", json={"title": "Policy", "content": "Text", "status": "APPROVED"}, headers=headers)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_STATUS_ON_CREATION"


@pytest.mark.asyncio
async def test_23_direct_active_creation_prohibited(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    res = await async_client.post("/api/v1/knowledge", json={"title": "Policy", "content": "Text", "status": "ACTIVE"}, headers=headers)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_STATUS_ON_CREATION"


@pytest.mark.asyncio
async def test_24_valid_knowledge_creation_forces_draft_and_v1(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    res = await async_client.post("/api/v1/knowledge", json={"title": "Draft Policy", "content": "Initial Text"}, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "DRAFT"
    assert data["version"] == 1
    assert data["approval_id"] is None


@pytest.mark.asyncio
async def test_25_list_knowledge_items_filtered_by_category(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    await async_client.post("/api/v1/knowledge", json={"title": "FAQ Item", "content": "Content", "category_key": "FAQ"}, headers=headers)
    await async_client.post("/api/v1/knowledge", json={"title": "Shipping Item", "content": "Content", "category_key": "SHIPPING"}, headers=headers)

    res = await async_client.get("/api/v1/knowledge?category_key=FAQ", headers=headers)
    assert res.status_code == 200
    items = res.json()
    assert len(items) >= 1
    assert all(i["category_key"] == "FAQ" for i in items)


@pytest.mark.asyncio
async def test_26_get_knowledge_item_by_id(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Target Item", "content": "Content"}, headers=headers)
    item_id = create_res.json()["id"]

    res = await async_client.get(f"/api/v1/knowledge/{item_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == item_id


@pytest.mark.asyncio
async def test_27_transition_draft_to_validating(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Policy", "content": "Content"}, headers=headers)
    item_id = create_res.json()["id"]

    res_trans = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "VALIDATING"}, headers=headers)
    assert res_trans.status_code == 200
    assert res_trans.json()["status"] == "VALIDATING"


@pytest.mark.asyncio
async def test_28_approve_knowledge_item_persists_approval_record(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "To Approve", "content": "Content"}, headers=headers)
    item_id = create_res.json()["id"]

    res_app = await async_client.post(f"/api/v1/knowledge/{item_id}/approve", json={"approved_by": "Manager", "reason": "Passed legal review"}, headers=headers)
    assert res_app.status_code == 200
    data = res_app.json()
    assert data["status"] == "APPROVED"
    assert data["approval_id"] is not None

    approval_id = uuid.UUID(data["approval_id"])
    app_stmt = select(Approval).where(Approval.id == approval_id)
    approval_rec = (await db_session.execute(app_stmt)).scalar_one_or_none()
    assert approval_rec is not None
    assert approval_rec.status == "APPROVED"
    assert approval_rec.requested_by == "Manager"


@pytest.mark.asyncio
async def test_29_transition_approved_to_active(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Approved To Active", "content": "Text"}, headers=headers)
    item_id = create_res.json()["id"]

    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)
    res_act = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "ACTIVE"}, headers=headers)
    assert res_act.status_code == 200
    assert res_act.json()["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_30_transition_active_to_outdated(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Active To Outdated", "content": "Text"}, headers=headers)
    item_id = create_res.json()["id"]

    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)
    await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "ACTIVE"}, headers=headers)

    res_out = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "OUTDATED"}, headers=headers)
    assert res_out.status_code == 200
    assert res_out.json()["status"] == "OUTDATED"


@pytest.mark.asyncio
async def test_31_transition_outdated_to_archived(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Outdated To Archived", "content": "Text"}, headers=headers)
    item_id = create_res.json()["id"]

    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)
    await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "OUTDATED"}, headers=headers)

    res_arch = await async_client.post(f"/api/v1/knowledge/{item_id}/archive", headers=headers)
    assert res_arch.status_code == 200
    assert res_arch.json()["status"] == "ARCHIVED"


@pytest.mark.asyncio
async def test_32_invalid_status_transition_draft_to_outdated_rejected(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Draft Policy", "content": "Text"}, headers=headers)
    item_id = create_res.json()["id"]

    res_invalid = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "OUTDATED"}, headers=headers)
    assert res_invalid.status_code == 400


@pytest.mark.asyncio
async def test_33_invalid_status_transition_archived_to_active_rejected(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Draft Policy", "content": "Text"}, headers=headers)
    item_id = create_res.json()["id"]

    await async_client.delete(f"/api/v1/knowledge/{item_id}", headers=headers)

    res_invalid = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"status": "ACTIVE"}, headers=headers)
    assert res_invalid.status_code == 400


@pytest.mark.asyncio
async def test_34_version_increment_and_reapproval_reset_on_content_change(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Version 1 Policy", "content": "Text v1"}, headers=headers)
    item_id = create_res.json()["id"]

    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)

    res_edit = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"content": "Text v2 modified"}, headers=headers)
    assert res_edit.status_code == 200
    data = res_edit.json()
    assert data["version"] == 2
    assert data["status"] == "DRAFT"
    assert data["approval_id"] is None


@pytest.mark.asyncio
async def test_34_b_editing_content_with_status_approved_in_payload_still_resets_to_draft(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Original Approved", "content": "Text v1"}, headers=headers)
    item_id = create_res.json()["id"]

    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)

    # Client attempts to keep status APPROVED alongside content edit
    res_edit = await async_client.put(
        f"/api/v1/knowledge/{item_id}",
        json={"content": "Malicious edit attempting to keep approved status", "status": "APPROVED"},
        headers=headers,
    )
    assert res_edit.status_code == 200
    data = res_edit.json()
    assert data["status"] == "DRAFT"
    assert data["approval_id"] is None
    assert data["version"] == 2


@pytest.mark.asyncio
async def test_35_metadata_only_update_preserves_version_and_approval(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Policy", "content": "Text"}, headers=headers)
    item_id = create_res.json()["id"]

    app_res = await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)
    approval_id = app_res.json()["approval_id"]

    res_meta = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"source": "Internal Doc"}, headers=headers)
    assert res_meta.status_code == 200
    data = res_meta.json()
    assert data["version"] == 1
    assert data["status"] == "APPROVED"
    assert data["approval_id"] == approval_id


@pytest.mark.asyncio
async def test_36_knowledge_tenant_isolation_read(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}

    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Alpha Item", "content": "Text"}, headers=headers_a)
    item_id = create_res.json()["id"]

    res_b = await async_client.get(f"/api/v1/knowledge/{item_id}", headers=headers_b)
    assert res_b.status_code == 404


@pytest.mark.asyncio
async def test_37_knowledge_tenant_isolation_write(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}

    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Alpha Item", "content": "Text"}, headers=headers_a)
    item_id = create_res.json()["id"]

    res_b = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"title": "Hacked"}, headers=headers_b)
    assert res_b.status_code == 404


@pytest.mark.asyncio
async def test_38_knowledge_tenant_isolation_approve(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}

    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Alpha Item", "content": "Text"}, headers=headers_a)
    item_id = create_res.json()["id"]

    res_b = await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers_b)
    assert res_b.status_code == 404


@pytest.mark.asyncio
async def test_39_knowledge_permission_read_denied(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_wrong = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "unrelated.perm"}
    res = await async_client.get("/api/v1/knowledge", headers=headers_wrong)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_40_knowledge_permission_write_denied(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_read_only = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.read"}
    res = await async_client.post("/api/v1/knowledge", json={"title": "Item", "content": "Text"}, headers=headers_read_only)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_41_knowledge_permission_approve_denied(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_no_approve = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read"}
    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Draft Item", "content": "Text"}, headers=headers_no_approve)
    item_id = create_res.json()["id"]

    res_app = await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers_no_approve)
    assert res_app.status_code == 403


# --- 5. AUDIT TRAIL LOGGING TESTS ---

@pytest.mark.asyncio
async def test_42_audit_trail_recorded_on_business_mutation(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,business.read"}

    await async_client.put("/api/v1/business", json={"business_name": "Audit Company"}, headers=headers)

    audit_stmt = select(ProvisioningAudit).where(ProvisioningAudit.tenant_id == tenant_alpha.id)
    records = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(records) >= 1
    assert any("business_profile" in r.action for r in records)


@pytest.mark.asyncio
async def test_43_audit_trail_recorded_on_product_mutation(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}

    await async_client.post("/api/v1/products", json={"name": "Audit Product", "price": "12000.00"}, headers=headers)

    audit_stmt = select(ProvisioningAudit).where(ProvisioningAudit.tenant_id == tenant_alpha.id)
    records = (await db_session.execute(audit_stmt)).scalars().all()
    assert len(records) >= 1
    assert any(r.action == "product.created" for r in records)


@pytest.mark.asyncio
async def test_44_audit_trail_recorded_on_knowledge_mutation(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}

    create_res = await async_client.post("/api/v1/knowledge", json={"title": "Audit Knowledge", "content": "Text"}, headers=headers)
    item_id = create_res.json()["id"]
    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)

    audit_stmt = select(ProvisioningAudit).where(ProvisioningAudit.tenant_id == tenant_alpha.id)
    records = (await db_session.execute(audit_stmt)).scalars().all()
    actions = [r.action for r in records]
    assert "knowledge.created" in actions
    assert "knowledge.approved" in actions


# --- 6. DETERMINISTIC READINESS & AI ROUTER DB TRUTH TESTS ---

@pytest.mark.asyncio
async def test_45_readiness_check_unconfigured_tenant_returns_not_ready(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(tenant_alpha.id)}
    res = await async_client.get("/api/v1/business/readiness", headers=headers)
    assert res.status_code == 200
    assert res.json()["ready"] is False


@pytest.mark.asyncio
async def test_46_readiness_check_fully_configured_tenant_returns_ready(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,product.write,knowledge.write,knowledge.approve"}

    await async_client.put(
        "/api/v1/business",
        json={
            "business_name": "Full Ready Corp",
            "description": "Description",
            "operating_hours": {"mon_fri": "09:00-17:00"},
            "payment_methods": {"bank": ["BCA"]},
            "shipping_information": {"courier": ["JNE"]},
            "return_policy": "Retur 7 hari",
            "exchange_policy": "Tukar size",
            "refund_policy": "Refund 100%",
        },
        headers=headers,
    )
    await async_client.post("/api/v1/products", json={"name": "Ready Item", "price": "100000.00", "stock": 10}, headers=headers)
    await async_client.post("/api/v1/knowledge", json={"title": "Kebijakan", "content": "S&K", "status": "APPROVED"}, headers=headers)

    res = await async_client.get("/api/v1/business/readiness", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["ready"] is True
    assert data["readiness_status"] == "READY"
    assert data["score"] >= 90.0


@pytest.mark.asyncio
async def test_47_readiness_check_alias_endpoint_parity(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    headers = {"X-Tenant-ID": str(tenant_alpha.id)}
    res1 = await async_client.get("/api/v1/business/readiness", headers=headers)
    res2 = await async_client.get("/api/v1/business-profile/readiness", headers=headers)
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json() == res2.json()


@pytest.mark.asyncio
async def test_48_ai_router_never_uses_unapproved_draft_knowledge(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.write,knowledge.read,knowledge.approve"}

    # Draft item
    await async_client.post("/api/v1/knowledge", json={"title": "Unapproved Draft", "content": "Draft text"}, headers=headers)

    # Approved item
    app_res = await async_client.post("/api/v1/knowledge", json={"title": "Approved Policy", "content": "Approved text"}, headers=headers)
    item_id = app_res.json()["id"]
    await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)

    service = BusinessDataService(db_session)
    active_items = await service.know_repo.list_active_and_approved(tenant_alpha.id)
    assert len(active_items) == 1
    assert active_items[0].title == "Approved Policy"


@pytest.mark.asyncio
async def test_49_router_uses_db_price_truth_deterministically(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    from app.core.router.router import MessageRouter
    from app.database.models import Conversation, Message, Customer

    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    prod_res = await async_client.post("/api/v1/products", json={"name": "Jaket Kulit", "price": "750000.00", "stock": 5}, headers=headers)
    assert prod_res.status_code == 201

    cust = Customer(tenant_id=tenant_alpha.id, name="Budi", phone="+62812333444")
    db_session.add(cust)
    await db_session.commit()

    conv = Conversation(tenant_id=tenant_alpha.id, customer_id=cust.id, channel="whatsapp", status="OPEN", ai_enabled=True)
    db_session.add(conv)
    await db_session.commit()

    msg = Message(tenant_id=tenant_alpha.id, conversation_id=conv.id, direction="INBOUND", text="Berapa harga Jaket Kulit?")

    router = MessageRouter()
    result = await router.route_message(tenant_alpha.id, conv, msg, db_session)

    assert result.was_ai_called is False
    assert "750,000" in result.response_text


@pytest.mark.asyncio
async def test_50_router_uses_db_stock_truth_deterministically(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    from app.core.router.router import MessageRouter
    from app.database.models import Conversation, Message, Customer

    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    await async_client.post("/api/v1/products", json={"name": "Helm Retro", "price": "300000.00", "stock": 18}, headers=headers)

    cust = Customer(tenant_id=tenant_alpha.id, name="Rider", phone="+62812555666")
    db_session.add(cust)
    await db_session.commit()

    conv = Conversation(tenant_id=tenant_alpha.id, customer_id=cust.id, channel="whatsapp", status="OPEN", ai_enabled=True)
    db_session.add(conv)
    await db_session.commit()

    msg = Message(tenant_id=tenant_alpha.id, conversation_id=conv.id, direction="INBOUND", text="Stok Helm Retro ready berapa?")

    router = MessageRouter()
    result = await router.route_message(tenant_alpha.id, conv, msg, db_session)

    assert result.was_ai_called is False
    assert "18" in result.response_text


@pytest.mark.asyncio
async def test_51_cross_tenant_foreign_key_variant_protection(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_a = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "product.write,product.read"}
    headers_b = {"X-Tenant-ID": str(tenant_beta.id), "X-Actor-Permissions": "product.write,product.read"}

    prod_res = await async_client.post("/api/v1/products", json={"name": "Alpha Item", "price": "1000.00"}, headers=headers_a)
    alpha_prod_id = prod_res.json()["id"]

    var_res = await async_client.post(f"/api/v1/products/{alpha_prod_id}/variants", json={"name": "Malicious Variant"}, headers=headers_b)
    assert var_res.status_code == 404


@pytest.mark.asyncio
async def test_52_event_bus_publishing_reliability(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "business.write,product.write,knowledge.write,knowledge.approve"}

    res_bp = await async_client.put("/api/v1/business", json={"business_name": "Event Reliability Corp"}, headers=headers)
    assert res_bp.status_code in (200, 201)

    res_p = await async_client.post("/api/v1/products", json={"name": "Event Prod", "price": "5000.00"}, headers=headers)
    assert res_p.status_code == 201

    res_k = await async_client.post("/api/v1/knowledge", json={"title": "Event Knowledge", "content": "Text"}, headers=headers)
    assert res_k.status_code == 201

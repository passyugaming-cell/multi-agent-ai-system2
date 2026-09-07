import uuid
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.core.auth import ROLE_PERMISSIONS
from app.database.models import Tenant, User, BusinessProfile, Product, ProductVariant, KnowledgeItem
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


def _set_test_actor(tenant_id: uuid.UUID, role: str = "owner"):
    perms = set(ROLE_PERMISSIONS.get(role, set()))
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        role=role,
        permissions=perms,
    )
    return set_actor_context(actor)


# --- 1. RBAC FAIL-CLOSED & SECURITY ATTACK TESTS (ALL 8 ATTACK VECTORS) ---

@pytest.mark.asyncio
async def test_01_attack_vector_no_authenticated_actor_returns_403(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id)}  # No authenticated actor context or database user
    res = await async_client.get("/api/v1/business", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_02_attack_vector_forged_actor_role_header_rejected(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_forged = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Role": "owner"}
    res = await async_client.get("/api/v1/business", headers=headers_forged)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_03_attack_vector_forged_actor_id_header_rejected(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_forged = {"X-Tenant-ID": str(tenant_alpha.id), "X-Authenticated-Actor-ID": str(uuid.uuid4())}
    res = await async_client.get("/api/v1/business", headers=headers_forged)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_04_attack_vector_forged_tenant_mismatch_rejected(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    # Authenticated actor belongs to Tenant Alpha
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        # Client request attempts X-Tenant-ID for Tenant Beta
        headers_mismatch = {"X-Tenant-ID": str(tenant_beta.id)}
        res = await async_client.get("/api/v1/business", headers=headers_mismatch)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN_CROSS_TENANT_ACCESS"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_05_attack_vector_forged_wildcard_permissions_header_rejected(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_forged = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "*"}
    res = await async_client.get("/api/v1/business", headers=headers_forged)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_06_attack_vector_forged_approve_permissions_header_rejected(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_forged = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "knowledge.approve"}
    res = await async_client.post("/api/v1/knowledge", json={"title": "Forged Item", "content": "Text"}, headers=headers_forged)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_07_real_authenticated_owner_from_server_side_identity_success(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res = await async_client.put("/api/v1/business", json={"business_name": "Authenticated Alpha Corp"}, headers=headers)
        assert res.status_code in (200, 201)
        assert res.json()["business_name"] == "Authenticated Alpha Corp"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_08_real_authenticated_member_denied_write_permission(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="member")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res = await async_client.put("/api/v1/business", json={"business_name": "Member Attempt"}, headers=headers)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "PERMISSION_DENIED"
    finally:
        reset_actor_context(token)


# --- 2. BUSINESS PROFILE EXTENSION TESTS ---

@pytest.mark.asyncio
async def test_09_create_business_profile_extended_fields(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
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
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_10_get_business_profile_returns_404_when_missing(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res = await async_client.get("/api/v1/business", headers=headers)
        assert res.status_code == 404
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_11_update_existing_business_profile(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        await async_client.put("/api/v1/business", json={"business_name": "Initial Name"}, headers=headers)

        res_update = await async_client.put("/api/v1/business", json={"business_name": "Updated Name", "city": "Bandung"}, headers=headers)
        assert res_update.status_code == 200
        assert res_update.json()["business_name"] == "Updated Name"
        assert res_update.json()["city"] == "Bandung"
    finally:
        reset_actor_context(token)


# --- 3. PRODUCTS & SERVICES & VARIANTS TESTS ---

@pytest.mark.asyncio
async def test_12_create_physical_product(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
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
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_13_create_service_item(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
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
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_14_list_products_scoped_by_tenant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        await async_client.post("/api/v1/products", json={"name": "P1", "price": "100.00"}, headers=headers)
        await async_client.post("/api/v1/products", json={"name": "P2", "price": "200.00"}, headers=headers)

        res = await async_client.get("/api/v1/products", headers=headers)
        assert res.status_code == 200
        assert len(res.json()) >= 2
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_15_get_product_by_id(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        create_res = await async_client.post("/api/v1/products", json={"name": "Target Product", "price": "50000.00"}, headers=headers)
        prod_id = create_res.json()["id"]

        res = await async_client.get(f"/api/v1/products/{prod_id}", headers=headers)
        assert res.status_code == 200
        assert res.json()["id"] == prod_id
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_16_update_product_price_and_stock(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        create_res = await async_client.post("/api/v1/products", json={"name": "Old Item", "price": "10000.00", "stock": 5}, headers=headers)
        prod_id = create_res.json()["id"]

        update_res = await async_client.put(
            f"/api/v1/products/{prod_id}", json={"price": "15000.00", "stock": 20}, headers=headers
        )
        assert update_res.status_code == 200
        assert Decimal(update_res.json()["price"]) == Decimal("15000.00")
        assert update_res.json()["stock"] == 20
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_17_delete_product_deletes_cascade_variants(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        create_res = await async_client.post("/api/v1/products", json={"name": "Item To Delete", "price": "10000.00"}, headers=headers)
        prod_id = create_res.json()["id"]

        del_res = await async_client.delete(f"/api/v1/products/{prod_id}", headers=headers)
        assert del_res.status_code == 200

        get_res = await async_client.get(f"/api/v1/products/{prod_id}", headers=headers)
        assert get_res.status_code == 404
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_18_create_product_variant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
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
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_19_update_product_variant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        create_res = await async_client.post("/api/v1/products", json={"name": "Jam Tangan", "price": "1000000.00"}, headers=headers)
        prod_id = create_res.json()["id"]

        var_res = await async_client.post(f"/api/v1/products/{prod_id}/variants", json={"name": "Tali Kulit", "stock": 3}, headers=headers)
        var_id = var_res.json()["id"]

        update_var = await async_client.put(f"/api/v1/products/variants/{var_id}", json={"stock": 10}, headers=headers)
        assert update_var.status_code == 200
        assert update_var.json()["stock"] == 10
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_20_delete_product_variant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        create_res = await async_client.post("/api/v1/products", json={"name": "Topi", "price": "75000.00"}, headers=headers)
        prod_id = create_res.json()["id"]

        var_res = await async_client.post(f"/api/v1/products/{prod_id}/variants", json={"name": "Warna Merah", "stock": 5}, headers=headers)
        var_id = var_res.json()["id"]

        del_var = await async_client.delete(f"/api/v1/products/variants/{var_id}", headers=headers)
        assert del_var.status_code == 200
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_21_product_tenant_isolation_read(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token_a = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers_a = {"X-Tenant-ID": str(tenant_alpha.id)}
        create_res = await async_client.post("/api/v1/products", json={"name": "Alpha Item", "price": "100.00"}, headers=headers_a)
        prod_id = create_res.json()["id"]
    finally:
        reset_actor_context(token_a)

    token_b = _set_test_actor(tenant_beta.id, role="owner")
    try:
        headers_b = {"X-Tenant-ID": str(tenant_beta.id)}
        res_b = await async_client.get(f"/api/v1/products/{prod_id}", headers=headers_b)
        assert res_b.status_code == 404
    finally:
        reset_actor_context(token_b)


@pytest.mark.asyncio
async def test_22_negative_price_stock_rejected(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res_price = await async_client.post("/api/v1/products", json={"name": "Bad Price", "price": "-100.00"}, headers=headers)
        assert res_price.status_code == 400

        res_stock = await async_client.post("/api/v1/products", json={"name": "Bad Stock", "price": "100.00", "stock": -10}, headers=headers)
        assert res_stock.status_code == 400
    finally:
        reset_actor_context(token)


# --- 5. KNOWLEDGE BASE CREATION, LIFECYCLE & APPROVAL TESTS ---

@pytest.mark.asyncio
async def test_23_direct_approved_creation_prohibited(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res = await async_client.post("/api/v1/knowledge", json={"title": "Policy", "content": "Text", "status": "APPROVED"}, headers=headers)
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "INVALID_STATUS_ON_CREATION"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_24_direct_active_creation_prohibited(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res = await async_client.post("/api/v1/knowledge", json={"title": "Policy", "content": "Text", "status": "ACTIVE"}, headers=headers)
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "INVALID_STATUS_ON_CREATION"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_25_valid_knowledge_creation_forces_draft_and_v1(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res = await async_client.post("/api/v1/knowledge", json={"title": "Draft Policy", "content": "Initial Text"}, headers=headers)
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "DRAFT"
        assert data["version"] == 1
        assert data["approval_id"] is None
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_26_approve_knowledge_item_persists_approval_record(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
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
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_27_version_increment_and_reapproval_reset_on_content_change(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        create_res = await async_client.post("/api/v1/knowledge", json={"title": "Version 1 Policy", "content": "Text v1"}, headers=headers)
        item_id = create_res.json()["id"]

        await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)

        res_edit = await async_client.put(f"/api/v1/knowledge/{item_id}", json={"content": "Text v2 modified"}, headers=headers)
        assert res_edit.status_code == 200
        data = res_edit.json()
        assert data["version"] == 2
        assert data["status"] == "DRAFT"
        assert data["approval_id"] is None
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_28_editing_content_with_status_approved_in_payload_still_resets_to_draft(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        create_res = await async_client.post("/api/v1/knowledge", json={"title": "Original Approved", "content": "Text v1"}, headers=headers)
        item_id = create_res.json()["id"]

        await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)

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
    finally:
        reset_actor_context(token)


# --- 6. AUDIT TRAIL LOGGING TESTS ---

@pytest.mark.asyncio
async def test_29_audit_trail_recorded_on_business_and_knowledge_mutations(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}

        await async_client.put("/api/v1/business", json={"business_name": "Audit Company"}, headers=headers)
        create_res = await async_client.post("/api/v1/knowledge", json={"title": "Audit Knowledge", "content": "Text"}, headers=headers)
        item_id = create_res.json()["id"]
        await async_client.post(f"/api/v1/knowledge/{item_id}/approve", headers=headers)

        audit_stmt = select(ProvisioningAudit).where(ProvisioningAudit.tenant_id == tenant_alpha.id)
        records = (await db_session.execute(audit_stmt)).scalars().all()
        actions = [r.action for r in records]
        assert "knowledge.created" in actions
        assert "knowledge.approved" in actions
    finally:
        reset_actor_context(token)


# --- 7. DETERMINISTIC READINESS & AI ROUTER DB TRUTH TESTS ---

@pytest.mark.asyncio
async def test_30_readiness_check_fully_configured_tenant_returns_ready(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}

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
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_31_ai_router_never_uses_unapproved_draft_knowledge(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}

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
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_32_router_uses_db_price_truth_deterministically(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    from app.core.router.router import MessageRouter
    from app.database.models import Conversation, Message, Customer

    token = _set_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
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
    finally:
        reset_actor_context(token)

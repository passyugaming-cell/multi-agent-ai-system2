import uuid
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context, get_actor_context
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


def _set_trusted_test_actor(tenant_id: uuid.UUID, role: str = "owner"):
    perms = set(ROLE_PERMISSIONS.get(role, set()))
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        role=role,
        permissions=perms,
    )
    return set_actor_context(actor)


# --- 1. NEGATIVE SECURITY ATTACK TESTS ---

@pytest.mark.asyncio
async def test_01_no_authentication_denied(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers = {"X-Tenant-ID": str(tenant_alpha.id)}  # No authenticated actor context
    res = await async_client.get("/api/v1/business", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_02_x_actor_role_without_authentication_denied(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_forged = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Role": "owner"}
    res = await async_client.get("/api/v1/business", headers=headers_forged)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_03_x_actor_permissions_without_authentication_denied(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_forged = {"X-Tenant-ID": str(tenant_alpha.id), "X-Actor-Permissions": "*"}
    res = await async_client.get("/api/v1/business", headers=headers_forged)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_04_arbitrary_x_authenticated_actor_id_without_authentication_denied(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_forged = {"X-Tenant-ID": str(tenant_alpha.id), "X-Authenticated-Actor-ID": str(uuid.uuid4())}
    res = await async_client.get("/api/v1/business", headers=headers_forged)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_05_arbitrary_x_authenticated_tenant_id_without_authentication_denied(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    headers_forged = {"X-Tenant-ID": str(tenant_alpha.id), "X-Authenticated-Tenant-ID": str(tenant_alpha.id)}
    res = await async_client.get("/api/v1/business", headers=headers_forged)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_06_active_user_existing_in_tenant_does_not_automatically_authenticate_requester(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    # Add active user to DB for tenant_alpha
    user = User(tenant_id=tenant_alpha.id, email="owner@alpha.com", password_hash="hash", is_active=True)
    db_session.add(user)
    await db_session.commit()

    # Request with X-Tenant-ID only without authenticated session MUST be denied
    headers = {"X-Tenant-ID": str(tenant_alpha.id)}
    res = await async_client.get("/api/v1/business", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_07_authenticated_user_from_tenant_A_cannot_access_tenant_B(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    # Establish trusted actor context for Tenant Alpha
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
    try:
        # Request attempts X-Tenant-ID for Tenant Beta
        headers_mismatch = {"X-Tenant-ID": str(tenant_beta.id)}
        res = await async_client.get("/api/v1/business", headers=headers_mismatch)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "FORBIDDEN_CROSS_TENANT_ACCESS"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_08_authenticated_member_cannot_receive_owner_permissions(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="member")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res = await async_client.put("/api/v1/business", json={"business_name": "Member Attempt"}, headers=headers)
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "PERMISSION_DENIED"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_09_actor_context_does_not_leak_between_requests(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
    reset_actor_context(token)

    # After reset, request must be denied as unauthenticated
    headers = {"X-Tenant-ID": str(tenant_alpha.id)}
    res = await async_client.get("/api/v1/business", headers=headers)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


# --- 2. POSITIVE TRUSTED ACTOR TESTS ---

@pytest.mark.asyncio
async def test_10_real_trusted_authenticated_owner_allowed(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res = await async_client.put("/api/v1/business", json={"business_name": "Trusted Alpha Corp"}, headers=headers)
        assert res.status_code in (200, 201)
        assert res.json()["business_name"] == "Trusted Alpha Corp"
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_11_real_trusted_authenticated_member_allowed_read_only(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token_owner = _set_trusted_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        await async_client.put("/api/v1/business", json={"business_name": "Read Only Corp"}, headers=headers)
    finally:
        reset_actor_context(token_owner)

    token_member = _set_trusted_test_actor(tenant_alpha.id, role="member")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res_get = await async_client.get("/api/v1/business", headers=headers)
        assert res_get.status_code == 200
        assert res_get.json()["business_name"] == "Read Only Corp"
    finally:
        reset_actor_context(token_member)


# --- 3. BUSINESS PROFILE EXTENSION TESTS ---

@pytest.mark.asyncio
async def test_12_create_business_profile_extended_fields(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
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


# --- 4. PRODUCTS, SERVICES & VARIANTS TESTS ---

@pytest.mark.asyncio
async def test_13_create_physical_product_and_service(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res_p = await async_client.post("/api/v1/products", json={"name": "Kemeja Batik", "type": "PRODUCT", "price": "350000.00", "stock": 15}, headers=headers)
        assert res_p.status_code == 201

        res_s = await async_client.post("/api/v1/products", json={"name": "Sewa Kamera", "type": "SERVICE", "price": "250000.00", "unit": "hari"}, headers=headers)
        assert res_s.status_code == 201
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_14_create_and_manage_product_variant(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
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
        var_id = var_res.json()["id"]

        update_var = await async_client.put(f"/api/v1/products/variants/{var_id}", json={"stock": 12}, headers=headers)
        assert update_var.status_code == 200
        assert update_var.json()["stock"] == 12

        del_var = await async_client.delete(f"/api/v1/products/variants/{var_id}", headers=headers)
        assert del_var.status_code == 200
    finally:
        reset_actor_context(token)


# --- 5. KNOWLEDGE LIFECYCLE & APPROVAL TESTS ---

@pytest.mark.asyncio
async def test_15_direct_approved_or_active_creation_prohibited(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
        res_app = await async_client.post("/api/v1/knowledge", json={"title": "Policy", "content": "Text", "status": "APPROVED"}, headers=headers)
        assert res_app.status_code == 400

        res_act = await async_client.post("/api/v1/knowledge", json={"title": "Policy", "content": "Text", "status": "ACTIVE"}, headers=headers)
        assert res_act.status_code == 400
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_16_valid_creation_forces_draft_and_v1(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
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
async def test_17_approve_knowledge_item_persists_approval_record(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
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
async def test_18_version_increment_and_reapproval_reset_on_content_change(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
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
async def test_19_editing_content_with_status_approved_in_payload_still_resets_to_draft(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
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
async def test_20_audit_trail_recorded_on_business_and_knowledge_mutations(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
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
async def test_21_readiness_check_fully_configured_tenant_returns_ready(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_alpha.id)
    await db_session.commit()

    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
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
async def test_22_ai_router_never_uses_unapproved_draft_knowledge(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
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
async def test_23_router_uses_db_price_truth_deterministically(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    from app.core.router.router import MessageRouter
    from app.database.models import Conversation, Message, Customer

    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
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


@pytest.mark.asyncio
async def test_24_router_uses_db_stock_truth_deterministically(async_client: AsyncClient, tenant_alpha: Tenant, db_session: AsyncSession):
    await db_session.commit()
    from app.core.router.router import MessageRouter
    from app.database.models import Conversation, Message, Customer

    token = _set_trusted_test_actor(tenant_alpha.id, role="owner")
    try:
        headers = {"X-Tenant-ID": str(tenant_alpha.id)}
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
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_25_cross_tenant_foreign_key_variant_protection(async_client: AsyncClient, tenant_alpha: Tenant, tenant_beta: Tenant, db_session: AsyncSession):
    await db_session.commit()
    token_a = _set_trusted_test_actor(tenant_alpha.id, role="owner")
    try:
        headers_a = {"X-Tenant-ID": str(tenant_alpha.id)}
        prod_res = await async_client.post("/api/v1/products", json={"name": "Alpha Item", "price": "1000.00"}, headers=headers_a)
        alpha_prod_id = prod_res.json()["id"]
    finally:
        reset_actor_context(token_a)

    token_b = _set_trusted_test_actor(tenant_beta.id, role="owner")
    try:
        headers_b = {"X-Tenant-ID": str(tenant_beta.id)}
        var_res = await async_client.post(f"/api/v1/products/{alpha_prod_id}/variants", json={"name": "Malicious Variant"}, headers=headers_b)
        assert var_res.status_code == 404
    finally:
        reset_actor_context(token_b)

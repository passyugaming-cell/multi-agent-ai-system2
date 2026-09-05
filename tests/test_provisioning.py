import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.database.models.business_profile import BusinessProfile
from app.database.models.product import Product
from app.database.models.onboarding import OnboardingChecklist
from app.database.models.knowledge import KnowledgeCategory
from app.database.models.guardrail import AIGuardrail
from app.database.models.workflow import WorkflowConfiguration
from app.tenants.provisioning.provisioner import TenantProvisioner
from app.tenants.provisioning.readiness import ReadinessCalculator
from app.tenants.provisioning.validators import TenantValidatorEngine
from app.tenants.onboarding_service import OnboardingService


@pytest.mark.asyncio
async def test_provision_tenant_initializes_defaults(db_session: AsyncSession, tenant_a: Tenant) -> None:
    """Provisioning a new tenant creates default database records for checklist, knowledge, guardrails, and workflows."""
    provisioner = TenantProvisioner(db_session)
    res = await provisioner.provision_tenant(tenant_a.id)

    assert res.tenant_id == tenant_a.id
    assert res.provisioning_status == "COMPLETED"
    assert res.readiness_score < 90.0  # Empty tenant is NOT_READY

    # Verify database counts
    cl_count = (await db_session.execute(
        select(func.count(OnboardingChecklist.id)).where(OnboardingChecklist.tenant_id == tenant_a.id)
    )).scalar()
    assert cl_count == 17

    kc_count = (await db_session.execute(
        select(func.count(KnowledgeCategory.id)).where(KnowledgeCategory.tenant_id == tenant_a.id)
    )).scalar()
    assert kc_count == 10

    gr_count = (await db_session.execute(
        select(func.count(AIGuardrail.id)).where(AIGuardrail.tenant_id == tenant_a.id)
    )).scalar()
    assert gr_count == 11

    wf_count = (await db_session.execute(
        select(func.count(WorkflowConfiguration.id)).where(WorkflowConfiguration.tenant_id == tenant_a.id)
    )).scalar()
    assert wf_count == 3


@pytest.mark.asyncio
async def test_provisioning_is_idempotent(db_session: AsyncSession, tenant_a: Tenant) -> None:
    """Calling provision_tenant multiple times produces no duplicate records."""
    provisioner = TenantProvisioner(db_session)

    # First call
    res1 = await provisioner.provision_tenant(tenant_a.id)
    # Second call
    res2 = await provisioner.provision_tenant(tenant_a.id)
    # Third call
    res3 = await provisioner.provision_tenant(tenant_a.id)

    assert res1.checklist.total == res2.checklist.total == res3.checklist.total == 17

    cl_count = (await db_session.execute(
        select(func.count(OnboardingChecklist.id)).where(OnboardingChecklist.tenant_id == tenant_a.id)
    )).scalar()
    assert cl_count == 17

    kc_count = (await db_session.execute(
        select(func.count(KnowledgeCategory.id)).where(KnowledgeCategory.tenant_id == tenant_a.id)
    )).scalar()
    assert kc_count == 10


@pytest.mark.asyncio
async def test_readiness_score_and_blocking_items(db_session: AsyncSession, tenant_a: Tenant) -> None:
    """Verify readiness score increases when data is populated and reaches READY when 100% complete."""
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_a.id)

    # Initially empty -> score low and blocking items exist
    svc = OnboardingService(db_session)
    sum1 = await svc.get_onboarding_summary(tenant_a.id)
    assert sum1.readiness_status in ("NOT_READY", "NEARLY_READY")
    assert len(sum1.blocking_items) > 0

    # Populate BusinessProfile and Product for Tenant A
    bp = BusinessProfile(
        tenant_id=tenant_a.id,
        business_name="Alpha Store",
        business_type="Retail",
        description="Alpha Store sells top notch products",
        phone="+123456789",
        address="123 Main St",
        operating_hours={"mon": "09:00-17:00"},
        payment_methods={"cash": True, "card": True},
        shipping_information={"express": True},
        return_policy="30 days return policy",
        exchange_policy="14 days exchange policy",
        refund_policy="Full refund within 30 days",
    )
    db_session.add(bp)

    p1 = Product(
        tenant_id=tenant_a.id,
        name="Widget A",
        price=99.99,
        stock=50,
        is_active=True,
    )
    db_session.add(p1)
    await db_session.flush()

    # Re-validate
    sum2 = await svc.validate_onboarding(tenant_a.id)
    assert sum2.readiness_score >= 90.0
    assert len(sum2.blocking_items) == 0
    assert sum2.readiness_status == "READY"


@pytest.mark.asyncio
async def test_tenant_isolation_onboarding_and_provisioning(
    client: AsyncClient, db_session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    """Tenant A cannot read or modify Tenant B onboarding data or checklist."""
    # Provision both tenants
    provisioner = TenantProvisioner(db_session)
    await provisioner.provision_tenant(tenant_a.id)
    await provisioner.provision_tenant(tenant_b.id)

    # 1. Tenant A fetching Tenant B checklist via API parameter mismatch must be forbidden
    res = await client.get(
        f"/api/v1/tenants/{tenant_b.id}/onboarding/checklist",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN_CROSS_TENANT_ACCESS"

    # 2. Tenant A attempting to provision Tenant B must be forbidden
    res_prov = await client.post(
        f"/api/v1/tenants/{tenant_b.id}/provision",
        headers={"X-Tenant-ID": str(tenant_a.id)},
    )
    assert res_prov.status_code == 403
    assert res_prov.json()["error"]["code"] == "FORBIDDEN_CROSS_TENANT_ACCESS"


@pytest.mark.asyncio
async def test_onboarding_api_full_flow(
    client: AsyncClient, db_session: AsyncSession, tenant_a: Tenant
) -> None:
    """Test full API endpoint suite for onboarding."""
    headers = {"X-Tenant-ID": str(tenant_a.id)}

    # POST /provision
    prov_res = await client.post(
        f"/api/v1/tenants/{tenant_a.id}/provision",
        headers=headers,
    )
    assert prov_res.status_code == 200
    pdata = prov_res.json()
    assert pdata["provisioning_status"] == "COMPLETED"

    # POST /onboarding/start
    start_res = await client.post(
        f"/api/v1/tenants/{tenant_a.id}/onboarding/start",
        headers=headers,
    )
    assert start_res.status_code == 200

    # GET /onboarding/checklist
    cl_res = await client.get(
        f"/api/v1/tenants/{tenant_a.id}/onboarding/checklist",
        headers=headers,
    )
    assert cl_res.status_code == 200
    items = cl_res.json()
    assert len(items) == 17

    # PATCH /onboarding/checklist/{item_id} - skipping optional item allowed
    opt_item = next(i for i in items if not i["required"])
    patch_res = await client.patch(
        f"/api/v1/tenants/{tenant_a.id}/onboarding/checklist/{opt_item['id']}",
        headers=headers,
        json={"status": "SKIPPED"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "SKIPPED"

    # PATCH skipping required item must fail
    req_item = next(i for i in items if i["required"])
    fail_patch = await client.patch(
        f"/api/v1/tenants/{tenant_a.id}/onboarding/checklist/{req_item['id']}",
        headers=headers,
        json={"status": "SKIPPED"},
    )
    assert fail_patch.status_code == 400
    assert fail_patch.json()["error"]["code"] == "CHECKLIST_REQUIREMENT_ERROR"

    # POST /onboarding/complete fails if NOT_READY
    comp_fail = await client.post(
        f"/api/v1/tenants/{tenant_a.id}/onboarding/complete",
        headers=headers,
    )
    assert comp_fail.status_code == 400
    assert comp_fail.json()["error"]["code"] == "TENANT_NOT_READY"

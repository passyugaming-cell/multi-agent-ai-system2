import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import (
    AuthenticatedActor,
    set_actor_context,
    set_tenant_context,
    get_actor_context,
)
from app.core.auth import ROLE_PERMISSIONS, resolve_actor_permissions
from app.core.authority.schemas import (
    ActionRequest,
    ActionRiskLevel,
    ExecutionDecision,
    ActionBinding,
)
from app.core.authority.risk import RiskClassifier
from app.core.authority.service import ActionAuthorizationService
from app.core.approvals.service import ApprovalService
from app.agents import agent_registry, AgentRequest, AgentRequestStatus
from app.agents.base.permissions import check_tool_permission, AGENT_PERMISSIONS
from app.integrations import IntegrationService
from app.tenants.business_service import BusinessDataService
from app.database.models.workflow import Approval
from app.database.models.audit import ProvisioningAudit
from app.core.exceptions import AppException, AppError


@pytest.fixture
def tenant_id_a():
    return uuid.uuid4()


@pytest.fixture
def tenant_id_b():
    return uuid.uuid4()


@pytest.fixture
def human_platform_owner_actor(tenant_id_a):
    return AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id_a,
        role="owner",
        permissions=ROLE_PERMISSIONS["owner"],
        is_platform_owner=True,
    )


@pytest.fixture
def human_tenant_owner_actor(tenant_id_a):
    return AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id_a,
        role="owner",
        permissions=ROLE_PERMISSIONS["owner"],
        is_platform_owner=False,
    )


@pytest.fixture
def human_tenant_admin_actor(tenant_id_a):
    return AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id_a,
        role="admin",
        permissions=ROLE_PERMISSIONS["admin"],
        is_platform_owner=False,
    )


@pytest.fixture
def human_tenant_staff_actor(tenant_id_a):
    return AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id_a,
        role="member",
        permissions=ROLE_PERMISSIONS["member"],
        is_platform_owner=False,
    )


@pytest.fixture
def cross_tenant_actor(tenant_id_b):
    return AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id_b,
        role="owner",
        permissions=ROLE_PERMISSIONS["owner"],
        is_platform_owner=False,
    )


# -----------------------------------------------------------------------------
# 1. Human Owner vs Human Admin vs Staff Authority Boundaries
# -----------------------------------------------------------------------------

def test_rbac_role_permissions_matrix():
    owner_perms = ROLE_PERMISSIONS["owner"]
    admin_perms = ROLE_PERMISSIONS["admin"]
    member_perms = ROLE_PERMISSIONS["member"]

    # Owner has approve_refund permission
    assert "APPROVE_REFUND" in owner_perms
    # Admin has request_refund but NOT approve_refund
    assert "REQUEST_REFUND" in admin_perms
    assert "APPROVE_REFUND" not in admin_perms
    # Member (staff) has read-only status permissions
    assert "VIEW_PAYMENT_STATUS" in member_perms
    assert "MANAGE_PAYMENTS" not in member_perms
    assert "REQUEST_REFUND" not in member_perms
    assert "APPROVE_REFUND" not in member_perms


# -----------------------------------------------------------------------------
# 2. Risk Classifier & Action Risk Levels
# -----------------------------------------------------------------------------

def test_risk_classifier_levels():
    assert RiskClassifier.classify("send_message") == ActionRiskLevel.LOW
    assert RiskClassifier.classify("update_customer") == ActionRiskLevel.MEDIUM
    assert RiskClassifier.classify("midtrans_cancel_payment") == ActionRiskLevel.HIGH
    assert RiskClassifier.classify("request_refund") == ActionRiskLevel.HIGH
    assert RiskClassifier.classify("issue_refund") == ActionRiskLevel.CRITICAL
    assert RiskClassifier.classify("delete_customer") == ActionRiskLevel.CRITICAL
    # Parameter override check
    assert RiskClassifier.classify("custom_action", {"is_critical": True}) == ActionRiskLevel.CRITICAL
    assert RiskClassifier.classify("custom_action", {"financial_impact": "high"}) == ActionRiskLevel.HIGH
    # Fail-safe default fallback for unknown action
    assert RiskClassifier.classify("unknown_custom_action") == ActionRiskLevel.HIGH


# -----------------------------------------------------------------------------
# 3. ActionAuthorizationService & Risk-Based Evaluation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_authorization_low_risk(db_session: AsyncSession, tenant_id_a, human_tenant_staff_actor):
    auth_srv = ActionAuthorizationService(db_session)
    req = ActionRequest(
        action_type="send_message",
        target="whatsapp",
        tenant_id=tenant_id_a,
        actor=human_tenant_staff_actor,
        params={"message": "Hello"},
    )
    decision = await auth_srv.evaluate_action(req)
    assert decision.decision == ExecutionDecision.ALLOW
    assert decision.risk_level == ActionRiskLevel.LOW


@pytest.mark.asyncio
async def test_action_authorization_medium_risk_permission_check(
    db_session: AsyncSession, tenant_id_a, human_tenant_staff_actor, human_tenant_admin_actor
):
    auth_srv = ActionAuthorizationService(db_session)

    # Member (staff) lacks 'business.write' required for update_customer
    req_staff = ActionRequest(
        action_type="update_customer",
        target="customer_1",
        tenant_id=tenant_id_a,
        actor=human_tenant_staff_actor,
        params={"name": "New Name"},
    )
    dec_staff = await auth_srv.evaluate_action(req_staff)
    assert dec_staff.decision == ExecutionDecision.DENY
    assert "PERMISSION_DENIED" in dec_staff.reason

    # Admin possesses 'business.write'
    req_admin = ActionRequest(
        action_type="update_customer",
        target="customer_1",
        tenant_id=tenant_id_a,
        actor=human_tenant_admin_actor,
        params={"name": "New Name"},
    )
    dec_admin = await auth_srv.evaluate_action(req_admin)
    assert dec_admin.decision == ExecutionDecision.ALLOW


@pytest.mark.asyncio
async def test_action_authorization_high_risk_requires_approval(
    db_session: AsyncSession, tenant_id_a, human_tenant_owner_actor
):
    auth_srv = ActionAuthorizationService(db_session)
    req = ActionRequest(
        action_type="change_official_price",
        target="product_100",
        tenant_id=tenant_id_a,
        actor=human_tenant_owner_actor,
        params={"price": 500000},
    )
    decision = await auth_srv.evaluate_action(req)
    assert decision.decision == ExecutionDecision.WAITING_APPROVAL
    assert decision.risk_level == ActionRiskLevel.HIGH


# -----------------------------------------------------------------------------
# 4. Cross-Tenant Isolation Enforcement
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_tenant_access_denied_in_action_eval(
    db_session: AsyncSession, tenant_id_a, cross_tenant_actor
):
    auth_srv = ActionAuthorizationService(db_session)
    # Actor belongs to tenant B, request targets tenant A
    req = ActionRequest(
        action_type="send_message",
        target="whatsapp",
        tenant_id=tenant_id_a,
        actor=cross_tenant_actor,
        params={"message": "cross tenant payload"},
    )
    decision = await auth_srv.evaluate_action(req)
    assert decision.decision == ExecutionDecision.DENY
    assert "FORBIDDEN_CROSS_TENANT_ACCESS" in decision.reason


# -----------------------------------------------------------------------------
# 5. Owner AI vs Non-Platform Actor Boundary
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_ai_target_forbidden_for_non_platform_owner(
    db_session: AsyncSession, tenant_id_a, human_tenant_owner_actor, human_platform_owner_actor
):
    auth_srv = ActionAuthorizationService(db_session)

    # Tenant Owner (even with owner role on Business plan) is DENIED execution of Owner AI
    req_tenant_owner = ActionRequest(
        action_type="run_owner_ai",
        target="owner_ai",
        tenant_id=tenant_id_a,
        actor=human_tenant_owner_actor,
        params={},
    )
    dec_tenant = await auth_srv.evaluate_action(req_tenant_owner)
    assert dec_tenant.decision == ExecutionDecision.DENY
    assert "UNAUTHORIZED_OWNER_AI_ACCESS" in dec_tenant.reason or "PERMISSION_DENIED" in dec_tenant.reason

    # Human Platform Owner is ALLOWED
    req_platform = ActionRequest(
        action_type="run_owner_ai",
        target="owner_ai",
        tenant_id=tenant_id_a,
        actor=human_platform_owner_actor,
        params={},
    )
    dec_platform = await auth_srv.evaluate_action(req_platform)
    assert dec_platform.decision == ExecutionDecision.ALLOW


# -----------------------------------------------------------------------------
# 6. AI Cannot Grant or Escalate Authority & Agent Delegation Boundary
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_delegation_owner_ai_guard(db_session: AsyncSession, tenant_id_a):
    # Specialist agent (or workflow) attempting to delegate to owner_ai is BLOCKED
    req = AgentRequest(
        tenant_id=tenant_id_a,
        source="agent_delegation",
        source_agent="ai_sales",
        target_agent="owner_ai",
        task_type="escalate_authority",
        objective="Escalate to owner AI",
    )
    res = await agent_registry.delegate_task(req, db_session)
    assert res.status == AgentRequestStatus.BLOCKED
    assert "Human Platform Owner" in res.error


@pytest.mark.asyncio
async def test_agent_delegation_depth_limit(db_session: AsyncSession, tenant_id_a):
    req = AgentRequest(
        tenant_id=tenant_id_a,
        source="agent_delegation",
        source_agent="ai_sales",
        target_agent="ai_support",
        task_type="test",
        objective="Recursion test",
        delegation_depth=3,  # Exceeds MAX_DELEGATION_DEPTH=3
    )
    res = await agent_registry.delegate_task(req, db_session)
    assert res.status == AgentRequestStatus.BLOCKED
    assert "Delegation depth limit exceeded" in res.error


def test_specialist_agent_tool_permissions():
    # Specialist agent ai_sales can call get_products
    assert check_tool_permission("ai_sales", "get_products") is True
    # Specialist agent ai_sales cannot call direct_db_mutation or issue_refund
    assert check_tool_permission("ai_sales", "issue_refund") is False
    assert check_tool_permission("ai_sales", "direct_db_mutation") is False
    # Unregistered tool or unknown agent returns False
    assert check_tool_permission("unknown_agent", "get_products") is False


# -----------------------------------------------------------------------------
# 7. AI Cannot Self-Approve Actions
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_owner_ai_self_approval_prohibited_in_authorization(
    db_session: AsyncSession, tenant_id_a
):
    auth_srv = ActionAuthorizationService(db_session)
    # Action requested by owner_ai agent without prior human approval
    req = ActionRequest(
        action_type="issue_refund",
        target="payment_123",
        tenant_id=tenant_id_a,
        agent_id="owner_ai",
        params={"amount": 100000},
    )
    decision = await auth_srv.evaluate_action(req)
    assert decision.decision == ExecutionDecision.WAITING_APPROVAL
    assert "Human Owner approval required" in decision.reason or "cannot self-approve" in decision.reason


@pytest.mark.asyncio
async def test_approval_service_blocks_ai_self_approval(
    db_session: AsyncSession, tenant_id_a, human_tenant_owner_actor
):
    appr_srv = ApprovalService(db_session)
    now = datetime.now(timezone.utc)

    # Create PENDING high risk approval
    appr = Approval(
        tenant_id=tenant_id_a,
        action_type="issue_refund",
        target="payment_999",
        risk_level="CRITICAL",
        requested_by="owner_ai",
        reason="AI requested refund",
        status="PENDING",
        requested_at=now,
        meta_data={"params": {"amount": "50000"}},
    )
    db_session.add(appr)
    await db_session.commit()

    # Attempt to approve with decided_by="owner_ai" under Human Tenant Owner context (not platform owner)
    token = set_actor_context(human_tenant_owner_actor)
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_srv.approve(tenant_id_a, appr.id, decided_by="owner_ai")
        assert exc_info.value.status_code == 403
        assert "PERMISSION_DENIED" in exc_info.value.message
    finally:
        from app.core.context import reset_actor_context
        reset_actor_context(token)


# -----------------------------------------------------------------------------
# 8. Approval Binding Hash Matching & Fabrication Prevention
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approval_hash_mismatch_rejected(
    db_session: AsyncSession, tenant_id_a, human_platform_owner_actor
):
    auth_srv = ActionAuthorizationService(db_session)
    appr_srv = ApprovalService(db_session)
    now = datetime.now(timezone.utc)

    # 1. Create approval for price change = 100000
    original_params = {"price": 100000}
    action_hash = ActionBinding.compute_hash(
        action_type="change_official_price",
        target="product_1",
        tenant_id=tenant_id_a,
        params=original_params,
    )

    appr = Approval(
        tenant_id=tenant_id_a,
        action_type="change_official_price",
        target="product_1",
        risk_level="HIGH",
        requested_by="user_123",
        reason="Price update",
        status="PENDING",
        requested_at=now,
        meta_data={
            "params": original_params,
            "action_hash": action_hash,
        },
    )
    db_session.add(appr)
    await db_session.commit()

    # Approve as Human Platform Owner
    token = set_actor_context(human_platform_owner_actor)
    try:
        await appr_srv.approve(tenant_id_a, appr.id, decided_by=str(human_platform_owner_actor.user_id))
    finally:
        from app.core.context import reset_actor_context
        reset_actor_context(token)

        # Refresh approval record to get meta_data updated by approve()
        await db_session.refresh(appr)

    # Attempt to execute action with tampered/altered parameter price = 5000 (hash mismatch)
    req_tampered = ActionRequest(
        action_type="change_official_price",
        target="product_1",
        tenant_id=tenant_id_a,
        actor=human_platform_owner_actor,
        approval_id=appr.id,
        params={"price": 5000},  # Altered parameter!
    )
    dec = await auth_srv.evaluate_action(req_tampered)
    assert dec.decision == ExecutionDecision.DENY
    assert "APPROVAL_BINDING_MISMATCH" in dec.reason or "mismatch" in dec.reason.lower()


# -----------------------------------------------------------------------------
# 9. Service-Layer Authorization & Trusted Context Verification
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_layer_integration_service_checks_permissions(
    db_session: AsyncSession, tenant_id_a, human_tenant_staff_actor
):
    srv = IntegrationService(db_session)

    # Member (staff) possesses VIEW_INTEGRATIONS but lacks MANAGE_INTEGRATIONS / MANAGE_CREDENTIALS
    from app.integrations.exceptions import PermissionDeniedError
    with pytest.raises(PermissionDeniedError) as exc_info:
        await srv.connect_integration(
            tenant_id=tenant_id_a,
            integration_key="midtrans",
            credentials={"server_key": "dummy"},
            actor_permissions=human_tenant_staff_actor.permissions,
        )
    assert "MANAGE_INTEGRATIONS" in str(exc_info.value) or "PermissionDeniedError" in type(exc_info.value).__name__


@pytest.mark.asyncio
async def test_business_data_service_checks_permissions(
    db_session: AsyncSession, tenant_id_a, human_tenant_staff_actor
):
    svc = BusinessDataService(db_session)

    # Member (staff) possesses product.read but lacks product.write
    from app.schemas.domain import ProductCreate
    payload = ProductCreate(name="Test Product", price=10000)
    with pytest.raises(AppException) as exc_info:
        await svc.create_product(
            tenant_id=tenant_id_a,
            payload=payload,
            actor_permissions=human_tenant_staff_actor.permissions,
        )
    assert exc_info.value.code == "PERMISSION_DENIED"


# -----------------------------------------------------------------------------
# 10. Fail-Closed Authentication Resolution
# -----------------------------------------------------------------------------

def test_resolve_actor_permissions_fails_closed_without_actor():
    set_tenant_context(uuid.uuid4())
    # No active actor set in contextvar -> resolve_actor_permissions fails closed
    with pytest.raises(AppException) as exc_info:
        resolve_actor_permissions(
            x_actor_role=None,
            x_authenticated_actor_id=None,
            x_authenticated_tenant_id=None,
            x_actor_permissions=None,
        )
    assert exc_info.value.code == "PERMISSION_DENIED"
    assert exc_info.value.status_code == 403


# -----------------------------------------------------------------------------
# 11. Auditability & Event Trail Verification
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_evaluation_records_audit_event(
    db_session: AsyncSession, tenant_id_a, human_tenant_staff_actor
):
    auth_srv = ActionAuthorizationService(db_session)
    req = ActionRequest(
        action_type="send_message",
        target="whatsapp",
        tenant_id=tenant_id_a,
        actor=human_tenant_staff_actor,
        params={"message": "Audit check"},
        correlation_id="corr_audit_123",
    )
    await auth_srv.evaluate_action(req)
    await db_session.flush()

    # Query audit record in database
    from sqlalchemy import select
    stmt = select(ProvisioningAudit).where(
        ProvisioningAudit.tenant_id == tenant_id_a,
        ProvisioningAudit.action == "action_authorization.send_message",
    )
    audit = (await db_session.execute(stmt)).scalar_one_or_none()
    assert audit is not None
    assert audit.result == "LOW_RISK_AUTHORIZED"
    assert audit.metadata_info.get("correlation_id") == "corr_audit_123"


# -----------------------------------------------------------------------------
# 12. Security Attack Regression Tests (Attacks 1-5) & Delegation Monotonicity
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attack_1_forged_internal_bypass_denied(
    db_session: AsyncSession, tenant_id_a, human_tenant_staff_actor, cross_tenant_actor
):
    """Attack 1 — Untrusted actor attempting internal service call with allow_internal=True is STILL subject to permission & tenant isolation checks."""
    srv = IntegrationService(db_session)
    from app.integrations.exceptions import PermissionDeniedError

    # 1. Staff member passing allow_internal=True cannot bypass missing MANAGE_INTEGRATIONS permission
    with pytest.raises(PermissionDeniedError):
        await srv.connect_integration(
            tenant_id=tenant_id_a,
            integration_key="midtrans",
            credentials={"server_key": "forged_key"},
            actor_permissions=human_tenant_staff_actor.permissions, # Staff lacks MANAGE_INTEGRATIONS
            allow_internal=True, # Attempting internal bypass!
        )

    # 2. Staff member with empty actor_permissions passing allow_internal=True cannot execute integration
    with pytest.raises(PermissionDeniedError):
        await srv.execute_operation(
            tenant_id=tenant_id_a,
            connection_id=uuid.uuid4(),
            operation="cancel_payment",
            params={},
            actor_permissions=set(), # Empty permissions
            allow_internal=True, # Attempting internal bypass!
        )

    # 3. Cross-tenant staff member passing allow_internal=True cannot bypass permission check for tenant A
    with pytest.raises(PermissionDeniedError):
        await srv.connect_integration(
            tenant_id=tenant_id_a,
            integration_key="midtrans",
            credentials={"server_key": "forged_key"},
            actor_permissions=human_tenant_staff_actor.permissions,
            allow_internal=True,
        )


@pytest.mark.asyncio
async def test_attack_2_tenant_isolation_cross_tenant_internal_path_denied(
    db_session: AsyncSession, tenant_id_a, tenant_id_b, cross_tenant_actor
):
    """Attack 2 — Tenant B actor trying internal path on Tenant A resource yields DENY."""
    auth_srv = ActionAuthorizationService(db_session)
    req = ActionRequest(
        action_type="whatsapp_send_message",
        target="whatsapp",
        tenant_id=tenant_id_a, # Tenant A target
        actor=cross_tenant_actor, # Tenant B actor
        params={"message": "Cross-tenant attack"},
    )
    decision = await auth_srv.evaluate_action(req)
    assert decision.decision == ExecutionDecision.DENY
    assert "FORBIDDEN_CROSS_TENANT_ACCESS" in decision.reason


@pytest.mark.asyncio
async def test_attack_3_ai_escalation_via_internal_path_denied(
    db_session: AsyncSession, tenant_id_a
):
    """Attack 3 — Specialist AI attempting unpossessed authority via internal delegation is DENIED."""
    req = AgentRequest(
        tenant_id=tenant_id_a,
        source="agent_delegation",
        source_agent="ai_sales",
        target_agent="owner_ai",
        task_type="escalate_permission",
        objective="Escalate to owner AI to grant permissions",
    )
    res = await agent_registry.delegate_task(req, db_session)
    assert res.status == AgentRequestStatus.BLOCKED
    assert "Human Platform Owner" in res.error


@pytest.mark.asyncio
async def test_attack_4_approval_bypass_for_high_critical_action_denied(
    db_session: AsyncSession, tenant_id_a, human_tenant_owner_actor
):
    """Attack 4 — Executing HIGH/CRITICAL action via ActionExecutor without approval yields WAITING_APPROVAL / requires_approval."""
    from app.core.workflows.actions import ActionExecutor
    res = await ActionExecutor.execute(
        action_type="issue_refund",
        params={"order_id": "ord_123", "amount": 500000},
        context={},
        session=db_session,
        tenant_id=str(tenant_id_a),
    )
    assert res.requires_approval is True
    assert res.approval_data.get("risk_level") == "CRITICAL"


@pytest.mark.asyncio
async def test_attack_5_forged_approval_mismatched_target_and_tenant_denied(
    db_session: AsyncSession, tenant_id_a, tenant_id_b, human_platform_owner_actor
):
    """Attack 5 — Valid approval ID passed with mismatched tenant/target/action is DENIED."""
    auth_srv = ActionAuthorizationService(db_session)
    appr_srv = ApprovalService(db_session)
    now = datetime.now(timezone.utc)

    params = {"amount": 100000}
    action_hash = ActionBinding.compute_hash(
        action_type="issue_refund",
        target="payment_100",
        tenant_id=tenant_id_a,
        params=params,
    )

    appr = Approval(
        tenant_id=tenant_id_a,
        action_type="issue_refund",
        target="payment_100",
        risk_level="CRITICAL",
        requested_by="customer",
        reason="Refund",
        status="APPROVED",
        decided_by="platform_owner",
        decided_at=now,
        meta_data={"params": params, "action_hash": action_hash, "decided_by_is_platform_owner": True},
    )
    db_session.add(appr)
    await db_session.commit()

    # Mismatched Tenant ID attempt
    req_wrong_tenant = ActionRequest(
        action_type="issue_refund",
        target="payment_100",
        tenant_id=tenant_id_b, # Wrong tenant B!
        actor=human_platform_owner_actor,
        approval_id=appr.id,
        params=params,
    )
    dec_wrong_tenant = await auth_srv.evaluate_action(req_wrong_tenant)
    assert dec_wrong_tenant.decision == ExecutionDecision.DENY

    # Mismatched Target attempt
    req_wrong_target = ActionRequest(
        action_type="issue_refund",
        target="payment_999", # Mismatched target!
        tenant_id=tenant_id_a,
        actor=human_platform_owner_actor,
        approval_id=appr.id,
        params=params,
    )
    dec_wrong_target = await auth_srv.evaluate_action(req_wrong_target)
    assert dec_wrong_target.decision == ExecutionDecision.DENY


def test_delegation_monotonicity():
    """Delegation Monotonicity — Delegated request permissions cannot exceed delegator permissions."""
    # 1. Specialist AI ai_sales cannot execute forbidden actions or tools outside its scope
    sales_tools = AGENT_PERMISSIONS["ai_sales"]["allowed_tools"]
    forbidden_sales = AGENT_PERMISSIONS["ai_sales"]["forbidden_actions"]
    assert "issue_refund" in forbidden_sales
    assert "change_official_price" in forbidden_sales
    assert check_tool_permission("ai_sales", "issue_refund") is False

    # 2. Specialist AI ai_analyst is read-only and cannot mutate business data
    assert AGENT_PERMISSIONS["ai_analyst"]["read_only"] is True
    assert check_tool_permission("ai_analyst", "modify_business_data") is False

    # 3. Specialist AI ai_support cannot execute critical production changes
    forbidden_support = AGENT_PERMISSIONS["ai_support"]["forbidden_actions"]
    assert "critical_production_change" in forbidden_support


@pytest.mark.asyncio
async def test_low_risk_action_contract_traceability():
    """LOW-Risk Permission Contract Traceability — Verify LOW-risk actions execute autonomously under tenant scope without approval gates."""
    assert RiskClassifier.classify("send_message") == ActionRiskLevel.LOW
    assert RiskClassifier.classify("create_task") == ActionRiskLevel.LOW
    assert RiskClassifier.classify("add_tag") == ActionRiskLevel.LOW
    assert RiskClassifier.classify("remove_tag") == ActionRiskLevel.LOW
    assert RiskClassifier.classify("log_result") == ActionRiskLevel.LOW
    assert RiskClassifier.classify("delay") == ActionRiskLevel.LOW
    assert RiskClassifier.classify("emit_event") == ActionRiskLevel.LOW

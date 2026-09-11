import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authority import (
    ActionRiskLevel,
    ExecutionDecision,
    ActionBinding,
    ActionRequest,
    RiskClassifier,
    ActionAuthorizationService,
)
from app.core.workflows.actions import ActionExecutor
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.database.models.workflow import Approval
from app.core.approvals.service import ApprovalService
from app.core.exceptions import AppError


@pytest.mark.asyncio
async def test_risk_classification():
    """Verify deterministic risk classification mapping."""
    assert RiskClassifier.classify("send_message") == ActionRiskLevel.LOW
    assert RiskClassifier.classify("create_task") == ActionRiskLevel.LOW
    assert RiskClassifier.classify("update_customer") == ActionRiskLevel.MEDIUM
    assert RiskClassifier.classify("call_agent") == ActionRiskLevel.MEDIUM
    assert RiskClassifier.classify("midtrans_cancel_payment") == ActionRiskLevel.HIGH
    assert RiskClassifier.classify("issue_refund") == ActionRiskLevel.HIGH
    assert RiskClassifier.classify("delete_customer") == ActionRiskLevel.CRITICAL
    assert RiskClassifier.classify("delete_data") == ActionRiskLevel.CRITICAL
    # Unknown actions fail-safe to HIGH risk
    assert RiskClassifier.classify("unknown_custom_action") == ActionRiskLevel.HIGH


# ============================================================================
# MEDIUM-RISK PERMISSION ENFORCEMENT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_medium_action_actor_has_required_permission_allows(db_session: AsyncSession, tenant_a):
    """MEDIUM action + actor has required permission -> ALLOW."""
    service = ActionAuthorizationService(db_session)
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="admin",
        permissions={"business.write", "business.read"},
    )
    req = ActionRequest(
        action_type="update_customer",
        target="customer_123",
        tenant_id=tenant_a.id,
        actor=actor,
        params={"customer_id": "c_123", "name": "Updated Name"},
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.ALLOW
    assert dec.risk_level == ActionRiskLevel.MEDIUM


@pytest.mark.asyncio
async def test_medium_action_actor_lacks_required_permission_denies(db_session: AsyncSession, tenant_a):
    """MEDIUM action + actor lacks required permission -> DENY."""
    service = ActionAuthorizationService(db_session)
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="member",
        permissions={"business.read"}, # Lacks business.write!
    )
    req = ActionRequest(
        action_type="update_customer",
        target="customer_123",
        tenant_id=tenant_a.id,
        actor=actor,
        params={"customer_id": "c_123", "name": "Updated Name"},
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.DENY
    assert "PERMISSION_DENIED" in dec.reason


@pytest.mark.asyncio
async def test_medium_action_no_permissions_denies(db_session: AsyncSession, tenant_a):
    """MEDIUM action + no permissions -> DENY."""
    service = ActionAuthorizationService(db_session)
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="guest",
        permissions=set(), # Empty permissions!
    )
    req = ActionRequest(
        action_type="update_order",
        target="order_123",
        tenant_id=tenant_a.id,
        actor=actor,
        params={"order_id": "o_123"},
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.DENY
    assert "PERMISSION_DENIED" in dec.reason


@pytest.mark.asyncio
async def test_medium_action_ai_actor_lacking_permission_denies(db_session: AsyncSession, tenant_a):
    """MEDIUM action cannot bypass permission checks because actor is an AI."""
    service = ActionAuthorizationService(db_session)
    ai_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="agent_ai_sales",
        permissions=set(), # AI agent with no explicit permissions
    )
    req = ActionRequest(
        action_type="whatsapp_send_message",
        target="whatsapp",
        tenant_id=tenant_a.id,
        actor=ai_actor,
        agent_id="ai_sales",
        params={"message": "Unapproved broadcast"},
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.DENY
    assert "PERMISSION_DENIED" in dec.reason


# ============================================================================
# APPROVAL IDENTITY ENFORCEMENT SECURITY REGRESSION TESTS (Case 1 - 10)
# ============================================================================

@pytest.mark.asyncio
async def test_security_case_01_non_platform_actor_attempting_high_approval_raises_403(db_session: AsyncSession, tenant_a):
    """Case 1: Non-platform actor attempting HIGH approval -> 403."""
    appr_service = ApprovalService(db_session)
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="ai_agent",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr)
    await db_session.commit()

    non_platform_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner", # Tenant Owner, NOT Platform Owner!
        is_platform_owner=False,
    )
    token = set_actor_context(non_platform_actor)
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.approve(tenant_a.id, appr.id, decided_by="tenant_owner")
        assert exc_info.value.status_code == 403
        assert "PERMISSION_DENIED" in exc_info.value.message
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_security_case_02_non_platform_actor_using_decided_by_platform_owner_raises_403(db_session: AsyncSession, tenant_a):
    """Case 2: Non-platform actor using decided_by='platform_owner' -> 403."""
    appr_service = ApprovalService(db_session)
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="ai_agent",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr)
    await db_session.commit()

    non_platform_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="member",
        is_platform_owner=False,
    )
    token = set_actor_context(non_platform_actor)
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.approve(tenant_a.id, appr.id, decided_by="platform_owner") # String spoofing attempt!
        assert exc_info.value.status_code == 403
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_security_case_03_non_platform_actor_using_decided_by_human_platform_owner_raises_403(db_session: AsyncSession, tenant_a):
    """Case 3: Non-platform actor using decided_by='human_platform_owner' -> 403."""
    appr_service = ApprovalService(db_session)
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="ai_agent",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr)
    await db_session.commit()

    non_platform_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="admin",
        is_platform_owner=False,
    )
    token = set_actor_context(non_platform_actor)
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.approve(tenant_a.id, appr.id, decided_by="human_platform_owner") # String spoofing attempt!
        assert exc_info.value.status_code == 403
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_security_case_04_human_platform_owner_approval_succeeds(db_session: AsyncSession, tenant_a):
    """Case 4: Human Platform Owner approval -> succeeds."""
    appr_service = ApprovalService(db_session)
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="ai_agent",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr)
    await db_session.commit()

    platform_owner_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        is_platform_owner=True, # Valid Human Platform Owner
    )
    token = set_actor_context(platform_owner_actor)
    try:
        approved = await appr_service.approve(tenant_a.id, appr.id, decided_by="trusted_human_owner")
        assert approved.status == "APPROVED"
        assert approved.meta_data.get("decided_by_is_platform_owner") is True
        assert approved.meta_data.get("decided_by_user_id") == str(platform_owner_actor.user_id)
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_security_case_05_owner_ai_self_approval_rejected(db_session: AsyncSession, tenant_a):
    """Case 5: Owner AI self-approval -> rejected."""
    appr_service = ApprovalService(db_session)
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="agent:owner_ai",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr)
    await db_session.commit()

    owner_ai_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner_ai",
        is_platform_owner=True, # Even if platform owner flag was somehow set
    )
    token = set_actor_context(owner_ai_actor)
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.approve(tenant_a.id, appr.id, decided_by="owner_ai")
        assert exc_info.value.status_code == 403
        assert "cannot self-approve" in exc_info.value.message
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_security_case_06_requesting_agent_self_approval_rejected(db_session: AsyncSession, tenant_a):
    """Case 6: Requesting agent self-approval -> rejected."""
    appr_service = ApprovalService(db_session)
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="agent:ai_sales",
        action_type="approve_discount",
        target="customer_1",
        reason="Discount",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr)
    await db_session.commit()

    agent_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="agent:ai_sales",
        is_platform_owner=False,
    )
    token = set_actor_context(agent_actor)
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.approve(tenant_a.id, appr.id, decided_by="agent:ai_sales")
        assert exc_info.value.status_code == 403
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_security_case_07_approval_with_decided_by_metadata_missing_denies(db_session: AsyncSession, tenant_a):
    """Case 7: Approval with decided_by metadata missing -> DENY."""
    service = ActionAuthorizationService(db_session)
    params = {"order_id": "ord_123", "amount": 100}
    action_hash = ActionBinding.compute_hash(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
    )

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="ai_agent",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="APPROVED",
        decided_by="platform_owner", # Raw string without metadata!
        meta_data={"params": params, "action_hash": action_hash}, # Missing decided_by_is_platform_owner!
    )
    db_session.add(appr)
    await db_session.commit()

    req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.DENY
    assert "Human Platform Owner" in dec.reason


@pytest.mark.asyncio
async def test_security_case_08_approval_with_decided_by_is_platform_owner_false_denies(db_session: AsyncSession, tenant_a):
    """Case 8: Approval with decided_by_is_platform_owner=False -> DENY."""
    service = ActionAuthorizationService(db_session)
    params = {"order_id": "ord_123", "amount": 100}
    action_hash = ActionBinding.compute_hash(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
    )

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="ai_agent",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="APPROVED",
        decided_by="tenant_owner_user",
        meta_data={"params": params, "action_hash": action_hash, "decided_by_is_platform_owner": False},
    )
    db_session.add(appr)
    await db_session.commit()

    req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.DENY
    assert "Human Platform Owner" in dec.reason


@pytest.mark.asyncio
async def test_security_case_09_approval_with_valid_platform_owner_metadata_allows(db_session: AsyncSession, tenant_a):
    """Case 9: Approval with valid platform-owner metadata -> ALLOW."""
    service = ActionAuthorizationService(db_session)
    params = {"order_id": "ord_123", "amount": 100}
    action_hash = ActionBinding.compute_hash(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
    )

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="ai_agent",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="APPROVED",
        decided_by="trusted_human_platform_owner",
        meta_data={"params": params, "action_hash": action_hash, "decided_by_is_platform_owner": True},
    )
    db_session.add(appr)
    await db_session.commit()

    req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.ALLOW
    assert dec.approval_id == appr.id


@pytest.mark.asyncio
async def test_security_case_10_approval_where_decided_by_equals_request_agent_id_denies(db_session: AsyncSession, tenant_a):
    """Case 10: Approval where decided_by == request.agent_id -> DENY."""
    service = ActionAuthorizationService(db_session)
    params = {"order_id": "ord_123", "amount": 100}
    action_hash = ActionBinding.compute_hash(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
    )

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="ai_sales",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="APPROVED",
        decided_by="ai_sales", # Agent attempted self-approval!
        meta_data={"params": params, "action_hash": action_hash, "decided_by_is_platform_owner": True},
    )
    db_session.add(appr)
    await db_session.commit()

    req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        agent_id="ai_sales",
        params=params,
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.DENY
    assert "cannot self-approve" in dec.reason.lower()


# ============================================================================
# REGRESSION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_already_approved_param_cannot_bypass_action_executor(db_session: AsyncSession, tenant_a):
    """REGRESSION TEST: Verify _already_approved: True parameter CANNOT bypass authorization gate."""
    res = await ActionExecutor.execute(
        action_type="issue_refund",
        params={"order_id": "ord_fake", "amount": 1000, "_already_approved": True},
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )
    assert res.requires_approval is True
    assert res.success is True
    assert res.output == {}


@pytest.mark.asyncio
async def test_fake_approval_booleans_cannot_bypass(db_session: AsyncSession, tenant_a):
    """REGRESSION TEST: Verify fake approval booleans (approved: True, is_approved: True) cannot bypass authorization."""
    res1 = await ActionExecutor.execute(
        action_type="midtrans_cancel_payment",
        params={"order_id": "ord_fake", "approved": True},
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )
    assert res1.requires_approval is True

    res2 = await ActionExecutor.execute(
        action_type="delete_customer",
        params={"customer_id": "cust_fake", "is_approved": True},
        context={},
        session=db_session,
        tenant_id=str(tenant_a.id),
    )
    assert res2.requires_approval is True

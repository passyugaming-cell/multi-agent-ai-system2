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
# MEDIUM-RISK PERMISSION ENFORCEMENT TESTS (Case 1 - 4)
# ============================================================================

@pytest.mark.asyncio
async def test_01_medium_action_actor_has_required_permission_allows(db_session: AsyncSession, tenant_a):
    """Case 1: MEDIUM action + actor has required permission -> ALLOW."""
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
async def test_02_medium_action_actor_lacks_required_permission_denies(db_session: AsyncSession, tenant_a):
    """Case 2: MEDIUM action + actor lacks required permission -> DENY."""
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
async def test_03_medium_action_no_permissions_denies(db_session: AsyncSession, tenant_a):
    """Case 3: MEDIUM action + no permissions -> DENY."""
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
async def test_04_medium_action_ai_actor_lacking_permission_denies(db_session: AsyncSession, tenant_a):
    """Case 4: MEDIUM action cannot bypass permission checks because actor is an AI."""
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
# HIGH / CRITICAL APPROVAL & PROVENANCE TESTS (Case 5 - 12)
# ============================================================================

@pytest.mark.asyncio
async def test_05_high_action_without_approval_returns_waiting_approval(db_session: AsyncSession, tenant_a):
    """Case 5: HIGH action without approval -> WAITING_APPROVAL."""
    service = ActionAuthorizationService(db_session)
    req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params={"order_id": "ord_123", "amount": 100},
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.WAITING_APPROVAL
    assert dec.risk_level == ActionRiskLevel.HIGH


@pytest.mark.asyncio
async def test_06_high_action_valid_approval_from_platform_owner_allows(db_session: AsyncSession, tenant_a):
    """Case 6: HIGH action with valid approval from authorized Human Platform Owner -> ALLOW."""
    service = ActionAuthorizationService(db_session)
    params = {"order_id": "ord_123", "amount": 500}
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
        reason="Refund requested by customer",
        risk_level="HIGH",
        status="APPROVED",
        decided_by="platform_owner",
        decided_at=datetime.now(timezone.utc),
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
async def test_07_high_action_approval_from_unauthorized_actor_denies(db_session: AsyncSession, tenant_a):
    """Case 7: HIGH action with approval from unauthorized non-platform actor -> DENY."""
    service = ActionAuthorizationService(db_session)
    params = {"order_id": "ord_123", "amount": 500}
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
        decided_by="unauthorized_tenant_member", # NOT a platform owner!
        decided_at=datetime.now(timezone.utc),
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
async def test_08_high_action_owner_ai_as_approver_denies(db_session: AsyncSession, tenant_a):
    """Case 8: HIGH action with Owner AI as approver -> DENY."""
    service = ActionAuthorizationService(db_session)
    params = {"order_id": "ord_123", "amount": 500}
    action_hash = ActionBinding.compute_hash(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
    )

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="agent:owner_ai",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="APPROVED",
        decided_by="owner_ai", # Owner AI attempted self-approval!
        decided_at=datetime.now(timezone.utc),
        meta_data={"params": params, "action_hash": action_hash},
    )
    db_session.add(appr)
    await db_session.commit()

    req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        agent_id="owner_ai",
        params=params,
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.DENY
    assert "cannot self-approve" in dec.reason or "Human Platform Owner" in dec.reason


@pytest.mark.asyncio
async def test_09_high_action_mismatched_action_hash_denies(db_session: AsyncSession, tenant_a):
    """Case 9: HIGH action with mismatched action_hash -> DENY."""
    service = ActionAuthorizationService(db_session)
    original_params = {"amount": 100, "customer_id": "c_1"}
    original_hash = ActionBinding.compute_hash(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=original_params,
    )

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="user_owner",
        action_type="issue_refund",
        target="issue_refund",
        reason="Approved refund of 100",
        risk_level="HIGH",
        status="APPROVED",
        decided_by="platform_owner",
        meta_data={"params": original_params, "action_hash": original_hash, "decided_by_is_platform_owner": True},
    )
    db_session.add(appr)
    await db_session.commit()

    # Forged parameters amount=10000
    forged_req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params={"amount": 10000, "customer_id": "c_1"},
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(forged_req)
    assert dec.decision == ExecutionDecision.DENY
    assert "mismatch" in dec.reason.lower()


@pytest.mark.asyncio
async def test_10_high_action_expired_approval_denies(db_session: AsyncSession, tenant_a):
    """Case 10: HIGH action with expired approval -> DENY."""
    service = ActionAuthorizationService(db_session)
    params = {"amount": 100}

    expired_appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="user_owner",
        action_type="issue_refund",
        target="issue_refund",
        reason="Old refund",
        risk_level="HIGH",
        status="APPROVED",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        decided_by="platform_owner",
        meta_data={"params": params, "decided_by_is_platform_owner": True},
    )
    db_session.add(expired_appr)
    await db_session.commit()

    req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
        approval_id=expired_appr.id,
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.DENY
    assert "expired" in dec.reason.lower()


@pytest.mark.asyncio
async def test_11_critical_action_follows_independent_human_approval_rule(db_session: AsyncSession, tenant_a):
    """Case 11: CRITICAL action follows the same independent-human approval rule."""
    service = ActionAuthorizationService(db_session)
    params = {"customer_id": "c_999"}
    action_hash = ActionBinding.compute_hash(
        action_type="delete_customer",
        target="delete_customer",
        tenant_id=tenant_a.id,
        params=params,
    )

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="ai_agent",
        action_type="delete_customer",
        target="delete_customer",
        reason="Delete customer account",
        risk_level="CRITICAL",
        status="APPROVED",
        decided_by="platform_owner",
        decided_at=datetime.now(timezone.utc),
        meta_data={"params": params, "action_hash": action_hash, "decided_by_is_platform_owner": True},
    )
    db_session.add(appr)
    await db_session.commit()

    req = ActionRequest(
        action_type="delete_customer",
        target="delete_customer",
        tenant_id=tenant_a.id,
        params=params,
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.ALLOW
    assert dec.risk_level == ActionRiskLevel.CRITICAL


@pytest.mark.asyncio
async def test_12_cross_tenant_approval_remains_deny(db_session: AsyncSession, tenant_a, tenant_b):
    """Case 12: Cross-tenant approval remains DENY."""
    service = ActionAuthorizationService(db_session)

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="user_owner",
        action_type="issue_refund",
        target="issue_refund",
        reason="Tenant A refund",
        risk_level="HIGH",
        status="APPROVED",
        decided_by="platform_owner",
        meta_data={"params": {"amount": 50}, "decided_by_is_platform_owner": True},
    )
    db_session.add(appr)
    await db_session.commit()

    req_tenant_b = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_b.id,
        params={"amount": 50},
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(req_tenant_b)
    assert dec.decision == ExecutionDecision.DENY
    assert "cross-tenant" in dec.reason.lower() or "invalid approval" in dec.reason.lower()


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

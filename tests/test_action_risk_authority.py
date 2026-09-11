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


@pytest.mark.asyncio
async def test_action_authorization_low_and_high_risk(db_session: AsyncSession, tenant_a):
    """Verify LOW risk allowed without approval, HIGH risk returns WAITING_APPROVAL."""
    service = ActionAuthorizationService(db_session)

    # 1. LOW Risk Action -> ALLOW
    low_req = ActionRequest(
        action_type="send_message",
        target="send_message",
        tenant_id=tenant_a.id,
        params={"message": "Hello tenant"},
    )
    low_dec = await service.evaluate_action(low_req)
    assert low_dec.decision == ExecutionDecision.ALLOW
    assert low_dec.risk_level == ActionRiskLevel.LOW

    # 2. HIGH Risk Action without approval -> WAITING_APPROVAL
    high_req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params={"order_id": "ord_123", "amount": 100},
    )
    high_dec = await service.evaluate_action(high_req)
    assert high_dec.decision == ExecutionDecision.WAITING_APPROVAL
    assert high_dec.risk_level == ActionRiskLevel.HIGH


@pytest.mark.asyncio
async def test_critical_risk_requires_approval(db_session: AsyncSession, tenant_a):
    """Verify CRITICAL risk returns WAITING_APPROVAL when no approval_id provided."""
    service = ActionAuthorizationService(db_session)
    crit_req = ActionRequest(
        action_type="delete_customer",
        target="customer_123",
        tenant_id=tenant_a.id,
        params={"customer_id": "c_123"},
    )
    crit_dec = await service.evaluate_action(crit_req)
    assert crit_dec.decision == ExecutionDecision.WAITING_APPROVAL
    assert crit_dec.risk_level == ActionRiskLevel.CRITICAL


@pytest.mark.asyncio
async def test_valid_approval_binding_allows_execution(db_session: AsyncSession, tenant_a):
    """Verify approved action with matching action_hash allows execution."""
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
        requested_by="user_owner",
        action_type="issue_refund",
        target="issue_refund",
        reason="Customer requested refund",
        risk_level="HIGH",
        status="APPROVED",
        decided_by="platform_owner",
        decided_at=datetime.now(timezone.utc),
        meta_data={"params": params, "action_hash": action_hash},
    )
    db_session.add(appr)
    await db_session.commit()
    await db_session.refresh(appr)

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
async def test_approval_status_pending_and_rejected_blocks_execution(db_session: AsyncSession, tenant_a):
    """Verify PENDING and REJECTED approvals block execution with DENY."""
    service = ActionAuthorizationService(db_session)
    params = {"amount": 100}

    # 1. PENDING approval
    pending_appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="ai_agent",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund request",
        risk_level="HIGH",
        status="PENDING",
        meta_data={"params": params},
    )
    db_session.add(pending_appr)
    await db_session.commit()

    pending_req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
        approval_id=pending_appr.id,
    )
    dec = await service.evaluate_action(pending_req)
    assert dec.decision == ExecutionDecision.DENY
    assert "status is PENDING" in dec.reason

    # 2. REJECTED approval
    pending_appr.status = "REJECTED"
    await db_session.commit()

    dec_rej = await service.evaluate_action(pending_req)
    assert dec_rej.decision == ExecutionDecision.DENY
    assert "status is REJECTED" in dec_rej.reason


@pytest.mark.asyncio
async def test_expired_approval_blocks_execution(db_session: AsyncSession, tenant_a):
    """Verify expired approval blocks execution and marks status as EXPIRED."""
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
        meta_data={"params": params},
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
async def test_approval_binding_mismatch_blocks_execution(db_session: AsyncSession, tenant_a):
    """Verify approval with mismatched parameter hash is rejected (wrong approval reuse)."""
    service = ActionAuthorizationService(db_session)

    approved_params = {"amount": 100, "customer_id": "c_1"}
    approved_hash = ActionBinding.compute_hash(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=approved_params,
    )

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="user_owner",
        action_type="issue_refund",
        target="issue_refund",
        reason="Approved refund of 100",
        risk_level="HIGH",
        status="APPROVED",
        meta_data={"params": approved_params, "action_hash": approved_hash},
    )
    db_session.add(appr)
    await db_session.commit()

    # Attempt to use approval with modified parameter amount=10000
    mismatched_req = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params={"amount": 10000, "customer_id": "c_1"}, # Forged parameters
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(mismatched_req)
    assert dec.decision == ExecutionDecision.DENY
    assert "mismatch" in dec.reason.lower()


@pytest.mark.asyncio
async def test_cross_tenant_approval_reuse_denied(db_session: AsyncSession, tenant_a, tenant_b):
    """Verify tenant B cannot execute action using tenant A's approval."""
    service = ActionAuthorizationService(db_session)

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="user_owner",
        action_type="issue_refund",
        target="issue_refund",
        reason="Tenant A refund",
        risk_level="HIGH",
        status="APPROVED",
        meta_data={"params": {"amount": 50}},
    )
    db_session.add(appr)
    await db_session.commit()

    # Tenant B tries to pass tenant A's approval_id
    req_tenant_b = ActionRequest(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_b.id,
        params={"amount": 50},
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(req_tenant_b)
    assert dec.decision == ExecutionDecision.DENY
    assert "Invalid approval request or cross-tenant" in dec.reason


@pytest.mark.asyncio
async def test_owner_ai_self_approval_prohibition(db_session: AsyncSession, tenant_a):
    """Verify Owner AI agent cannot self-approve high risk action."""
    service = ActionAuthorizationService(db_session)

    req = ActionRequest(
        action_type="change_official_price",
        target="product_price",
        tenant_id=tenant_a.id,
        agent_id="owner_ai",
        params={"product_id": "p_1", "new_price": 10},
    )

    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.WAITING_APPROVAL
    assert "Owner AI cannot self-approve" in dec.reason


@pytest.mark.asyncio
async def test_tenant_ai_and_tenant_owner_cannot_access_owner_ai(db_session: AsyncSession, tenant_a):
    """Verify non-platform actors (Tenant AI or Tenant Owner) targeting owner_ai are DENIED."""
    service = ActionAuthorizationService(db_session)

    tenant_owner_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read"},
        is_platform_owner=False,
    )

    req = ActionRequest(
        action_type="owner_ai",
        target="owner_ai",
        tenant_id=tenant_a.id,
        actor=tenant_owner_actor,
        agent_id="ai_sales",
        params={"objective": "Access platform AI secrets"},
    )

    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.DENY
    assert "PERMISSION_DENIED" in dec.reason


@pytest.mark.asyncio
async def test_human_platform_owner_can_execute_owner_ai(db_session: AsyncSession, tenant_a):
    """Verify Human Platform Owner actor is permitted to call owner_ai."""
    service = ActionAuthorizationService(db_session)

    platform_owner_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.read"},
        is_platform_owner=True, # Human Platform Owner
    )

    req = ActionRequest(
        action_type="owner_ai",
        target="owner_ai",
        tenant_id=tenant_a.id,
        actor=platform_owner_actor,
        params={"objective": "Platform AI strategy analysis"},
    )

    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.ALLOW

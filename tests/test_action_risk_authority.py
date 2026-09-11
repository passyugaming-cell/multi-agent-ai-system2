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
# BLOCKER 1: MODIFY_AND_APPROVE SELF-APPROVAL & SECURITY BOUNDARY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_modify_and_approve_owner_ai_self_approval_denied(db_session: AsyncSession, tenant_a):
    """1. Owner AI attempts modify_and_approve() on its own HIGH action -> 403."""
    appr_service = ApprovalService(db_session)
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="agent:owner_ai",
        action_type="change_official_price",
        target="product_price",
        reason="Price change",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr)
    await db_session.commit()

    owner_ai_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner_ai",
        is_platform_owner=True, # Even if platform owner flag was set
    )
    token = set_actor_context(owner_ai_actor)
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.modify_and_approve(
                tenant_a.id, appr.id, decided_by="owner_ai", modified_params={"new_price": 50}, reason="Self approval"
            )
        assert exc_info.value.status_code == 403
        assert "cannot self-approve" in exc_info.value.message
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_modify_and_approve_requesting_specialist_agent_self_approval_denied(db_session: AsyncSession, tenant_a):
    """2. Requesting specialist AI attempts modify_and_approve() on its own HIGH action -> 403."""
    appr_service = ApprovalService(db_session)
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="agent:ai_sales",
        action_type="approve_discount",
        target="customer_123",
        reason="Discount request",
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
            await appr_service.modify_and_approve(
                tenant_a.id, appr.id, decided_by="agent:ai_sales", modified_params={"discount": 10}, reason="Self approve"
            )
        assert exc_info.value.status_code == 403
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_modify_and_approve_human_platform_owner_succeeds(db_session: AsyncSession, tenant_a):
    """3. Legitimate Human Platform Owner performs modify_and_approve() -> SUCCESS."""
    appr_service = ApprovalService(db_session)
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="agent:ai_sales",
        action_type="approve_discount",
        target="customer_123",
        reason="Discount request",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr)
    await db_session.commit()

    platform_owner_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        is_platform_owner=True,
    )
    token = set_actor_context(platform_owner_actor)
    try:
        res = await appr_service.modify_and_approve(
            tenant_a.id, appr.id, decided_by="trusted_human_owner", modified_params={"discount": 10}, reason="Adjusted discount"
        )
        assert res.status == "MODIFIED"
        assert res.meta_data.get("decided_by_is_platform_owner") is True
        assert res.meta_data.get("decided_by_user_id") == str(platform_owner_actor.user_id)
    finally:
        reset_actor_context(token)


@pytest.mark.asyncio
async def test_modify_and_approve_non_platform_actor_spoofing_denied(db_session: AsyncSession, tenant_a):
    """4. Non-platform tenant actor attempts modify_and_approve() while spoofing decided_by="platform_owner" -> 403."""
    appr_service = ApprovalService(db_session)
    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="agent:ai_sales",
        action_type="approve_discount",
        target="customer_123",
        reason="Discount request",
        risk_level="HIGH",
        status="PENDING",
    )
    db_session.add(appr)
    await db_session.commit()

    tenant_owner_actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        is_platform_owner=False, # Tenant Owner, NOT Platform Owner!
    )
    token = set_actor_context(tenant_owner_actor)
    try:
        with pytest.raises(AppError) as exc_info:
            await appr_service.modify_and_approve(
                tenant_a.id, appr.id, decided_by="platform_owner", modified_params={"discount": 10}, reason="Spoof attempt"
            )
        assert exc_info.value.status_code == 403
    finally:
        reset_actor_context(token)


# ============================================================================
# BLOCKER 2: RISK-AWARE APPROVAL IDENTITY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_05_high_action_valid_human_platform_owner_approval_allows(db_session: AsyncSession, tenant_a):
    """5. HIGH action + valid Human Platform Owner approval -> ALLOW."""
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
        decided_by="trusted_platform_owner",
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
async def test_06_high_action_approved_record_without_platform_owner_metadata_denies(db_session: AsyncSession, tenant_a):
    """6. HIGH action + approved record without decided_by_is_platform_owner -> DENY."""
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
        decided_by="some_caller_string",
        decided_at=datetime.now(timezone.utc),
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
async def test_07_high_action_decided_by_is_platform_owner_false_denies(db_session: AsyncSession, tenant_a):
    """7. HIGH action + decided_by_is_platform_owner=False -> DENY."""
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
        decided_by="tenant_member",
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
async def test_08_high_action_requesting_agent_recorded_as_approver_denies(db_session: AsyncSession, tenant_a):
    """8. HIGH action + requesting agent is recorded as approver -> DENY."""
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
        requested_by="ai_sales",
        action_type="issue_refund",
        target="issue_refund",
        reason="Refund",
        risk_level="HIGH",
        status="APPROVED",
        decided_by="ai_sales", # Agent self-approval!
        decided_at=datetime.now(timezone.utc),
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


@pytest.mark.asyncio
async def test_09_medium_action_valid_actor_permission_without_platform_owner_metadata_allows(db_session: AsyncSession, tenant_a):
    """9. MEDIUM action + valid actor permission + approval_id without platform-owner metadata -> MUST NOT be rejected solely because Platform Owner metadata is absent."""
    service = ActionAuthorizationService(db_session)
    params = {"customer_id": "c_123", "name": "Updated"}
    action_hash = ActionBinding.compute_hash(
        action_type="update_customer",
        target="customer_123",
        tenant_id=tenant_a.id,
        params=params,
    )

    appr = Approval(
        tenant_id=tenant_a.id,
        requested_by="user_admin",
        action_type="update_customer",
        target="customer_123",
        reason="Update details",
        risk_level="MEDIUM",
        status="APPROVED",
        decided_by="tenant_admin", # Standard tenant admin without platform owner flag
        decided_at=datetime.now(timezone.utc),
        meta_data={"params": params, "action_hash": action_hash}, # No decided_by_is_platform_owner flag!
    )
    db_session.add(appr)
    await db_session.commit()

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="admin",
        permissions={"business.write", "business.read"}, # Possesses required permission business.write!
    )

    req = ActionRequest(
        action_type="update_customer",
        target="customer_123",
        tenant_id=tenant_a.id,
        actor=actor,
        params=params,
        approval_id=appr.id,
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.ALLOW
    assert dec.risk_level == ActionRiskLevel.MEDIUM


@pytest.mark.asyncio
async def test_10_medium_action_missing_required_permission_denies(db_session: AsyncSession, tenant_a):
    """10. MEDIUM action + missing required permission -> DENY."""
    service = ActionAuthorizationService(db_session)
    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="member",
        permissions={"business.read"}, # Lacks business.write required for update_customer!
    )
    req = ActionRequest(
        action_type="update_customer",
        target="customer_123",
        tenant_id=tenant_a.id,
        actor=actor,
        params={"customer_id": "c_123"},
    )
    dec = await service.evaluate_action(req)
    assert dec.decision == ExecutionDecision.DENY
    assert "PERMISSION_DENIED" in dec.reason


@pytest.mark.asyncio
async def test_11_critical_action_valid_human_platform_owner_approval_allows(db_session: AsyncSession, tenant_a):
    """11. CRITICAL action + valid Human Platform Owner approval -> ALLOW."""
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
        decided_by="trusted_human_platform_owner",
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
async def test_12_critical_action_non_platform_approval_denies(db_session: AsyncSession, tenant_a):
    """12. CRITICAL action + non-platform approval -> DENY."""
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
        decided_by="tenant_admin_user",
        decided_at=datetime.now(timezone.utc),
        meta_data={"params": params, "action_hash": action_hash, "decided_by_is_platform_owner": False},
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
    assert dec.decision == ExecutionDecision.DENY
    assert "Human Platform Owner" in dec.reason


# ============================================================================
# ANTI-BYPASS REGRESSION TESTS
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

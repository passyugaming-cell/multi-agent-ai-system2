import pytest
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.tenants.lifecycle import ClientLifecycleManager
from app.tenants.provisioning.exceptions import InvalidLifecycleTransitionError


@pytest.mark.asyncio
async def test_valid_lifecycle_transitions(db_session: AsyncSession, tenant_a: Tenant) -> None:
    """Verify standard valid forward transitions."""
    mgr = ClientLifecycleManager(db_session)
    assert tenant_a.lifecycle_state == "PROSPECT"

    # PROSPECT -> ONBOARDING
    t1 = await mgr.transition_state(tenant_a.id, "ONBOARDING", reason="Start onboarding")
    assert t1.lifecycle_state == "ONBOARDING"
    assert t1.previous_state == "PROSPECT"

    # ONBOARDING -> CONFIGURING
    t2 = await mgr.transition_state(tenant_a.id, "CONFIGURING", reason="Configuring")
    assert t2.lifecycle_state == "CONFIGURING"
    assert t2.previous_state == "ONBOARDING"

    # CONFIGURING -> VALIDATING
    t3 = await mgr.transition_state(tenant_a.id, "VALIDATING", reason="Validating")
    assert t3.lifecycle_state == "VALIDATING"
    assert t3.previous_state == "CONFIGURING"


@pytest.mark.asyncio
async def test_invalid_lifecycle_transitions_rejected(db_session: AsyncSession, tenant_a: Tenant) -> None:
    """Verify invalid state transitions are rejected."""
    mgr = ClientLifecycleManager(db_session)

    # PROSPECT -> ACTIVE directly must fail
    with pytest.raises(InvalidLifecycleTransitionError):
        await mgr.transition_state(tenant_a.id, "ACTIVE", reason="Jump to active")

    # PROSPECT -> READY directly must fail
    with pytest.raises(InvalidLifecycleTransitionError):
        await mgr.transition_state(tenant_a.id, "READY", reason="Jump to ready")


@pytest.mark.asyncio
async def test_ready_transition_enforces_readiness_score(db_session: AsyncSession, tenant_a: Tenant) -> None:
    """Transitioning to READY must fail if readiness requirements are not met."""
    mgr = ClientLifecycleManager(db_session)

    # Move to CONFIGURING
    await mgr.transition_state(tenant_a.id, "ONBOARDING")
    await mgr.transition_state(tenant_a.id, "CONFIGURING")

    # Trying to transition to READY without completing configuration must fail
    with pytest.raises(InvalidLifecycleTransitionError) as exc_info:
        await mgr.transition_state(tenant_a.id, "READY")

    assert "Readiness score" in str(exc_info.value)


@pytest.mark.asyncio
async def test_archived_is_terminal_state(db_session: AsyncSession, tenant_a: Tenant) -> None:
    """Verify ARCHIVED is a terminal state and cannot transition out."""
    mgr = ClientLifecycleManager(db_session)

    await mgr.transition_state(tenant_a.id, "ARCHIVED", reason="Archiving tenant")
    assert tenant_a.lifecycle_state == "ARCHIVED"

    with pytest.raises(InvalidLifecycleTransitionError):
        await mgr.transition_state(tenant_a.id, "ONBOARDING")

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.core.approvals.service import ApprovalService
from app.core.exceptions import AppException
from app.schemas.phase2 import ApprovalResponse, ApprovalDecisionRequest

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> list[ApprovalResponse]:
    tenant_id = get_tenant_id()
    service = ApprovalService(db)
    approvals = await service.list_approvals(tenant_id, status=status)
    return [
        ApprovalResponse(
            id=str(a.id),
            tenant_id=str(a.tenant_id),
            workflow_execution_id=str(a.workflow_execution_id) if a.workflow_execution_id else None,
            requested_by=a.requested_by,
            action_type=a.action_type,
            target=a.target,
            reason=a.reason,
            risk_level=a.risk_level,
            status=a.status,
        )
        for a in approvals
    ]


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> ApprovalResponse:
    tenant_id = get_tenant_id()
    service = ApprovalService(db)
    try:
        a = await service.get_approval(tenant_id, uuid.UUID(approval_id))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return ApprovalResponse(
        id=str(a.id),
        tenant_id=str(a.tenant_id),
        workflow_execution_id=str(a.workflow_execution_id) if a.workflow_execution_id else None,
        requested_by=a.requested_by,
        action_type=a.action_type,
        target=a.target,
        reason=a.reason,
        risk_level=a.risk_level,
        status=a.status,
    )


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve_request(
    approval_id: str,
    body: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ApprovalResponse:
    tenant_id = get_tenant_id()
    service = ApprovalService(db)
    try:
        if body.modified_params:
            a = await service.modify_and_approve(
                tenant_id=tenant_id,
                approval_id=uuid.UUID(approval_id),
                decided_by=body.decided_by,
                modified_params=body.modified_params,
                reason=body.reason or "Approved with modifications",
            )
        else:
            a = await service.approve(
                tenant_id=tenant_id,
                approval_id=uuid.UUID(approval_id),
                decided_by=body.decided_by,
                reason=body.reason,
            )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return ApprovalResponse(
        id=str(a.id),
        tenant_id=str(a.tenant_id),
        workflow_execution_id=str(a.workflow_execution_id) if a.workflow_execution_id else None,
        requested_by=a.requested_by,
        action_type=a.action_type,
        target=a.target,
        reason=a.reason,
        risk_level=a.risk_level,
        status=a.status,
    )


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
async def reject_request(
    approval_id: str,
    body: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ApprovalResponse:
    tenant_id = get_tenant_id()
    service = ApprovalService(db)
    try:
        a = await service.reject(
            tenant_id=tenant_id,
            approval_id=uuid.UUID(approval_id),
            decided_by=body.decided_by,
            reason=body.reason or "Rejected by reviewer",
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return ApprovalResponse(
        id=str(a.id),
        tenant_id=str(a.tenant_id),
        workflow_execution_id=str(a.workflow_execution_id) if a.workflow_execution_id else None,
        requested_by=a.requested_by,
        action_type=a.action_type,
        target=a.target,
        reason=a.reason,
        risk_level=a.risk_level,
        status=a.status,
    )


@router.post("/{approval_id}/cancel", response_model=ApprovalResponse)
async def cancel_approval(
    approval_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> ApprovalResponse:
    tenant_id = get_tenant_id()
    service = ApprovalService(db)
    try:
        a = await service.get_approval(tenant_id, uuid.UUID(approval_id))
        if a.status != "PENDING":
            raise HTTPException(status_code=400, detail="Cannot cancel non-pending approval")
        a.status = "CANCELLED"
        await db.commit()
        await db.refresh(a)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return ApprovalResponse(
        id=str(a.id),
        tenant_id=str(a.tenant_id),
        workflow_execution_id=str(a.workflow_execution_id) if a.workflow_execution_id else None,
        requested_by=a.requested_by,
        action_type=a.action_type,
        target=a.target,
        reason=a.reason,
        risk_level=a.risk_level,
        status=a.status,
    )

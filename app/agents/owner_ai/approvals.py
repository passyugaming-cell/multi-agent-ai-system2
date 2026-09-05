import uuid
from typing import Any, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.approvals.service import ApprovalService
from app.core.exceptions import AppError


class ApprovalRouter:
    """Routes and explains pending approval requests to the Human Owner. Owner AI CANNOT approve high-risk actions itself."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session
        self.approval_service = ApprovalService(db_session)

    async def get_pending_approvals_with_explanations(
        self, tenant_id: uuid.UUID
    ) -> List[Dict[str, Any]]:
        approvals = await self.approval_service.list_approvals(tenant_id, status="PENDING")
        result = []

        for appr in approvals:
            explanation = {
                "approval_id": str(appr.id),
                "tenant_id": str(appr.tenant_id),
                "requested_by": appr.requested_by,
                "action_type": appr.action_type,
                "target": appr.target,
                "risk_level": appr.risk_level,
                "reason": appr.reason,
                "expected_result": appr.expected_result,
                "confidence": appr.confidence,
                "evidence": appr.evidence,
                "status": appr.status,
                "explanation_summary": (
                    f"Action '{appr.action_type}' requested on target '{appr.target}'. "
                    f"Risk level: {appr.risk_level}. Reason: {appr.reason}. "
                    "Requires explicit Human Owner decision."
                ),
                "owner_action_required": True,
            }
            result.append(explanation)

        return result

    def validate_owner_authority(self, is_high_risk: bool, action_type: str) -> None:
        """Enforces that Owner AI cannot self-approve high-risk or critical actions."""
        if is_high_risk or action_type in [
            "change_official_price",
            "issue_refund",
            "change_critical_config",
            "delete_critical_data",
            "modify_security_policy",
        ]:
            raise AppError(
                f"Owner AI is forbidden from self-approving high-risk action '{action_type}'. Human Owner approval is strictly required.",
                status_code=403,
            )

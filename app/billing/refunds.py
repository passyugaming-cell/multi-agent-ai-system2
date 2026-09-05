import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.billing import Payment
from app.database.models.workflow import Approval
from app.billing.payments import PaymentService
from app.billing.state_machine import PaymentStatus, validate_payment_transition
from app.billing.exceptions import PaymentFailedError, BillingError
from app.billing.events import publish_billing_event


class RefundService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session
        self.payment_service = PaymentService(db_session)

    async def request_refund(
        self,
        tenant_id: uuid.UUID,
        payment_id: uuid.UUID,
        amount: Decimal,
        reason: str,
        requested_by: str = "CUSTOMER",
    ) -> Approval:
        """Creates a high-risk financial Approval request for human owner decision."""
        payment = await self.payment_service.get_payment(tenant_id, payment_id)

        if payment.status != PaymentStatus.SUCCEEDED:
            raise BillingError(f"Cannot refund payment in status '{payment.status}'. Must be SUCCEEDED.")

        if amount > payment.amount:
            raise BillingError(f"Refund amount ({amount}) exceeds payment amount ({payment.amount}).")

        now = datetime.now(timezone.utc)
        approval = Approval(
            tenant_id=tenant_id,
            action_type="issue_refund",
            target=f"payment_{payment_id}",
            risk_level="CRITICAL",
            requested_by=requested_by,
            reason=f"Refund request for payment {payment_id}: {reason}",
            status="PENDING",
            requested_at=now,
            meta_data={
                "payment_id": str(payment_id),
                "amount": str(amount),
                "reason": reason,
            },
        )
        self.session.add(approval)
        await self.session.flush()

        await publish_billing_event(
            event_type="refund.requested",
            tenant_id=tenant_id,
            payload={
                "approval_id": str(approval.id),
                "payment_id": str(payment_id),
                "amount": str(amount),
                "reason": reason,
            },
            source="refund_service",
        )

        return approval

    async def execute_approved_refund(
        self,
        tenant_id: uuid.UUID,
        approval_id: uuid.UUID,
    ) -> Payment:
        """Executes refund after approval by Human Owner."""
        stmt = select(Approval).where(
            and_(
                Approval.id == approval_id,
                Approval.tenant_id == tenant_id,
                Approval.action_type == "issue_refund",
            )
        )
        approval = (await self.session.execute(stmt)).scalar_one_or_none()

        if not approval:
            raise BillingError(f"Refund approval request '{approval_id}' not found.")

        if approval.status != "APPROVED":
            raise BillingError(f"Refund approval request is in status '{approval.status}', expected APPROVED.")

        payment_id = uuid.UUID(approval.meta_data["payment_id"])
        refund_amount = Decimal(approval.meta_data["amount"])

        payment = await self.payment_service.get_payment(tenant_id, payment_id)
        validate_payment_transition(payment.status, PaymentStatus.REFUNDED)

        # Call payment provider to process refund
        res = await self.payment_service.provider.refund(
            provider_payment_id=payment.provider_payment_id or str(payment.id),
            amount=refund_amount,
            reason=approval.meta_data.get("reason"),
        )

        if not res.success:
            raise PaymentFailedError(res.error_message or "Provider refund failed.")

        payment.status = PaymentStatus.REFUNDED

        await self.session.flush()

        await publish_billing_event(
            event_type="payment.refunded",
            tenant_id=tenant_id,
            payload={
                "payment_id": str(payment.id),
                "refund_amount": str(refund_amount),
                "approval_id": str(approval.id),
                "decided_by": approval.decided_by,
            },
            source="refund_service",
        )

        return payment

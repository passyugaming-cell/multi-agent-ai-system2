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

        if payment.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED):
            raise BillingError(f"Cannot refund payment in status '{payment.status}'. Must be SUCCEEDED or PARTIALLY_REFUNDED.")

        current_refunded = getattr(payment, "refunded_amount", Decimal("0.00")) or Decimal("0.00")
        remaining_refundable = payment.amount - current_refunded

        if amount > remaining_refundable:
            raise BillingError(
                f"Refund amount ({amount}) exceeds remaining refundable amount ({remaining_refundable})."
            )

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
        """Executes refund idempotently and atomically after approval by Human Owner."""
        # R2-002-P1-002: Atomic claim/lock on Approval record
        stmt_app = select(Approval).where(
            and_(
                Approval.id == approval_id,
                Approval.tenant_id == tenant_id,
                Approval.action_type == "issue_refund",
            )
        ).with_for_update()
        approval = (await self.session.execute(stmt_app)).scalar_one_or_none()

        if not approval:
            raise BillingError(f"Refund approval request '{approval_id}' not found.")

        if approval.status == "EXECUTED":
            # Idempotent return if already executed
            payment_id = uuid.UUID(approval.meta_data["payment_id"])
            return await self.payment_service.get_payment(tenant_id, payment_id)

        if approval.status != "APPROVED":
            raise BillingError(f"Refund approval request is in status '{approval.status}', expected APPROVED.")

        payment_id = uuid.UUID(approval.meta_data["payment_id"])
        refund_amount = Decimal(str(approval.meta_data["amount"]))

        # R2-002 FOLLOW-UP: Lock target Payment row FIRST with with_for_update before reading refunded_amount
        stmt_pmt = select(Payment).where(
            and_(Payment.id == payment_id, Payment.tenant_id == tenant_id)
        ).with_for_update()
        payment = (await self.session.execute(stmt_pmt)).scalar_one_or_none()

        if not payment:
            raise BillingError(f"Payment record '{payment_id}' not found.")

        current_refunded = getattr(payment, "refunded_amount", Decimal("0.00")) or Decimal("0.00")
        remaining_refundable = payment.amount - current_refunded

        if refund_amount > remaining_refundable:
            approval.status = "FAILED"
            approval.meta_data = dict(approval.meta_data or {}, failure_reason="Refund amount exceeds remaining refundable amount.")
            await self.session.commit()
            raise BillingError(
                f"Refund amount ({refund_amount}) exceeds remaining refundable amount ({remaining_refundable})."
            )

        new_total_refunded = current_refunded + refund_amount
        target_status = PaymentStatus.REFUNDED if new_total_refunded >= payment.amount else PaymentStatus.PARTIALLY_REFUNDED

        validate_payment_transition(payment.status, target_status)

        # R2-002-P1-001: Refund failure persistence
        res = await self.payment_service.provider.refund(
            provider_payment_id=payment.provider_payment_id or str(payment.id),
            amount=refund_amount,
            reason=approval.meta_data.get("reason"),
        )

        if not res.success:
            approval.status = "FAILED"
            approval.meta_data = dict(approval.meta_data or {}, failure_reason=res.error_message or "Provider refund failed.")
            await self.session.commit()
            await publish_billing_event(
                event_type="refund.failed",
                tenant_id=tenant_id,
                payload={
                    "payment_id": str(payment.id),
                    "approval_id": str(approval.id),
                    "error": res.error_message or "Provider refund failed.",
                },
                source="refund_service",
            )
            raise PaymentFailedError(res.error_message or "Provider refund failed.")

        # Atomic state updates on provider success
        approval.status = "EXECUTED"
        payment.refunded_amount = new_total_refunded
        payment.status = target_status

        await self.session.commit()

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

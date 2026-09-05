import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.billing import Payment, Invoice, Subscription, Plan
from app.billing.invoices import InvoiceService
from app.billing.subscription import SubscriptionService
from app.billing.state_machine import PaymentStatus, InvoiceStatus, validate_payment_transition
from app.billing.exceptions import PaymentFailedError
from app.billing.provider import PaymentProvider, FakePaymentProvider, WebhookResult
from app.billing.events import publish_billing_event


class PaymentService:
    def __init__(self, db_session: AsyncSession, provider: PaymentProvider | None = None) -> None:
        self.session = db_session
        self.provider = provider or FakePaymentProvider()
        self.invoice_service = InvoiceService(db_session)
        self.sub_service = SubscriptionService(db_session)

    async def get_payment(self, tenant_id: uuid.UUID, payment_id: uuid.UUID) -> Payment:
        stmt = select(Payment).where(and_(Payment.id == payment_id, Payment.tenant_id == tenant_id))
        payment = (await self.session.execute(stmt)).scalar_one_or_none()
        if not payment:
            raise PaymentFailedError(f"Payment record '{payment_id}' not found.")
        return payment

    async def list_payments(self, tenant_id: uuid.UUID) -> Sequence[Payment]:
        stmt = select(Payment).where(Payment.tenant_id == tenant_id).order_by(Payment.created_at.desc())
        return (await self.session.execute(stmt)).scalars().all()

    async def create_payment_intent(
        self,
        tenant_id: uuid.UUID,
        invoice_id: uuid.UUID,
        amount: Decimal,
        currency: str = "IDR",
    ) -> Payment:
        invoice = await self.invoice_service.get_invoice(tenant_id, invoice_id)

        now = datetime.now(timezone.utc)
        result = await self.provider.create_payment(tenant_id, invoice_id, amount, currency)

        payment = Payment(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            amount=amount,
            currency=currency,
            status=PaymentStatus.PENDING,
            provider="fake",
            provider_payment_id=result.provider_payment_id,
            attempted_at=now,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def confirm_payment_success(
        self,
        tenant_id: uuid.UUID,
        payment_id: uuid.UUID,
        provider_payment_id: str | None = None,
    ) -> Payment:
        """Idempotently confirms payment success, updates invoice to PAID, and reactivates subscription."""
        payment = await self.get_payment(tenant_id, payment_id)

        if payment.status == PaymentStatus.SUCCEEDED:
            return payment  # Idempotent return

        validate_payment_transition(payment.status, PaymentStatus.SUCCEEDED)
        now = datetime.now(timezone.utc)

        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = now
        if provider_payment_id:
            payment.provider_payment_id = provider_payment_id

        # Update invoice to PAID
        await self.invoice_service.update_status(tenant_id, payment.invoice_id, InvoiceStatus.PAID)

        # Reactivate/Activate subscription
        invoice = await self.invoice_service.get_invoice(tenant_id, payment.invoice_id)
        if invoice.subscription_id:
            sub = await self.sub_service.get_subscription(tenant_id)
            plan_stmt = select(Subscription.plan_id).where(Subscription.id == sub.id)
            plan_id = (await self.session.execute(plan_stmt)).scalar_one()

            p_stmt = select(Plan.code).where(Plan.id == plan_id)
            p_code = (await self.session.execute(p_stmt)).scalar_one()

            await self.sub_service.activate_subscription(
                tenant_id=tenant_id,
                plan_code=p_code,
                billing_cycle=sub.billing_cycle,
                actor="PAYMENT_PROVIDER",
            )

        await self.session.flush()

        await publish_billing_event(
            event_type="payment.succeeded",
            tenant_id=tenant_id,
            payload={
                "payment_id": str(payment.id),
                "invoice_id": str(payment.invoice_id),
                "amount": str(payment.amount),
                "provider_payment_id": payment.provider_payment_id,
            },
            source="payment_service",
        )

        return payment

    async def record_payment_failure(
        self,
        tenant_id: uuid.UUID,
        payment_id: uuid.UUID,
        reason: str,
    ) -> Payment:
        payment = await self.get_payment(tenant_id, payment_id)

        if payment.status == PaymentStatus.FAILED:
            return payment

        validate_payment_transition(payment.status, PaymentStatus.FAILED)
        now = datetime.now(timezone.utc)

        payment.status = PaymentStatus.FAILED
        payment.failed_at = now
        payment.failure_reason = reason

        # Apply payment failure policy (Day 0 past_due)
        await self.sub_service.update_payment_failure_status(tenant_id, days_past_due=0)

        await self.session.flush()

        await publish_billing_event(
            event_type="payment.failed",
            tenant_id=tenant_id,
            payload={
                "payment_id": str(payment.id),
                "invoice_id": str(payment.invoice_id),
                "reason": reason,
            },
            source="payment_service",
        )

        return payment

    async def handle_provider_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        secret: str = "test_webhook_secret",
    ) -> Payment:
        """Processes payment provider webhook idempotently."""
        webhook_res: WebhookResult = await self.provider.handle_webhook(payload, headers, secret)

        stmt = select(Payment).where(
            and_(
                Payment.tenant_id == webhook_res.tenant_id,
                Payment.provider_payment_id == webhook_res.provider_payment_id,
            )
        )
        payment = (await self.session.execute(stmt)).scalar_one_or_none()

        if not payment:
            payment = Payment(
                tenant_id=webhook_res.tenant_id,
                invoice_id=webhook_res.invoice_id,
                amount=webhook_res.amount,
                currency="IDR",
                status=PaymentStatus.PENDING,
                provider="webhook",
                provider_payment_id=webhook_res.provider_payment_id,
                attempted_at=datetime.now(timezone.utc),
            )
            self.session.add(payment)
            await self.session.flush()

        if webhook_res.status == "SUCCEEDED" or webhook_res.event_type == "payment.succeeded":
            return await self.confirm_payment_success(
                tenant_id=webhook_res.tenant_id,
                payment_id=payment.id,
                provider_payment_id=webhook_res.provider_payment_id,
            )
        elif webhook_res.status == "FAILED" or webhook_res.event_type == "payment.failed":
            return await self.record_payment_failure(
                tenant_id=webhook_res.tenant_id,
                payment_id=payment.id,
                reason="Failed via provider webhook",
            )

        return payment

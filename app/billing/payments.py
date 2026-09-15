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
from app.billing.exceptions import PaymentFailedError, PaymentConfigurationError
from app.billing.provider import PaymentProvider, FakePaymentProvider, MidtransPaymentProvider, WebhookResult
from app.billing.events import publish_billing_event


def get_default_payment_provider() -> PaymentProvider:
    from app.core.config import settings
    env = (settings.APP_ENV or "").lower()
    if env in ("production", "staging"):
        provider_type = (settings.PAYMENT_PROVIDER or "").lower()
        if not provider_type or provider_type == "fake":
            raise PaymentConfigurationError(
                "FakePaymentProvider is forbidden in production or staging environment. "
                "An explicit production payment provider must be configured."
            )
        elif provider_type == "midtrans":
            if not settings.MIDTRANS_SERVER_KEY or "mock" in settings.MIDTRANS_SERVER_KEY.lower():
                raise PaymentConfigurationError(
                    "MIDTRANS_SERVER_KEY is missing or invalid. Midtrans payment provider configuration is incomplete."
                )
            return MidtransPaymentProvider(
                server_key=settings.MIDTRANS_SERVER_KEY,
                is_sandbox=settings.MIDTRANS_IS_SANDBOX,
            )
        else:
            raise PaymentConfigurationError(
                f"Unsupported production payment provider: '{settings.PAYMENT_PROVIDER}'"
            )
    elif env in ("development", "testing"):
        provider_type = (settings.PAYMENT_PROVIDER or "").lower()
        if provider_type == "midtrans" and settings.MIDTRANS_SERVER_KEY and "mock" not in settings.MIDTRANS_SERVER_KEY.lower():
            return MidtransPaymentProvider(
                server_key=settings.MIDTRANS_SERVER_KEY,
                is_sandbox=settings.MIDTRANS_IS_SANDBOX,
            )
        return FakePaymentProvider()
    else:
        raise PaymentConfigurationError(
            f"Invalid or unknown application environment: '{settings.APP_ENV}'"
        )


class PaymentService:
    def __init__(self, db_session: AsyncSession, provider: PaymentProvider | None = None) -> None:
        self.session = db_session
        if provider is None:
            self.provider = get_default_payment_provider()
        else:
            from app.core.config import settings
            p_name = getattr(provider, "provider_name", None)
            if not p_name or not isinstance(p_name, str) or not p_name.strip():
                raise PaymentConfigurationError(
                    "PaymentProvider passed to PaymentService must have a valid non-empty 'provider_name' attribute."
                )
            p_name_clean = p_name.strip().lower()
            env = (settings.APP_ENV or "").lower()
            if env in ("production", "staging") and p_name_clean == "fake":
                raise PaymentConfigurationError(
                    "FakePaymentProvider cannot be used in production or staging environment."
                )
            self.provider = provider
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
        amount: Decimal | None = None,
        currency: str | None = None,
    ) -> Payment:
        invoice = await self.invoice_service.get_invoice(tenant_id, invoice_id)

        # R2-002-P1-004: Strict tenant ownership invariant
        if invoice.tenant_id != tenant_id:
            raise PaymentFailedError(
                f"Tenant ID mismatch: invoice tenant '{invoice.tenant_id}' does not match request tenant '{tenant_id}'."
            )

        # R2-002-P0-003: Derive authoritative amount and currency from invoice if missing or mismatch
        auth_amount = invoice.total
        auth_currency = invoice.currency

        if amount is not None and amount != auth_amount:
            raise PaymentFailedError(
                f"Payment amount mismatch: requested '{amount}' does not match authoritative invoice total '{auth_amount}'."
            )
        if currency is not None and currency.upper() != auth_currency.upper():
            raise PaymentFailedError(
                f"Payment currency mismatch: requested '{currency}' does not match authoritative invoice currency '{auth_currency}'."
            )

        now = datetime.now(timezone.utc)
        result = await self.provider.create_payment(tenant_id, invoice_id, auth_amount, auth_currency)

        if not result.success:
            raise PaymentFailedError(
                f"Payment provider creation failed: {result.error_message or 'Unknown provider error'}"
            )

        provider_name = getattr(self.provider, "provider_name", None) or "unknown"

        payment = Payment(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            amount=auth_amount,
            currency=auth_currency,
            status=PaymentStatus.PENDING,
            provider=provider_name,
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
                verified_payment=True,
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
        """Processes payment provider webhook idempotently, deterministically, and with atomic concurrency safety."""
        webhook_res: WebhookResult = await self.provider.handle_webhook(payload, headers, secret)

        # R2-002-P0-006: Unmatched Webhook Policy
        # Verify that referenced invoice exists and belongs to the specified tenant.
        # Catch ONLY InvoiceNotFoundError so DB/connection errors propagate directly as infrastructure failures.
        from app.billing.exceptions import InvoiceNotFoundError
        try:
            invoice = await self.invoice_service.get_invoice(
                tenant_id=webhook_res.tenant_id,
                invoice_id=webhook_res.invoice_id,
            )
        except InvoiceNotFoundError as err:
            raise PaymentFailedError(
                f"Unmatched webhook rejected: invoice '{webhook_res.invoice_id}' not found for tenant '{webhook_res.tenant_id}'."
            ) from err

        if invoice.tenant_id != webhook_res.tenant_id:
            raise PaymentFailedError(
                f"Unmatched webhook rejected: invoice tenant '{invoice.tenant_id}' mismatch with webhook tenant '{webhook_res.tenant_id}'."
            )

        # R2-002 FOLLOW-UP: Verify webhook amount AND currency match authoritative invoice total and currency
        if webhook_res.amount != invoice.total:
            raise PaymentFailedError(
                f"Unmatched webhook rejected: webhook amount '{webhook_res.amount}' does not match invoice total '{invoice.total}'."
            )
        if (webhook_res.currency or "").upper() != invoice.currency.upper():
            raise PaymentFailedError(
                f"Unmatched webhook rejected: currency mismatch. Webhook currency '{webhook_res.currency}' does not match invoice currency '{invoice.currency}'."
            )

        provider_name = getattr(self.provider, "provider_name", None) or "unknown"

        # R2-002 FOLLOW-UP: Lock and resolve legitimate internal Payment intent.
        # DO NOT blindly create a Payment if no internal intent exists!
        stmt = select(Payment).where(
            and_(
                Payment.tenant_id == webhook_res.tenant_id,
                Payment.provider == provider_name,
                Payment.provider_payment_id == webhook_res.provider_payment_id,
            )
        ).with_for_update()
        payment = (await self.session.execute(stmt)).scalar_one_or_none()

        if not payment:
            # Attempt to find payment by invoice_id if provider_payment_id was not populated during creation
            stmt_inv = select(Payment).where(
                and_(
                    Payment.tenant_id == webhook_res.tenant_id,
                    Payment.invoice_id == webhook_res.invoice_id,
                    Payment.status == PaymentStatus.PENDING,
                )
            ).with_for_update()
            payment = (await self.session.execute(stmt_inv)).scalar_one_or_none()

        # R2-002-P0-006 REPAIR: If no legitimate internal Payment record exists, REJECT!
        if not payment:
            raise PaymentFailedError(
                f"Unmatched webhook rejected: no matching internal payment intent found for invoice '{webhook_res.invoice_id}' and provider payment ID '{webhook_res.provider_payment_id}'."
            )

        # Single State Authority route
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

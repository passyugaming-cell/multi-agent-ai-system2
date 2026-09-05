import hmac
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
import uuid


@dataclass
class PaymentResult:
    success: bool
    provider_payment_id: str
    status: str
    error_message: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass
class RefundResult:
    success: bool
    refund_id: str
    amount: Decimal
    error_message: str | None = None


@dataclass
class WebhookResult:
    event_type: str
    provider_payment_id: str
    amount: Decimal
    status: str
    tenant_id: uuid.UUID
    invoice_id: uuid.UUID


class PaymentProvider(ABC):
    @abstractmethod
    async def create_payment(
        self,
        tenant_id: uuid.UUID,
        invoice_id: uuid.UUID,
        amount: Decimal,
        currency: str = "IDR",
        metadata: dict[str, Any] | None = None,
    ) -> PaymentResult:
        pass

    @abstractmethod
    async def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        pass

    @abstractmethod
    async def refund(
        self,
        provider_payment_id: str,
        amount: Decimal,
        reason: str | None = None,
    ) -> RefundResult:
        pass

    @abstractmethod
    async def handle_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        secret: str = "test_webhook_secret",
    ) -> WebhookResult:
        pass


class FakePaymentProvider(PaymentProvider):
    """Fake Payment Provider for testing and local development."""

    def __init__(self, secret: str = "test_webhook_secret") -> None:
        self.secret = secret

    async def create_payment(
        self,
        tenant_id: uuid.UUID,
        invoice_id: uuid.UUID,
        amount: Decimal,
        currency: str = "IDR",
        metadata: dict[str, Any] | None = None,
    ) -> PaymentResult:
        provider_id = f"pay_fake_{uuid.uuid4().hex[:12]}"
        return PaymentResult(
            success=True,
            provider_payment_id=provider_id,
            status="PENDING",
            raw_response={"mock": True, "tenant_id": str(tenant_id), "invoice_id": str(invoice_id)},
        )

    async def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        return PaymentResult(
            success=True,
            provider_payment_id=provider_payment_id,
            status="SUCCEEDED",
        )

    async def refund(
        self,
        provider_payment_id: str,
        amount: Decimal,
        reason: str | None = None,
    ) -> RefundResult:
        refund_id = f"ref_fake_{uuid.uuid4().hex[:12]}"
        return RefundResult(
            success=True,
            refund_id=refund_id,
            amount=amount,
        )

    async def handle_webhook(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        secret: str | None = None,
    ) -> WebhookResult:
        sec = secret or self.secret
        sig = headers.get("x-signature") or headers.get("X-Signature")

        if sig:
            body_bytes = str(payload).encode("utf-8")
            expected_sig = hmac.new(sec.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
            if sig != expected_sig and sig != "valid_test_signature":
                from app.billing.exceptions import WebhookVerificationError
                raise WebhookVerificationError("Invalid webhook signature.")

        event_type = payload.get("event", "payment.succeeded")
        payment_id = payload.get("provider_payment_id") or f"pay_fake_{uuid.uuid4().hex[:8]}"
        amount = Decimal(str(payload.get("amount", "0.00")))
        tenant_id = uuid.UUID(payload["tenant_id"])
        invoice_id = uuid.UUID(payload["invoice_id"])
        status = payload.get("status", "SUCCEEDED")

        return WebhookResult(
            event_type=event_type,
            provider_payment_id=payment_id,
            amount=amount,
            status=status,
            tenant_id=tenant_id,
            invoice_id=invoice_id,
        )

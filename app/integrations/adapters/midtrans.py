import hmac
import hashlib
import logging
from typing import Any
from decimal import Decimal
import uuid
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.interfaces import IntegrationAdapter
from app.integrations.exceptions import (
    PermanentIntegrationError,
    TransientIntegrationError,
    IntegrationNotFoundError,
)

logger = logging.getLogger(__name__)

SANDBOX_BASE_URL = "https://api.sandbox.midtrans.com/v2"
PRODUCTION_BASE_URL = "https://api.midtrans.com/v2"

SANDBOX_SNAP_URL = "https://app.sandbox.midtrans.com/snap/v1"
PRODUCTION_SNAP_URL = "https://app.midtrans.com/snap/v1"


class MidtransAdapter(IntegrationAdapter):
    """
    Adapter for Midtrans Payment Gateway.
    Supports Core API & Snap API operations with Decimal monetary safety and SHA-512 signature verification.
    """

    def __init__(self, is_sandbox: bool = True) -> None:
        self.is_sandbox = is_sandbox

    def _get_base_url(self, credentials: dict[str, Any]) -> str:
        is_sandbox = credentials.get("is_sandbox", self.is_sandbox)
        if isinstance(is_sandbox, str):
            is_sandbox = is_sandbox.lower() in ("true", "1", "yes")
        return SANDBOX_BASE_URL if is_sandbox else PRODUCTION_BASE_URL

    def _get_headers(self, server_key: str) -> dict[str, str]:
        import base64
        auth_str = f"{server_key}:"
        encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded_auth}",
        }

    async def connect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        server_key = credentials.get("server_key")
        if not server_key:
            raise PermanentIntegrationError("Midtrans 'server_key' is required.", error_code="AUTHENTICATION_ERROR")
        return True

    async def disconnect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> bool:
        return True

    async def execute(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        operation: str,
        params: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        server_key = credentials.get("server_key")
        if not server_key:
            raise PermanentIntegrationError("Midtrans server_key missing.", error_code="AUTHENTICATION_ERROR")

        if operation == "create_payment":
            return await self.create_payment(credentials, params)
        elif operation == "get_payment_status":
            order_id = params.get("order_id") or params.get("transaction_id")
            if not order_id:
                raise PermanentIntegrationError("order_id or transaction_id is required.", error_code="VALIDATION_ERROR")
            return await self.get_payment_status(credentials, order_id)
        elif operation == "cancel_payment":
            order_id = params.get("order_id") or params.get("transaction_id")
            if not order_id:
                raise PermanentIntegrationError("order_id or transaction_id is required.", error_code="VALIDATION_ERROR")
            return await self.cancel_payment(credentials, order_id)
        elif operation == "refund_payment":
            order_id = params.get("order_id") or params.get("transaction_id")
            amount = params.get("amount")
            reason = params.get("reason", "Refund requested")
            if not order_id or amount is None:
                raise PermanentIntegrationError("order_id and amount are required for refund.", error_code="VALIDATION_ERROR")
            return await self.refund_payment(credentials, order_id, Decimal(str(amount)), reason)
        else:
            raise PermanentIntegrationError(f"Unsupported Midtrans operation: {operation}", error_code="INVALID_OPERATION")

    async def create_payment(
        self, credentials: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        server_key = credentials.get("server_key")
        order_id = params.get("order_id")
        gross_amount = params.get("gross_amount") or params.get("amount")

        if not order_id or gross_amount is None:
            raise PermanentIntegrationError("order_id and gross_amount are required.", error_code="VALIDATION_ERROR")

        amount_dec = Decimal(str(gross_amount))
        if amount_dec <= Decimal("0"):
            raise PermanentIntegrationError("Payment amount must be greater than zero.", error_code="VALIDATION_ERROR")

        base_url = self._get_base_url(credentials)
        headers = self._get_headers(server_key)

        payload = {
            "payment_type": params.get("payment_type", "bank_transfer"),
            "transaction_details": {
                "order_id": str(order_id),
                "gross_amount": int(amount_dec) if amount_dec == amount_dec.to_integral_value() else float(amount_dec),
            },
        }
        if "customer_details" in params:
            payload["customer_details"] = params["customer_details"]
        if "item_details" in params:
            payload["item_details"] = params["item_details"]
        if "bank_transfer" in params:
            payload["bank_transfer"] = params["bank_transfer"]

        endpoint = f"{base_url}/charge"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "success": True,
                    "order_id": str(order_id),
                    "transaction_id": data.get("transaction_id"),
                    "transaction_status": data.get("transaction_status", "pending"),
                    "gross_amount": str(amount_dec),
                    "raw_response": data,
                }
            else:
                data = resp.json() if resp.content else {}
                err_msg = data.get("status_message") or f"Midtrans HTTP {resp.status_code}"
                return {
                    "success": False,
                    "order_id": str(order_id),
                    "transaction_status": "failed",
                    "error_message": err_msg,
                    "raw_response": data,
                }

    async def get_payment_status(
        self, credentials: dict[str, Any], order_id_or_transaction_id: str
    ) -> dict[str, Any]:
        server_key = credentials.get("server_key")
        base_url = self._get_base_url(credentials)
        headers = self._get_headers(server_key)

        endpoint = f"{base_url}/{order_id_or_transaction_id}/status"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(endpoint, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                norm_status = self.normalize_notification(data)
                return {
                    "success": True,
                    "order_id": data.get("order_id"),
                    "transaction_id": data.get("transaction_id"),
                    "transaction_status": data.get("transaction_status"),
                    "normalized_status": norm_status,
                    "gross_amount": data.get("gross_amount"),
                    "raw_response": data,
                }
            elif resp.status_code == 404:
                raise IntegrationNotFoundError(f"Midtrans transaction not found for ID: {order_id_or_transaction_id}")
            else:
                data = resp.json() if resp.content else {}
                err_msg = data.get("status_message") or f"Midtrans HTTP {resp.status_code}"
                raise PermanentIntegrationError(err_msg, error_code="PROVIDER_ERROR")

    async def cancel_payment(
        self, credentials: dict[str, Any], order_id_or_transaction_id: str
    ) -> dict[str, Any]:
        server_key = credentials.get("server_key")
        base_url = self._get_base_url(credentials)
        headers = self._get_headers(server_key)

        endpoint = f"{base_url}/{order_id_or_transaction_id}/cancel"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "success": True,
                    "order_id": data.get("order_id"),
                    "transaction_id": data.get("transaction_id"),
                    "transaction_status": data.get("transaction_status", "cancel"),
                    "raw_response": data,
                }
            else:
                data = resp.json() if resp.content else {}
                err_msg = data.get("status_message") or f"Midtrans HTTP {resp.status_code}"
                return {
                    "success": False,
                    "error_message": err_msg,
                    "raw_response": data,
                }

    async def refund_payment(
        self,
        credentials: dict[str, Any],
        order_id_or_transaction_id: str,
        amount: Decimal,
        reason: str = "Refund requested",
    ) -> dict[str, Any]:
        server_key = credentials.get("server_key")
        base_url = self._get_base_url(credentials)
        headers = self._get_headers(server_key)

        if amount <= Decimal("0"):
            raise PermanentIntegrationError("Refund amount must be greater than zero.", error_code="VALIDATION_ERROR")

        payload = {
            "refund_key": f"ref_{uuid.uuid4().hex[:12]}",
            "amount": int(amount) if amount == amount.to_integral_value() else float(amount),
            "reason": reason,
        }

        endpoint = f"{base_url}/{order_id_or_transaction_id}/refund"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "success": True,
                    "order_id": data.get("order_id"),
                    "transaction_id": data.get("transaction_id"),
                    "refund_amount": str(amount),
                    "transaction_status": data.get("transaction_status", "refund"),
                    "raw_response": data,
                }
            else:
                data = resp.json() if resp.content else {}
                err_msg = data.get("status_message") or f"Midtrans HTTP {resp.status_code}"
                return {
                    "success": False,
                    "error_message": err_msg,
                    "raw_response": data,
                }

    def verify_notification(self, payload: dict[str, Any], server_key: str) -> bool:
        """
        Verifies Midtrans HTTP notification signature_key.
        SHA-512(order_id + status_code + gross_amount + ServerKey)
        Uses hmac.compare_digest for constant-time comparison.
        """
        signature_key = payload.get("signature_key")
        if not signature_key:
            return False

        order_id = payload.get("order_id", "")
        status_code = payload.get("status_code", "")
        gross_amount = payload.get("gross_amount", "")

        raw_str = f"{order_id}{status_code}{gross_amount}{server_key}"
        calculated_sig = hashlib.sha512(raw_str.encode("utf-8")).hexdigest()

        return hmac.compare_digest(signature_key.lower(), calculated_sig.lower())

    def normalize_notification(self, payload: dict[str, Any]) -> str:
        """
        Maps Midtrans transaction_status & fraud_status to internal Payment status:
        - capture + accept -> SUCCEEDED
        - settlement -> SUCCEEDED
        - pending -> PENDING
        - deny / cancel / expire -> FAILED / CANCELLED / EXPIRED
        - refund / partial_refund -> REFUNDED
        """
        tx_status = payload.get("transaction_status", "").lower()
        fraud_status = payload.get("fraud_status", "").lower()

        if tx_status == "capture":
            if fraud_status == "challenge":
                return "PENDING"
            return "SUCCEEDED"
        elif tx_status == "settlement":
            return "SUCCEEDED"
        elif tx_status == "pending":
            return "PENDING"
        elif tx_status in ("deny", "failure"):
            return "FAILED"
        elif tx_status == "cancel":
            return "CANCELLED"
        elif tx_status == "expire":
            return "EXPIRED"
        elif tx_status in ("refund", "partial_refund"):
            return "REFUNDED"
        else:
            return "FAILED"

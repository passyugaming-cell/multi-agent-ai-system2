import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Sequence, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.billing import Invoice, InvoiceItem, Subscription
from app.billing.state_machine import InvoiceStatus, validate_invoice_transition
from app.billing.exceptions import InvoiceNotFoundError


class RevenueType:
    SUBSCRIPTION = "SUBSCRIPTION"
    SETUP = "SETUP"
    ADD_ON = "ADD_ON"
    CUSTOM_SERVICE = "CUSTOM_SERVICE"


SETUP_FEE_PRICES = {
    "basic": Decimal("299000.00"),
    "advanced": Decimal("799000.00"),
    "custom": Decimal("1500000.00"),
}


def generate_invoice_number() -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rand_suffix = str(uuid.uuid4())[:6].upper()
    return f"INV-{now_str}-{rand_suffix}"


class InvoiceService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_invoice(self, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
        stmt = select(Invoice).where(and_(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id))
        inv = (await self.session.execute(stmt)).scalar_one_or_none()
        if not inv:
            raise InvoiceNotFoundError(str(invoice_id))
        return inv

    async def list_invoices(self, tenant_id: uuid.UUID, status: str | None = None) -> Sequence[Invoice]:
        filters = [Invoice.tenant_id == tenant_id]
        if status:
            filters.append(Invoice.status == status)

        stmt = select(Invoice).where(and_(*filters)).order_by(Invoice.issued_at.desc())
        return (await self.session.execute(stmt)).scalars().all()

    async def create_invoice(
        self,
        tenant_id: uuid.UUID,
        items_data: list[dict[str, Any]],
        subscription_id: uuid.UUID | None = None,
        discount: Decimal = Decimal("0.00"),
        tax: Decimal = Decimal("0.00"),
        currency: str = "IDR",
        billing_period_start: datetime | None = None,
        billing_period_end: datetime | None = None,
        due_days: int = 7,
    ) -> Invoice:
        now = datetime.now(timezone.utc)
        due_at = now + timedelta(days=due_days)
        inv_num = generate_invoice_number()

        subtotal = Decimal("0.00")
        items = []

        for item_def in items_data:
            qty = int(item_def.get("quantity", 1))
            unit_price = Decimal(str(item_def["unit_price"])).quantize(Decimal("0.01"))
            item_subtotal = (unit_price * Decimal(qty)).quantize(Decimal("0.01"))
            subtotal += item_subtotal

            items.append(
                InvoiceItem(
                    description=item_def["description"],
                    revenue_type=item_def.get("revenue_type", RevenueType.SUBSCRIPTION),
                    amount=item_subtotal,
                    quantity=qty,
                    unit_price=unit_price,
                    metadata_=item_def.get("metadata"),
                )
            )

        total = (subtotal - discount + tax).quantize(Decimal("0.01"))

        invoice = Invoice(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            invoice_number=inv_num,
            status=InvoiceStatus.ISSUED,
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            total=total,
            currency=currency,
            billing_period_start=billing_period_start,
            billing_period_end=billing_period_end,
            issued_at=now,
            due_at=due_at,
            items=items,
        )

        self.session.add(invoice)
        await self.session.commit()
        await self.session.refresh(invoice)
        return invoice

    async def update_status(self, tenant_id: uuid.UUID, invoice_id: uuid.UUID, new_status: str) -> Invoice:
        inv = await self.get_invoice(tenant_id, invoice_id)
        validate_invoice_transition(inv.status, new_status)
        now = datetime.now(timezone.utc)

        inv.status = new_status
        if new_status == InvoiceStatus.PAID:
            inv.paid_at = now
        elif new_status == InvoiceStatus.VOID:
            inv.voided_at = now

        await self.session.commit()
        await self.session.refresh(inv)
        return inv

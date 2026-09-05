import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.billing import Payment, Invoice, InvoiceItem, Subscription, Plan
from app.database.models.order import Order
from app.analytics.schemas import FinancialAnalyticsSchema
from app.analytics.metrics import safe_decimal, calculate_change_pct


class FinancialAnalyticsService:
    """Service for computing deterministic financial analytics."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_financial_analytics(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> FinancialAnalyticsSchema:
        now = datetime.now(timezone.utc)
        if not period_end:
            period_end = now
        if not period_start:
            period_start = period_end - timedelta(days=30)

        period_duration = period_end - period_start
        prior_period_start = period_start - period_duration
        prior_period_end = period_start

        # Filter conditions
        tenant_filter = [Invoice.tenant_id == tenant_id] if tenant_id else []
        pmt_tenant_filter = [Payment.tenant_id == tenant_id] if tenant_id else []
        sub_tenant_filter = [Subscription.tenant_id == tenant_id] if tenant_id else []

        # 1. Total Revenue (Paid Invoices or Successful Payments in period)
        stmt_rev = select(
            func.coalesce(func.sum(Invoice.total), Decimal("0.00"))
        ).where(
            and_(
                Invoice.status == "PAID",
                Invoice.paid_at >= period_start,
                Invoice.paid_at <= period_end,
                *tenant_filter,
            )
        )
        total_revenue = safe_decimal((await self.session.execute(stmt_rev)).scalar())

        # Prior period revenue for growth calculation
        stmt_prior_rev = select(
            func.coalesce(func.sum(Invoice.total), Decimal("0.00"))
        ).where(
            and_(
                Invoice.status == "PAID",
                Invoice.paid_at >= prior_period_start,
                Invoice.paid_at <= prior_period_end,
                *tenant_filter,
            )
        )
        prior_revenue = safe_decimal((await self.session.execute(stmt_prior_rev)).scalar())
        revenue_growth_pct = calculate_change_pct(total_revenue, prior_revenue)

        # 2. MRR and ARR from Active Subscriptions
        stmt_mrr = select(
            Subscription.billing_cycle,
            Subscription.amount
        ).where(
            and_(
                Subscription.status.in_(["ACTIVE", "TRIALING"]),
                *sub_tenant_filter,
            )
        )
        sub_rows = (await self.session.execute(stmt_mrr)).all()

        mrr = Decimal("0.00")
        for cycle, amt in sub_rows:
            amt_dec = safe_decimal(amt)
            if cycle == "MONTHLY":
                mrr += amt_dec
            elif cycle == "YEARLY":
                mrr += (amt_dec / Decimal("12.00"))
        mrr = mrr.quantize(Decimal("0.01"))
        arr = (mrr * Decimal("12.00")).quantize(Decimal("0.01"))

        # 3. Revenue by Type (Subscription, Setup, Addon, Custom)
        stmt_type_rev = select(
            InvoiceItem.revenue_type,
            func.coalesce(func.sum(InvoiceItem.amount), Decimal("0.00"))
        ).join(
            Invoice, InvoiceItem.invoice_id == Invoice.id
        ).where(
            and_(
                Invoice.status == "PAID",
                Invoice.paid_at >= period_start,
                Invoice.paid_at <= period_end,
                *tenant_filter,
            )
        ).group_by(InvoiceItem.revenue_type)

        type_rows = (await self.session.execute(stmt_type_rev)).all()
        revenue_by_type: Dict[str, Decimal] = {
            "SUBSCRIPTION": Decimal("0.00"),
            "SETUP": Decimal("0.00"),
            "ADDON": Decimal("0.00"),
            "CUSTOM": Decimal("0.00"),
        }
        for rev_type, amt in type_rows:
            type_key = rev_type.upper() if rev_type else "SUBSCRIPTION"
            revenue_by_type[type_key] = safe_decimal(amt)

        subscription_revenue = revenue_by_type.get("SUBSCRIPTION", Decimal("0.00"))
        setup_revenue = revenue_by_type.get("SETUP", Decimal("0.00"))
        addon_revenue = revenue_by_type.get("ADDON", Decimal("0.00"))
        custom_service_revenue = revenue_by_type.get("CUSTOM", Decimal("0.00"))

        # 4. Outstanding Payments (Unpaid Invoices)
        stmt_outstanding = select(
            func.coalesce(func.sum(Invoice.total), Decimal("0.00"))
        ).where(
            and_(
                Invoice.status.in_(["ISSUED", "OVERDUE", "OPEN", "PENDING"]),
                *tenant_filter,
            )
        )
        outstanding_payments = safe_decimal((await self.session.execute(stmt_outstanding)).scalar())

        # 5. Failed, Successful, and Refund Payments
        stmt_pmts = select(
            Payment.status,
            func.coalesce(func.sum(Payment.amount), Decimal("0.00"))
        ).where(
            and_(
                Payment.created_at >= period_start,
                Payment.created_at <= period_end,
                *pmt_tenant_filter,
            )
        ).group_by(Payment.status)

        pmt_rows = (await self.session.execute(stmt_pmts)).all()
        failed_pmts = Decimal("0.00")
        succ_pmts = Decimal("0.00")
        refund_pmts = Decimal("0.00")

        for status, amt in pmt_rows:
            s_upper = status.upper() if status else ""
            if s_upper == "FAILED":
                failed_pmts += safe_decimal(amt)
            elif s_upper in ["SUCCESSFUL", "PAID", "COMPLETED"]:
                succ_pmts += safe_decimal(amt)
            elif s_upper in ["REFUNDED", "REFUND"]:
                refund_pmts += safe_decimal(amt)

        # 6. Revenue by Plan
        stmt_plan_rev = select(
            Plan.code,
            func.coalesce(func.sum(Invoice.total), Decimal("0.00"))
        ).join(
            Subscription, Subscription.plan_id == Plan.id
        ).join(
            Invoice, Invoice.subscription_id == Subscription.id
        ).where(
            and_(
                Invoice.status == "PAID",
                Invoice.paid_at >= period_start,
                Invoice.paid_at <= period_end,
                *tenant_filter,
            )
        ).group_by(Plan.code)

        plan_rows = (await self.session.execute(stmt_plan_rev)).all()
        revenue_by_plan = {code: safe_decimal(amt) for code, amt in plan_rows}

        # 7. Revenue by Tenant (Platform level query when tenant_id is None)
        revenue_by_tenant = None
        if tenant_id is None:
            stmt_tenant_rev = select(
                Invoice.tenant_id,
                func.coalesce(func.sum(Invoice.total), Decimal("0.00"))
            ).where(
                and_(
                    Invoice.status == "PAID",
                    Invoice.paid_at >= period_start,
                    Invoice.paid_at <= period_end,
                )
            ).group_by(Invoice.tenant_id)
            tenant_rows = (await self.session.execute(stmt_tenant_rev)).all()
            revenue_by_tenant = {str(t_id): safe_decimal(amt) for t_id, amt in tenant_rows}

        # 8. Average Revenue Per Client (ARPC)
        stmt_active_clients = select(
            func.count(func.distinct(Subscription.tenant_id))
        ).where(
            and_(
                Subscription.status.in_(["ACTIVE", "TRIALING"]),
                *sub_tenant_filter,
            )
        )
        active_client_count = (await self.session.execute(stmt_active_clients)).scalar() or 0

        arpc = Decimal("0.00")
        if active_client_count > 0:
            arpc = (total_revenue / Decimal(active_client_count)).quantize(Decimal("0.01"))

        return FinancialAnalyticsSchema(
            tenant_id=str(tenant_id) if tenant_id else None,
            period_start=period_start,
            period_end=period_end,
            total_revenue=total_revenue,
            mrr=mrr,
            arr=arr,
            subscription_revenue=subscription_revenue,
            setup_revenue=setup_revenue,
            addon_revenue=addon_revenue,
            custom_service_revenue=custom_service_revenue,
            outstanding_payments=outstanding_payments,
            failed_payments_amount=failed_pmts,
            successful_payments_amount=succ_pmts,
            refunds_amount=refund_pmts,
            arpc=arpc,
            revenue_growth_pct=revenue_growth_pct,
            revenue_by_plan=revenue_by_plan,
            revenue_by_type=revenue_by_type,
            revenue_by_tenant=revenue_by_tenant,
            generated_at=now,
        )

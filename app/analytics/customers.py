import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.customer import Customer
from app.database.models.order import Order
from app.analytics.schemas import CustomerAnalyticsSchema
from app.analytics.metrics import safe_decimal, calculate_change_pct


class CustomerAnalyticsService:
    """Service for computing customer domain analytics."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def get_customer_analytics(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> CustomerAnalyticsSchema:
        now = datetime.now(timezone.utc)
        if not period_end:
            period_end = now
        if not period_start:
            period_start = period_end - timedelta(days=30)

        period_duration = period_end - period_start
        prior_period_start = period_start - period_duration

        cust_filter = [Customer.tenant_id == tenant_id] if tenant_id else []
        order_filter = [Order.tenant_id == tenant_id] if tenant_id else []

        # 1. Total Customers
        stmt_total = select(func.count(Customer.id)).where(and_(*cust_filter))
        total_customers = (await self.session.execute(stmt_total)).scalar() or 0

        # 2. New Customers in period
        stmt_new = select(func.count(Customer.id)).where(
            and_(
                Customer.created_at >= period_start,
                Customer.created_at <= period_end,
                *cust_filter,
            )
        )
        new_customers = (await self.session.execute(stmt_new)).scalar() or 0

        stmt_prior_new = select(func.count(Customer.id)).where(
            and_(
                Customer.created_at >= prior_period_start,
                Customer.created_at < period_start,
                *cust_filter,
            )
        )
        prior_new_customers = (await self.session.execute(stmt_prior_new)).scalar() or 0
        customer_growth_pct = calculate_change_pct(new_customers, prior_new_customers)

        # 3. Active Customers (Customers with orders in period)
        stmt_active_cust = select(func.count(func.distinct(Order.customer_id))).where(
            and_(
                Order.created_at >= period_start,
                Order.created_at <= period_end,
                Order.customer_id.is_not(None),
                *order_filter,
            )
        )
        active_customers = (await self.session.execute(stmt_active_cust)).scalar() or 0
        inactive_customers = max(0, total_customers - active_customers)

        # 4. Order Frequency, AOV, Total Customer Revenue
        stmt_orders = select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), Decimal("0.00")),
            func.avg(Order.total)
        ).where(
            and_(
                Order.created_at >= period_start,
                Order.created_at <= period_end,
                Order.status.in_(["COMPLETED", "PAID", "DELIVERED"]),
                *order_filter,
            )
        )
        order_res = (await self.session.execute(stmt_orders)).one()
        total_orders, tot_rev, avg_val = order_res[0], safe_decimal(order_res[1]), safe_decimal(order_res[2])

        order_frequency = round((total_orders / active_customers), 2) if active_customers > 0 else 0.0
        aov = avg_val.quantize(Decimal("0.01"))

        # 5. Returning Customers & Repeat Purchase Rate
        stmt_repeat = select(
            Order.customer_id,
            func.count(Order.id).label("cnt")
        ).where(
            and_(
                Order.created_at >= period_start,
                Order.created_at <= period_end,
                Order.customer_id.is_not(None),
                *order_filter,
            )
        ).group_by(Order.customer_id).having(func.count(Order.id) > 1)

        repeat_rows = (await self.session.execute(stmt_repeat)).all()
        returning_customers = len(repeat_rows)
        repeat_purchase_rate = round((returning_customers / active_customers * 100.0), 2) if active_customers > 0 else 0.0

        # 6. Customer Segments based on deterministic rules
        # VIP: Revenue > 10,000,000 IDR or Order Count >= 5
        # Regular: Order Count between 1 and 4
        # Inactive: Order Count == 0 in period
        stmt_seg = select(
            Order.customer_id,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), Decimal("0.00"))
        ).where(
            and_(
                Order.created_at >= period_start,
                Order.created_at <= period_end,
                Order.customer_id.is_not(None),
                *order_filter,
            )
        ).group_by(Order.customer_id)

        seg_rows = (await self.session.execute(stmt_seg)).all()
        vip_cnt = 0
        regular_cnt = 0
        for _, o_cnt, o_sum in seg_rows:
            sum_dec = safe_decimal(o_sum)
            if o_cnt >= 5 or sum_dec >= Decimal("10000000.00"):
                vip_cnt += 1
            else:
                regular_cnt += 1

        customer_segments: Dict[str, int] = {
            "VIP": vip_cnt,
            "REGULAR": regular_cnt,
            "INACTIVE": inactive_customers,
        }

        return CustomerAnalyticsSchema(
            total_customers=total_customers,
            active_customers=active_customers,
            new_customers=new_customers,
            returning_customers=returning_customers,
            inactive_customers=inactive_customers,
            customer_growth_pct=customer_growth_pct,
            order_frequency=order_frequency,
            average_order_value=aov,
            total_customer_revenue=tot_rev,
            repeat_purchase_rate=repeat_purchase_rate,
            customer_segments=customer_segments,
            generated_at=now,
        )

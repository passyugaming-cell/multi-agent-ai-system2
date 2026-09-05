from decimal import Decimal
from typing import Sequence, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.billing import Plan, PlanFeature, PlanLimit
from app.billing.exceptions import PlanNotFoundError

ANNUAL_DISCOUNT_PERCENT = Decimal("0.15")

STARTER_FEATURES = [
    "ai_customer_service",
    "faq",
    "knowledge_base",
    "products",
    "product_variants",
    "stock",
    "customer_database",
    "conversation_history",
    "orders",
    "cart",
    "human_handoff",
    "admin_inbox",
    "basic_analytics",
    "basic_automation",
    "whatsapp_cloud_api",
]

PRO_FEATURES = STARTER_FEATURES + [
    "ai_memory",
    "advanced_knowledge",
    "ai_sales",
    "ai_support",
    "ai_followup",
    "lead_qualification",
    "conversation_analysis",
    "workflow_builder",
    "scheduled_automation",
    "abandoned_cart",
    "reminders",
    "broadcast",
    "segmentation",
    "campaigns",
    "advanced_analytics",
    "conversion_analytics",
    "customer_segmentation",
    "ai_recommendations",
    "api_access",
    "webhooks",
    "google_sheets",
    "google_calendar",
    "midtrans",
    "midtrans_payment",
    "payments",
    "rest_api",
    "make_connector",
    "n8n_connector",
    "zapier_connector",
]

BUSINESS_FEATURES = PRO_FEATURES + [
    "owner_ai",
    "ai_client_manager",
    "ai_analyst",
    "ai_data_manager",
    "custom_ai_agent",
    "advanced_bi",
    "forecasting",
    "anomaly_detection",
    "trend_detection",
    "business_health_score",
    "daily_brief",
    "weekly_review",
    "instagram",
    "facebook_messenger",
    "web_chat",
    "advanced_crm",
    "advanced_api",
    "custom_webhooks",
    "advanced_workflow",
    "custom_roles",
    "granular_permissions",
    "2fa",
    "ip_restriction",
    "audit_log",
    "advanced_reports",
    "customer_360",
    "priority_support",
]

TRIAL_FEATURES = STARTER_FEATURES + ["broadcast", "api_access", "webhooks", "google_sheets", "google_calendar", "midtrans", "midtrans_payment", "payments", "rest_api", "whatsapp_cloud_api"]

PLAN_DEFINITIONS = {
    "starter": {
        "name": "Starter",
        "code": "starter",
        "description": "Ideal for small businesses getting started with AI automation",
        "price_monthly": Decimal("299000.00"),
        "price_yearly": (Decimal("299000.00") * Decimal("12") * (Decimal("1.00") - ANNUAL_DISCOUNT_PERCENT)).quantize(Decimal("0.01")),
        "limits": {
            "whatsapp_connections": 1,
            "admins": 3,
            "active_customers": 1000,
            "ai_credits": 3000,
            "automation_runs": 2000,
            "outbound_messages": 5000,
            "storage_bytes": 5 * 1024 * 1024 * 1024,
        },
        "features": STARTER_FEATURES,
    },
    "pro": {
        "name": "Pro",
        "code": "pro",
        "description": "Growing businesses needing advanced sales & marketing workflows",
        "price_monthly": Decimal("799000.00"),
        "price_yearly": (Decimal("799000.00") * Decimal("12") * (Decimal("1.00") - ANNUAL_DISCOUNT_PERCENT)).quantize(Decimal("0.01")),
        "limits": {
            "whatsapp_connections": 2,
            "admins": 10,
            "active_customers": 5000,
            "ai_credits": 15000,
            "automation_runs": 10000,
            "outbound_messages": 25000,
            "storage_bytes": 25 * 1024 * 1024 * 1024,
        },
        "features": PRO_FEATURES,
    },
    "business": {
        "name": "Business",
        "code": "business",
        "description": "Full-featured AI Business OS with Owner AI intelligence",
        "price_monthly": Decimal("1999000.00"),
        "price_yearly": (Decimal("1999000.00") * Decimal("12") * (Decimal("1.00") - ANNUAL_DISCOUNT_PERCENT)).quantize(Decimal("0.01")),
        "limits": {
            "whatsapp_connections": 5,
            "admins": 25,
            "active_customers": 20000,
            "ai_credits": 50000,
            "automation_runs": 50000,
            "outbound_messages": 50000,
            "storage_bytes": 100 * 1024 * 1024 * 1024,
        },
        "features": BUSINESS_FEATURES,
    },
    "enterprise": {
        "name": "Enterprise",
        "code": "enterprise",
        "description": "Custom scale and dedicated resources for large organizations",
        "price_monthly": Decimal("0.00"),
        "price_yearly": Decimal("0.00"),
        "limits": {
            "whatsapp_connections": -1,
            "admins": -1,
            "active_customers": -1,
            "ai_credits": -1,
            "automation_runs": -1,
            "outbound_messages": -1,
            "storage_bytes": -1,
        },
        "features": BUSINESS_FEATURES,
    },
}

TRIAL_LIMITS = {
    "whatsapp_connections": 1,
    "admins": 3,
    "active_customers": 500,
    "ai_credits": 1000,
    "automation_runs": 500,
    "outbound_messages": 1000,
    "storage_bytes": 1 * 1024 * 1024 * 1024,
}


def calculate_billed_amount(monthly_price: Decimal, billing_cycle: str) -> Decimal:
    """Calculates billed amount for a monthly or annual billing cycle deterministically using Decimal."""
    if billing_cycle.upper() == "YEARLY":
        raw_year = monthly_price * Decimal("12")
        discount = raw_year * ANNUAL_DISCOUNT_PERCENT
        return (raw_year - discount).quantize(Decimal("0.01"))
    return monthly_price.quantize(Decimal("0.01"))


class PlanService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def seed_plans(self) -> Sequence[Plan]:
        """Idempotently seed default plans, features, and limits into the database."""
        for code, defn in PLAN_DEFINITIONS.items():
            stmt = select(Plan).where(Plan.code == code)
            plan = (await self.session.execute(stmt)).scalar_one_or_none()

            if not plan:
                plan = Plan(
                    name=defn["name"],
                    code=defn["code"],
                    description=defn["description"],
                    price_monthly=defn["price_monthly"],
                    price_yearly=defn["price_yearly"],
                    currency="IDR",
                    is_active=True,
                )
                self.session.add(plan)
                await self.session.flush()
            else:
                plan.name = defn["name"]
                plan.description = defn["description"]
                plan.price_monthly = defn["price_monthly"]
                plan.price_yearly = defn["price_yearly"]

            # Sync features
            existing_feats_stmt = select(PlanFeature).where(PlanFeature.plan_id == plan.id)
            existing_feats = {f.feature_key: f for f in (await self.session.execute(existing_feats_stmt)).scalars().all()}

            for feat_key in set(defn["features"]):
                if feat_key not in existing_feats:
                    pf = PlanFeature(plan_id=plan.id, feature_key=feat_key, is_enabled=True)
                    self.session.add(pf)

            # Sync limits
            existing_limits_stmt = select(PlanLimit).where(PlanLimit.plan_id == plan.id)
            existing_limits = {l.metric: l for l in (await self.session.execute(existing_limits_stmt)).scalars().all()}

            for metric, lim_val in defn["limits"].items():
                if metric not in existing_limits:
                    pl = PlanLimit(plan_id=plan.id, metric=metric, limit_value=lim_val)
                    self.session.add(pl)
                else:
                    existing_limits[metric].limit_value = lim_val

        await self.session.flush()
        return await self.list_plans()

    async def list_plans(self) -> Sequence[Plan]:
        stmt = (
            select(Plan)
            .options(selectinload(Plan.features), selectinload(Plan.limits))
            .where(Plan.is_active == True)
            .order_by(Plan.price_monthly.asc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def get_plan_by_code(self, code: str) -> Plan:
        stmt = (
            select(Plan)
            .options(selectinload(Plan.features), selectinload(Plan.limits))
            .where(Plan.code == code.lower())
        )
        plan = (await self.session.execute(stmt)).scalar_one_or_none()
        if not plan:
            raise PlanNotFoundError(code)
        return plan

    async def get_plan_by_id(self, plan_id: Any) -> Plan:
        stmt = (
            select(Plan)
            .options(selectinload(Plan.features), selectinload(Plan.limits))
            .where(Plan.id == plan_id)
        )
        plan = (await self.session.execute(stmt)).scalar_one_or_none()
        if not plan:
            raise PlanNotFoundError(str(plan_id))
        return plan

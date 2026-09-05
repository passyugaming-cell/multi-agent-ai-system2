import uuid
from typing import Any, List
from decimal import Decimal
from fastapi import APIRouter, Depends, Header, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.core.context import get_tenant_id
from app.billing.plans import PlanService
from app.billing.subscription import SubscriptionService
from app.billing.entitlement import EntitlementResolver
from app.billing.usage import UsageService, UsageMetric
from app.billing.invoices import InvoiceService
from app.billing.payments import PaymentService
from app.billing.refunds import RefundService
from app.core.exceptions import AppError

router = APIRouter(prefix="/billing", tags=["Billing"])


# Request / Response Schemas
class PlanResponse(BaseModel):
    id: str
    name: str
    code: str
    description: str | None
    price_monthly: float
    price_yearly: float
    currency: str
    features: list[str] = []


class SubscriptionResponse(BaseModel):
    id: str
    tenant_id: str
    plan_code: str
    status: str
    billing_cycle: str
    amount: float
    currency: str
    started_at: str
    current_period_start: str
    current_period_end: str
    trial_end: str | None = None


class ActivateSubscriptionRequest(BaseModel):
    plan_code: str = Field(..., json_schema_extra={"example": "pro"})
    billing_cycle: str = Field(default="MONTHLY", json_schema_extra={"example": "MONTHLY"})


class ChangePlanRequest(BaseModel):
    new_plan_code: str = Field(..., json_schema_extra={"example": "business"})
    billing_cycle: str | None = Field(default=None, json_schema_extra={"example": "YEARLY"})


class CancelSubscriptionRequest(BaseModel):
    reason: str | None = Field(default=None, json_schema_extra={"example": "Not using service"})


class UsageResponse(BaseModel):
    metric: str
    current_usage: int
    limit: int


class InvoiceResponse(BaseModel):
    id: str
    tenant_id: str
    invoice_number: str
    status: str
    subtotal: float
    discount: float
    tax: float
    total: float
    currency: str
    issued_at: str | None = None
    due_at: str | None = None


class PaymentResponse(BaseModel):
    id: str
    tenant_id: str
    invoice_id: str
    amount: float
    currency: str
    status: str
    provider: str
    provider_payment_id: str | None = None


class RefundRequest(BaseModel):
    amount: float = Field(..., json_schema_extra={"example": 299000.0})
    reason: str = Field(..., json_schema_extra={"example": "Billing error"})


class EntitlementResponse(BaseModel):
    feature_key: str
    allowed: bool
    state: str
    reason: str | None = None


# Helper to validate active tenant context
def require_tenant_id() -> uuid.UUID:
    tid = get_tenant_id()
    if not tid:
        raise AppError("X-Tenant-ID header is missing or context is invalid.", status_code=400)
    return uuid.UUID(tid) if isinstance(tid, str) else tid


# Plan Endpoints
@router.get("/plans", response_model=List[PlanResponse])
async def list_plans(db: AsyncSession = Depends(get_db)):
    service = PlanService(db)
    plans = await service.list_plans()
    if not plans:
        plans = await service.seed_plans()
    return [
        PlanResponse(
            id=str(p.id),
            name=p.name,
            code=p.code,
            description=p.description,
            price_monthly=float(p.price_monthly),
            price_yearly=float(p.price_yearly),
            currency=p.currency,
            features=[f.feature_key for f in p.features if f.is_enabled],
        )
        for p in plans
    ]


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    service = PlanService(db)
    plan = await service.get_plan_by_code(plan_id) if not len(plan_id) == 36 else await service.get_plan_by_id(uuid.UUID(plan_id))
    return PlanResponse(
        id=str(plan.id),
        name=plan.name,
        code=plan.code,
        description=plan.description,
        price_monthly=float(plan.price_monthly),
        price_yearly=float(plan.price_yearly),
        currency=plan.currency,
        features=[f.feature_key for f in plan.features if f.is_enabled],
    )


# Subscription Endpoints
@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    sub_service = SubscriptionService(db)
    sub = await sub_service.get_subscription(tenant_id)
    return SubscriptionResponse(
        id=str(sub.id),
        tenant_id=str(sub.tenant_id),
        plan_code=sub.plan.code if sub.plan else "unknown",
        status=sub.status,
        billing_cycle=sub.billing_cycle,
        amount=float(sub.amount),
        currency=sub.currency,
        started_at=sub.started_at.isoformat(),
        current_period_start=sub.current_period_start.isoformat(),
        current_period_end=sub.current_period_end.isoformat(),
        trial_end=sub.trial_end.isoformat() if sub.trial_end else None,
    )


@router.post("/subscription", response_model=SubscriptionResponse)
async def activate_subscription(body: ActivateSubscriptionRequest, db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    sub_service = SubscriptionService(db)
    sub = await sub_service.activate_subscription(
        tenant_id=tenant_id,
        plan_code=body.plan_code,
        billing_cycle=body.billing_cycle,
        actor="API_USER",
    )
    return SubscriptionResponse(
        id=str(sub.id),
        tenant_id=str(sub.tenant_id),
        plan_code=sub.plan.code if sub.plan else body.plan_code,
        status=sub.status,
        billing_cycle=sub.billing_cycle,
        amount=float(sub.amount),
        currency=sub.currency,
        started_at=sub.started_at.isoformat(),
        current_period_start=sub.current_period_start.isoformat(),
        current_period_end=sub.current_period_end.isoformat(),
        trial_end=sub.trial_end.isoformat() if sub.trial_end else None,
    )


@router.post("/subscription/change-plan", response_model=SubscriptionResponse)
async def change_plan(body: ChangePlanRequest, db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    sub_service = SubscriptionService(db)
    sub = await sub_service.change_plan(
        tenant_id=tenant_id,
        new_plan_code=body.new_plan_code,
        billing_cycle=body.billing_cycle,
        actor="API_USER",
    )
    return SubscriptionResponse(
        id=str(sub.id),
        tenant_id=str(sub.tenant_id),
        plan_code=sub.plan.code if sub.plan else body.new_plan_code,
        status=sub.status,
        billing_cycle=sub.billing_cycle,
        amount=float(sub.amount),
        currency=sub.currency,
        started_at=sub.started_at.isoformat(),
        current_period_start=sub.current_period_start.isoformat(),
        current_period_end=sub.current_period_end.isoformat(),
        trial_end=sub.trial_end.isoformat() if sub.trial_end else None,
    )


@router.post("/subscription/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(body: CancelSubscriptionRequest, db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    sub_service = SubscriptionService(db)
    sub = await sub_service.cancel_subscription(
        tenant_id=tenant_id,
        reason=body.reason,
        actor="API_USER",
    )
    return SubscriptionResponse(
        id=str(sub.id),
        tenant_id=str(sub.tenant_id),
        plan_code=sub.plan.code if sub.plan else "unknown",
        status=sub.status,
        billing_cycle=sub.billing_cycle,
        amount=float(sub.amount),
        currency=sub.currency,
        started_at=sub.started_at.isoformat(),
        current_period_start=sub.current_period_start.isoformat(),
        current_period_end=sub.current_period_end.isoformat(),
        trial_end=sub.trial_end.isoformat() if sub.trial_end else None,
    )


# Usage Endpoints
@router.get("/usage", response_model=List[UsageResponse])
async def list_usage(db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    usage_service = UsageService(db)
    metrics = [
        UsageMetric.AI_CREDITS,
        UsageMetric.AUTOMATION_RUNS,
        UsageMetric.ACTIVE_CUSTOMERS,
        UsageMetric.OUTBOUND_MESSAGES,
        UsageMetric.WHATSAPP_CONNECTIONS,
        UsageMetric.ADMINS,
        UsageMetric.STORAGE_BYTES,
    ]
    res = []
    for m in metrics:
        curr = await usage_service.get_current_usage(tenant_id, m)
        lim = await usage_service.entitlement_resolver.get_limit(tenant_id, m)
        res.append(UsageResponse(metric=m, current_usage=curr, limit=lim))
    return res


@router.get("/usage/{metric}", response_model=UsageResponse)
async def get_usage_for_metric(metric: str, db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    usage_service = UsageService(db)
    curr = await usage_service.get_current_usage(tenant_id, metric)
    lim = await usage_service.entitlement_resolver.get_limit(tenant_id, metric)
    return UsageResponse(metric=metric, current_usage=curr, limit=lim)


# Invoices Endpoints
@router.get("/invoices", response_model=List[InvoiceResponse])
async def list_invoices(db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    service = InvoiceService(db)
    invs = await service.list_invoices(tenant_id)
    return [
        InvoiceResponse(
            id=str(inv.id),
            tenant_id=str(inv.tenant_id),
            invoice_number=inv.invoice_number,
            status=inv.status,
            subtotal=float(inv.subtotal),
            discount=float(inv.discount),
            tax=float(inv.tax),
            total=float(inv.total),
            currency=inv.currency,
            issued_at=inv.issued_at.isoformat() if inv.issued_at else None,
            due_at=inv.due_at.isoformat() if inv.due_at else None,
        )
        for inv in invs
    ]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(invoice_id: str, db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    service = InvoiceService(db)
    inv = await service.get_invoice(tenant_id, uuid.UUID(invoice_id))
    return InvoiceResponse(
        id=str(inv.id),
        tenant_id=str(inv.tenant_id),
        invoice_number=inv.invoice_number,
        status=inv.status,
        subtotal=float(inv.subtotal),
        discount=float(inv.discount),
        tax=float(inv.tax),
        total=float(inv.total),
        currency=inv.currency,
        issued_at=inv.issued_at.isoformat() if inv.issued_at else None,
        due_at=inv.due_at.isoformat() if inv.due_at else None,
    )


# Payments Endpoints
@router.get("/payments", response_model=List[PaymentResponse])
async def list_payments(db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    service = PaymentService(db)
    payments = await service.list_payments(tenant_id)
    return [
        PaymentResponse(
            id=str(p.id),
            tenant_id=str(p.tenant_id),
            invoice_id=str(p.invoice_id),
            amount=float(p.amount),
            currency=p.currency,
            status=p.status,
            provider=p.provider,
            provider_payment_id=p.provider_payment_id,
        )
        for p in payments
    ]


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str, db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    service = PaymentService(db)
    p = await service.get_payment(tenant_id, uuid.UUID(payment_id))
    return PaymentResponse(
        id=str(p.id),
        tenant_id=str(p.tenant_id),
        invoice_id=str(p.invoice_id),
        amount=float(p.amount),
        currency=p.currency,
        status=p.status,
        provider=p.provider,
        provider_payment_id=p.provider_payment_id,
    )


@router.post("/payments/{payment_id}/refund")
async def request_refund(payment_id: str, body: RefundRequest, db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    refund_service = RefundService(db)
    approval = await refund_service.request_refund(
        tenant_id=tenant_id,
        payment_id=uuid.UUID(payment_id),
        amount=Decimal(str(body.amount)),
        reason=body.reason,
        requested_by="TENANT_USER",
    )
    return {
        "status": "APPROVAL_REQUIRED",
        "approval_id": str(approval.id),
        "message": "High-risk refund request submitted for Human Owner approval.",
    }


# Entitlements Endpoints
@router.get("/entitlements", response_model=List[EntitlementResponse])
async def list_entitlements(db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    resolver = EntitlementResolver(db)
    sub = await resolver.get_tenant_subscription(tenant_id)
    sample_features = [
        "ai_customer_service", "knowledge_base", "products", "orders",
        "ai_sales", "ai_support", "workflow_builder", "owner_ai", "custom_ai_agent"
    ]
    res = []
    for f in sample_features:
        access = await resolver.can_use(tenant_id, f)
        res.append(
            EntitlementResponse(
                feature_key=f,
                allowed=access.allowed,
                state=access.state,
                reason=access.reason,
            )
        )
    return res


@router.get("/features/{feature_key}", response_model=EntitlementResponse)
async def check_feature(feature_key: str, db: AsyncSession = Depends(get_db)):
    tenant_id = require_tenant_id()
    resolver = EntitlementResolver(db)
    access = await resolver.can_use(tenant_id, feature_key)
    return EntitlementResponse(
        feature_key=feature_key,
        allowed=access.allowed,
        state=access.state,
        reason=access.reason,
    )


# Webhook Endpoint (No X-Tenant-ID required for payment provider incoming webhook)
@router.post("/webhooks/payment")
async def payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: str | None = Header(None, alias="x-signature"),
):
    payload = await request.json()
    headers = dict(request.headers)
    if x_signature:
        headers["x-signature"] = x_signature

    service = PaymentService(db)
    payment = await service.handle_provider_webhook(payload, headers)
    return {
        "status": "PROCESSED",
        "payment_id": str(payment.id),
        "payment_status": payment.status,
    }

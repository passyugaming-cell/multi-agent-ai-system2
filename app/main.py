from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.business import router as business_router
from app.api.v1.business_profile import router as business_profile_router
from app.api.v1.products import router as products_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.customers import router as customers_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.orders import router as orders_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.events import router as events_router
from app.api.v1.workflows import router as workflows_router
from app.api.v1.workflow_executions import router as workflow_executions_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.agents import router as agents_router
from app.api.v1.owner_ai import router as owner_ai_router
from app.api.v1.billing import router as billing_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.webhooks import router as webhooks_router
from app.integrations.whatsapp import whatsapp_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import RequestLoggingMiddleware, logger
from app.core.middleware import TenantMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown logging."""
    logger.info(f"Starting {settings.APP_NAME} in [{settings.APP_ENV}] mode")
    yield
    logger.info(f"Shutting down {settings.APP_NAME}")


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Register Middlewares (Order: CORSMiddleware must wrap on the outside to handle preflights & CORS headers)
app.add_middleware(TenantMiddleware)
app.add_middleware(RequestLoggingMiddleware)

origins = [o.strip() for o in settings.FRONTEND_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


# Register Exception Handlers for consistent JSON error formatting
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "HTTP_ERROR"
    if exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 405:
        code = "METHOD_NOT_ALLOWED"
    elif exc.status_code == 503:
        code = "SERVICE_UNAVAILABLE"

    message = str(exc.detail) if exc.detail else "HTTP request error"

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": message,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request payload or query parameters",
            }
        },
    )


# Include Routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(health_router)  # Also expose /health and /health/db at root
app.include_router(auth_router, prefix="/api/v1")
app.include_router(business_router, prefix="/api/v1")
app.include_router(business_profile_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(customers_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")
app.include_router(onboarding_router, prefix="/api/v1")
app.include_router(whatsapp_router, prefix="/api/v1")

# Phase 2 Routers
app.include_router(events_router, prefix="/api/v1")
app.include_router(workflows_router, prefix="/api/v1")
app.include_router(workflow_executions_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(approvals_router, prefix="/api/v1")

# Phase 3 Routers
app.include_router(agents_router, prefix="/api/v1")

# Phase 4 Routers
app.include_router(owner_ai_router, prefix="/api/v1")

# Phase 1.75 Billing Router
app.include_router(billing_router, prefix="/api/v1")

# Phase 5 Analytics Router
app.include_router(analytics_router, prefix="/api/v1")

# Phase 6 Integration & Webhook Routers
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")

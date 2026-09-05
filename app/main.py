from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.health import router as health_router
from app.api.v1.business_profile import router as business_profile_router
from app.api.v1.products import router as products_router
from app.api.v1.customers import router as customers_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.orders import router as orders_router
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

# Register Middlewares (Order: RequestLoggingMiddleware runs outside TenantMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(RequestLoggingMiddleware)


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
app.include_router(business_profile_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(customers_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(orders_router, prefix="/api/v1")
app.include_router(whatsapp_router, prefix="/api/v1")

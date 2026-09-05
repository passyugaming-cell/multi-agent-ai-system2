from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    """Health check endpoint to verify application status."""
    return {"status": "ok"}


@router.get("/health/db", status_code=status.HTTP_200_OK)
async def db_health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Database health check endpoint to verify PostgreSQL connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connectivity check failed",
        ) from exc

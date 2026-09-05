import uuid
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.middleware as middleware_module
import app.database.session as session_module
from app.core.config import settings
from app.database.base import Base
from app.database.models.tenant import Tenant
from app.tenants.repository import TenantRepository
from app.tenants.schemas import TenantCreate

TEST_DATABASE_URL = (
    settings.TEST_DATABASE_URL
    or settings.DATABASE_URL.replace("ai_business_os", "ai_business_os_test")
)


@pytest_asyncio.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a function-scoped test database engine with NullPool."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_session_factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Provide a session factory bound to the function-scoped test engine."""
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(autouse=True)
async def patch_middleware_session_factory(
    test_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure middleware and dependencies use the test database session factory."""
    monkeypatch.setattr(session_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(middleware_module, "async_session_factory", test_session_factory)


@pytest_asyncio.fixture
async def test_session(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Alias for test session."""
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def db_session(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean async database session for test fixture setup."""
    async with test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def async_client(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    """Provide httpx AsyncClient with database dependency override."""
    from app.main import app as fastapi_app

    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    fastapi_app.dependency_overrides[session_module.get_db] = _get_test_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    """Provide httpx AsyncClient with database dependency override."""
    from app.main import app as fastapi_app

    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    fastapi_app.dependency_overrides[session_module.get_db] = _get_test_db

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def tenant_a(db_session: AsyncSession) -> Tenant:
    """Fixture for active Tenant A."""
    repo = TenantRepository(db_session)
    slug = f"tenant-alpha-{uuid.uuid4().hex[:6]}"
    tenant = await repo.create(
        TenantCreate(name="Tenant Alpha", slug=slug, is_active=True)
    )
    await db_session.commit()
    return tenant


@pytest_asyncio.fixture
async def tenant_b(db_session: AsyncSession) -> Tenant:
    """Fixture for active Tenant B."""
    repo = TenantRepository(db_session)
    slug = f"tenant-beta-{uuid.uuid4().hex[:6]}"
    tenant = await repo.create(
        TenantCreate(name="Tenant Beta", slug=slug, is_active=True)
    )
    await db_session.commit()
    return tenant


@pytest_asyncio.fixture
async def inactive_tenant(db_session: AsyncSession) -> Tenant:
    """Fixture for inactive Tenant."""
    repo = TenantRepository(db_session)
    slug = f"tenant-inactive-{uuid.uuid4().hex[:6]}"
    tenant = await repo.create(
        TenantCreate(name="Tenant Inactive", slug=slug, is_active=False)
    )
    await db_session.commit()
    return tenant

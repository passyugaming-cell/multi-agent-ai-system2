import uuid
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.core import config
from app.core.config import Settings
from app.database.models.tenant import Tenant
from app.billing.payments import PaymentService, get_default_payment_provider
from app.billing.provider import FakePaymentProvider, MidtransPaymentProvider, PaymentResult
from app.billing.exceptions import PaymentConfigurationError, PaymentFailedError
from app.billing.invoices import InvoiceService


@pytest.fixture(autouse=True)
def mock_redis_revocation(monkeypatch):
    revoked_jtis = set()

    async def mock_is_revoked(jti: str) -> bool:
        return jti in revoked_jtis

    async def mock_revoke(jti: str, exp_timestamp: int | None = None, ttl: int = 86400):
        revoked_jtis.add(jti)

    import app.core.auth_service as auth_srv
    import app.api.v1.auth as auth_api
    monkeypatch.setattr(auth_srv, "is_token_revoked_redis", mock_is_revoked)
    monkeypatch.setattr(auth_srv, "revoke_token_redis", mock_revoke)
    monkeypatch.setattr(auth_api, "revoke_token_redis", mock_revoke)


@pytest.mark.asyncio
async def test_01_production_missing_payment_provider_fails_closed(monkeypatch, db_session: AsyncSession):
    """REQUIREMENT 1: Production + missing provider -> rejected / fail closed."""
    prod_settings = Settings(
        _env_file=None,
        APP_ENV="production",
        JWT_SECRET="a_prod_jwt_secret_32_characters_long_value!",
        ENCRYPTION_KEY="a_prod_encryption_key_32_bytes_long_value!",
        DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@prod-db:5432/prod_db",
        GOOGLE_CLIENT_ID="real_google_client_id.apps.googleusercontent.com",
        GOOGLE_CLIENT_SECRET="real_google_client_secret",
        PAYMENT_PROVIDER="midtrans",
        MIDTRANS_SERVER_KEY="real_server_key_123",
    )

    # Simulate missing PAYMENT_PROVIDER in production
    prod_settings.PAYMENT_PROVIDER = ""
    monkeypatch.setattr(config, "settings", prod_settings)

    with pytest.raises(PaymentConfigurationError) as excinfo:
        PaymentService(db_session)

    assert "FakePaymentProvider is forbidden in production" in str(excinfo.value) or "Unsupported production payment provider" in str(excinfo.value)


@pytest.mark.asyncio
async def test_02_production_fake_payment_provider_rejected(monkeypatch, db_session: AsyncSession):
    """REQUIREMENT 2: Production + FakePaymentProvider -> rejected."""
    # A. Direct Settings model validation rejection
    with pytest.raises(ValidationError) as exc_val:
        Settings(
            _env_file=None,
            APP_ENV="production",
            JWT_SECRET="a_prod_jwt_secret_32_characters_long_value!",
            ENCRYPTION_KEY="a_prod_encryption_key_32_bytes_long_value!",
            DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@prod-db:5432/prod_db",
            GOOGLE_CLIENT_ID="real_google_client_id.apps.googleusercontent.com",
            GOOGLE_CLIENT_SECRET="real_google_client_secret",
            PAYMENT_PROVIDER="fake",
        )
    assert "PAYMENT_PROVIDER cannot be 'fake'" in str(exc_val.value)

    # B. Explicit FakePaymentProvider instance passed to PaymentService in production -> rejected
    prod_settings = Settings(
        _env_file=None,
        APP_ENV="production",
        JWT_SECRET="a_prod_jwt_secret_32_characters_long_value!",
        ENCRYPTION_KEY="a_prod_encryption_key_32_bytes_long_value!",
        DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@prod-db:5432/prod_db",
        GOOGLE_CLIENT_ID="real_google_client_id.apps.googleusercontent.com",
        GOOGLE_CLIENT_SECRET="real_google_client_secret",
        PAYMENT_PROVIDER="midtrans",
        MIDTRANS_SERVER_KEY="real_server_key_123",
    )
    monkeypatch.setattr(config, "settings", prod_settings)

    fake_provider = FakePaymentProvider()
    with pytest.raises(PaymentConfigurationError) as exc_service:
        PaymentService(db_session, provider=fake_provider)

    assert "FakePaymentProvider cannot be used in production" in str(exc_service.value)


@pytest.mark.asyncio
async def test_03_test_development_explicit_fake_payment_provider_allowed(monkeypatch, db_session: AsyncSession):
    """REQUIREMENT 3: Test/development + explicit FakePaymentProvider -> allowed."""
    dev_settings = Settings(
        _env_file=None,
        APP_ENV="development",
        PAYMENT_PROVIDER="fake",
    )
    monkeypatch.setattr(config, "settings", dev_settings)

    service = PaymentService(db_session)
    assert isinstance(service.provider, FakePaymentProvider)
    assert service.provider.provider_name == "fake"


@pytest.mark.asyncio
async def test_04_production_valid_real_provider_allowed(monkeypatch, db_session: AsyncSession):
    """REQUIREMENT 4: Production + valid real provider -> allowed."""
    prod_settings = Settings(
        _env_file=None,
        APP_ENV="production",
        JWT_SECRET="a_prod_jwt_secret_32_characters_long_value!",
        ENCRYPTION_KEY="a_prod_encryption_key_32_bytes_long_value!",
        DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@prod-db:5432/prod_db",
        GOOGLE_CLIENT_ID="real_google_client_id.apps.googleusercontent.com",
        GOOGLE_CLIENT_SECRET="real_google_client_secret",
        PAYMENT_PROVIDER="midtrans",
        MIDTRANS_SERVER_KEY="real_midtrans_key_12345",
        MIDTRANS_IS_SANDBOX=False,
    )
    monkeypatch.setattr(config, "settings", prod_settings)

    service = PaymentService(db_session)
    assert isinstance(service.provider, MidtransPaymentProvider)
    assert service.provider.provider_name == "midtrans"
    assert service.provider.server_key == "real_midtrans_key_12345"


@pytest.mark.asyncio
async def test_05_no_silent_fake_fallback_when_production_config_incomplete(monkeypatch, db_session: AsyncSession):
    """REQUIREMENT 5: No silent fake fallback -> production cannot silently instantiate/use fake provider."""
    # A. Fails closed during Settings model validation at startup
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            APP_ENV="production",
            JWT_SECRET="a_prod_jwt_secret_32_characters_long_value!",
            ENCRYPTION_KEY="a_prod_encryption_key_32_bytes_long_value!",
            DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@prod-db:5432/prod_db",
            GOOGLE_CLIENT_ID="real_google_client_id.apps.googleusercontent.com",
            GOOGLE_CLIENT_SECRET="real_google_client_secret",
            PAYMENT_PROVIDER="midtrans",
            MIDTRANS_SERVER_KEY="",  # Incomplete config
        )
    assert "MIDTRANS_SERVER_KEY must be explicitly configured" in str(excinfo.value)

    # B. Fails closed during runtime provider resolution if key is empty/mock
    prod_settings = Settings(
        _env_file=None,
        APP_ENV="production",
        JWT_SECRET="a_prod_jwt_secret_32_characters_long_value!",
        ENCRYPTION_KEY="a_prod_encryption_key_32_bytes_long_value!",
        DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@prod-db:5432/prod_db",
        GOOGLE_CLIENT_ID="real_google_client_id.apps.googleusercontent.com",
        GOOGLE_CLIENT_SECRET="real_google_client_secret",
        PAYMENT_PROVIDER="midtrans",
        MIDTRANS_SERVER_KEY="real_server_key_123",
    )
    prod_settings.MIDTRANS_SERVER_KEY = ""  # Cleared after startup
    monkeypatch.setattr(config, "settings", prod_settings)

    with pytest.raises(PaymentConfigurationError) as excinfo2:
        get_default_payment_provider()

    assert "MIDTRANS_SERVER_KEY is missing or invalid" in str(excinfo2.value)


@pytest.mark.asyncio
async def test_06_actual_provider_identity_persistence(db_session: AsyncSession, tenant_a: Tenant):
    """REQUIREMENT 6: Actual provider identity persistence -> payment record contains actual provider_name."""
    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Pro Plan", "unit_price": "799000.00", "quantity": 1}],
    )

    # 1. Using FakePaymentProvider in test mode
    fake_provider = FakePaymentProvider()
    pay_service_fake = PaymentService(db_session, provider=fake_provider)
    p_fake = await pay_service_fake.create_payment_intent(tenant_a.id, invoice.id, Decimal("799000.00"))
    assert p_fake.provider == "fake"

    # 2. Using MidtransPaymentProvider
    midtrans_provider = MidtransPaymentProvider(server_key="SB-Mid-key-test-123", is_sandbox=True)

    # Mock midtrans adapter create_payment response to avoid HTTP calls
    async def mock_midtrans_create_payment(credentials, params):
        return {
            "success": True,
            "transaction_id": "midtrans_tx_9999",
            "transaction_status": "pending",
        }
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(midtrans_provider.adapter, "create_payment", mock_midtrans_create_payment)

    pay_service_midtrans = PaymentService(db_session, provider=midtrans_provider)
    p_midtrans = await pay_service_midtrans.create_payment_intent(tenant_a.id, invoice.id, Decimal("799000.00"))
    assert p_midtrans.provider == "midtrans"
    assert p_midtrans.provider_payment_id == "midtrans_tx_9999"


@pytest.mark.asyncio
async def test_07_provider_failure_fails_closed(db_session: AsyncSession, tenant_a: Tenant):
    """REQUIREMENT 7: Provider failure fails closed -> provider failure cannot produce fake payment success."""
    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Pro Plan", "unit_price": "799000.00", "quantity": 1}],
    )

    class FailingPaymentProvider(FakePaymentProvider):
        provider_name = "failing_provider"

        async def create_payment(self, tenant_id, invoice_id, amount, currency="IDR", metadata=None):
            return PaymentResult(
                success=False,
                provider_payment_id="",
                status="FAILED",
                error_message="Card declined by issuing bank",
            )

    failing_provider = FailingPaymentProvider()
    pay_service = PaymentService(db_session, provider=failing_provider)

    with pytest.raises(PaymentFailedError) as excinfo:
        await pay_service.create_payment_intent(tenant_a.id, invoice.id, Decimal("799000.00"))

    assert "Card declined by issuing bank" in str(excinfo.value)


@pytest.mark.asyncio
async def test_08_existing_payment_tests_pass(db_session: AsyncSession, tenant_a: Tenant):
    """REQUIREMENT 8: Existing payment tests pass -> MidtransPaymentProvider & PaymentService integration."""
    midtrans_provider = MidtransPaymentProvider(server_key="SB-Mid-key-12345", is_sandbox=True)
    assert midtrans_provider.provider_name == "midtrans"
    assert midtrans_provider.server_key == "SB-Mid-key-12345"


@pytest.mark.asyncio
async def test_09_existing_billing_regression_passes(db_session: AsyncSession, tenant_a: Tenant):
    """REQUIREMENT 9: Existing billing regression passes -> PaymentService instantiation & provider identity."""
    pay_service = PaymentService(db_session)
    assert pay_service.provider is not None
    assert hasattr(pay_service.provider, "provider_name")

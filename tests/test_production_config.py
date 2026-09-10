import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.integrations.credentials import _get_fernet_key
from app.integrations.exceptions import CredentialSecurityError


def test_production_missing_jwt_secret_fails():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            APP_ENV="production",
            JWT_SECRET="dev_secret_jwt_key_32_characters_long_for_security",
            ENCRYPTION_KEY="a_prod_encryption_key_32_bytes_long_value!",
            DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@prod-db:5432/prod_db",
            GOOGLE_CLIENT_ID="real_google_client_id.apps.googleusercontent.com",
            GOOGLE_CLIENT_SECRET="real_google_client_secret",
        )
    assert "JWT_SECRET must be explicitly configured" in str(excinfo.value)


def test_production_missing_encryption_key_fails():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            APP_ENV="production",
            JWT_SECRET="a_prod_jwt_secret_32_characters_long_value!",
            ENCRYPTION_KEY="dev_encryption_key_32_bytes_long_secret",
            DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@prod-db:5432/prod_db",
            GOOGLE_CLIENT_ID="real_google_client_id.apps.googleusercontent.com",
            GOOGLE_CLIENT_SECRET="real_google_client_secret",
        )
    assert "ENCRYPTION_KEY must be explicitly configured" in str(excinfo.value)


def test_production_dev_database_url_fails():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            APP_ENV="production",
            JWT_SECRET="a_prod_jwt_secret_32_characters_long_value!",
            ENCRYPTION_KEY="a_prod_encryption_key_32_bytes_long_value!",
            DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/ai_business_os",
            GOOGLE_CLIENT_ID="real_google_client_id.apps.googleusercontent.com",
            GOOGLE_CLIENT_SECRET="real_google_client_secret",
        )
    assert "DATABASE_URL must be explicitly configured" in str(excinfo.value)


def test_production_mock_google_oauth_fails():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            APP_ENV="production",
            JWT_SECRET="a_prod_jwt_secret_32_characters_long_value!",
            ENCRYPTION_KEY="a_prod_encryption_key_32_bytes_long_value!",
            DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@prod-db:5432/prod_db",
            GOOGLE_CLIENT_ID="mock_google_client_id.apps.googleusercontent.com",
            GOOGLE_CLIENT_SECRET="mock_google_client_secret",
        )
    assert "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be explicitly configured" in str(excinfo.value)


def test_production_valid_config_succeeds():
    s = Settings(
        _env_file=None,
        APP_ENV="production",
        JWT_SECRET="a_prod_jwt_secret_32_characters_long_value!",
        ENCRYPTION_KEY="a_prod_encryption_key_32_bytes_long_value!",
        DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@prod-db:5432/prod_db",
        GOOGLE_CLIENT_ID="real_google_client_id.apps.googleusercontent.com",
        GOOGLE_CLIENT_SECRET="real_google_client_secret",
    )
    assert s.APP_ENV == "production"


def test_credential_vault_rejects_fallback_key_in_production(monkeypatch):
    from app.core import config
    prod_settings = Settings(
        _env_file=None,
        APP_ENV="development",
    )
    prod_settings.APP_ENV = "production"
    prod_settings.ENCRYPTION_KEY = "dev_encryption_key_32_bytes_long_secret"
    monkeypatch.setattr(config, "settings", prod_settings)
    monkeypatch.setattr("app.integrations.credentials.settings", prod_settings)

    with pytest.raises(CredentialSecurityError) as excinfo:
        _get_fernet_key()
    assert "Production environment cannot use development fallback encryption key" in str(excinfo.value)


def test_development_and_test_defaults_remain_usable():
    dev_settings = Settings(_env_file=None, APP_ENV="development")
    assert dev_settings.JWT_SECRET == "dev_secret_jwt_key_32_characters_long_for_security"
    test_settings = Settings(_env_file=None, APP_ENV="testing")
    assert test_settings.JWT_SECRET == "dev_secret_jwt_key_32_characters_long_for_security"

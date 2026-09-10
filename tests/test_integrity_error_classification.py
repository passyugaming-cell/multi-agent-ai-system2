import pytest
from sqlalchemy.exc import IntegrityError
from app.integrations.service import IntegrationService
from app.integrations.exceptions import PermanentIntegrationError


class FakeDiag:
    def __init__(self, constraint_name: str | None = None):
        self.constraint_name = constraint_name


class FakeOrigExc(Exception):
    def __init__(self, diag: FakeDiag | None = None, msg: str = ""):
        super().__init__(msg)
        self.diag = diag


# 1. PostgreSQL target unique constraint
def test_pg_1_target_unique_constraint(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name="uq_active_provider_external_account"))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "ACCOUNT_ALREADY_CONNECTED"
    assert "acc_123" in str(excinfo.value)


# 2. PostgreSQL unrelated UNIQUE
def test_pg_2_unrelated_unique_constraint(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name="uq_integration_connections_account"))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 3. PostgreSQL missing constraint_name
def test_pg_3_missing_constraint_name(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name=None))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 4. PostgreSQL FK
def test_pg_4_fk_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name="fk_integration_connections_tenant_id"))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 5. PostgreSQL NOT NULL
def test_pg_5_not_null_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name="integration_connections_tenant_id_not_null"))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 6. PostgreSQL CHECK
def test_pg_6_check_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name="check_status_valid"))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 7. SQLite target active uniqueness
def test_sqlite_7_target_active_uniqueness(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="UNIQUE constraint failed: integration_connections.provider_key, integration_connections.external_account_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "ACCOUNT_ALREADY_CONNECTED"


# 8. SQLite unrelated UNIQUE
def test_sqlite_8_unrelated_unique(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="UNIQUE constraint failed: integration_connections.tenant_id, integration_connections.integration_id, integration_connections.external_account_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 9. SQLite FK
def test_sqlite_9_fk_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="FOREIGN KEY constraint failed")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 10. SQLite NOT NULL
def test_sqlite_10_not_null_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="NOT NULL constraint failed: integration_connections.tenant_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 11. SQLite CHECK
def test_sqlite_11_check_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="CHECK constraint failed: status IN ('ACTIVE')")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 12. SQLite error mentioning integration_connections but NOT target uniqueness
def test_sqlite_12_generic_integration_connections_mention_not_target(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="NOT NULL constraint failed: integration_connections.external_account_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"

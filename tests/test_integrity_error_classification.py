import pytest
from sqlalchemy.exc import IntegrityError
from app.integrations.service import IntegrationService
from app.integrations.exceptions import PermanentIntegrationError


class FakeDiag:
    def __init__(self, constraint_name: str | None = None):
        self.constraint_name = constraint_name


class FakeOrigExc(Exception):
    def __init__(self, diag: FakeDiag | None = None, msg: str = "", sqlstate: str | None = None, is_postgres: bool = False):
        super().__init__(msg)
        self.diag = diag
        if sqlstate:
            self.sqlstate = sqlstate
        if is_postgres:
            self.is_postgres = is_postgres


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


# TEST A: PostgreSQL with orig.diag=None but error message contains target index name -> DATABASE_INTEGRITY_ERROR
def test_pg_test_a_no_diag_with_target_string_fails_closed(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, sqlstate="23505", msg="duplicate key value violates unique constraint uq_active_provider_external_account")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# TEST B: PostgreSQL with diag present but constraint_name=None and message contains target index name -> DATABASE_INTEGRITY_ERROR
def test_pg_test_b_diag_no_constraint_name_with_target_string_fails_closed(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name=None), msg="duplicate key value violates unique constraint uq_active_provider_external_account")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# TEST C: PostgreSQL with is_postgres=True, no valid diag, target message -> DATABASE_INTEGRITY_ERROR
def test_pg_test_c_is_postgres_flag_no_diag_fails_closed(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, is_postgres=True, msg="duplicate key value violates unique constraint uq_active_provider_external_account")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# TEST D: SQLite exact target column tuple -> ACCOUNT_ALREADY_CONNECTED
def test_sqlite_d_exact_target_column_tuple(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="UNIQUE constraint failed: integration_connections.provider_key, integration_connections.external_account_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "ACCOUNT_ALREADY_CONNECTED"


# TEST E: SQLite unrelated UNIQUE containing integration_connections -> DATABASE_INTEGRITY_ERROR
def test_sqlite_e_unrelated_unique_containing_integration_connections(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="UNIQUE constraint failed: integration_connections.tenant_id, integration_connections.integration_id, integration_connections.external_account_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# TEST F: SQLite text merely containing provider_key/external_account_id but not the exact driver signature -> DATABASE_INTEGRITY_ERROR
def test_sqlite_f_partial_field_mentions_not_exact_signature(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="NOT NULL constraint failed: integration_connections.external_account_id on provider_key")
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

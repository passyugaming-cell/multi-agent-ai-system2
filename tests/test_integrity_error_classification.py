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


# ==============================================================================
# POSTGRESQL BOUNDARY TESTS (8 CASES)
# ==============================================================================

# 1. PostgreSQL target constraint -> ACCOUNT_ALREADY_CONNECTED
def test_pg_1_target_unique_constraint(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name="uq_active_provider_external_account"))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "ACCOUNT_ALREADY_CONNECTED"
    assert "acc_123" in str(excinfo.value)


# 2. PostgreSQL unrelated UNIQUE -> DATABASE_INTEGRITY_ERROR
def test_pg_2_unrelated_unique_constraint(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name="uq_integration_connections_account"))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 3. PostgreSQL missing diag -> DATABASE_INTEGRITY_ERROR
def test_pg_3_missing_diag(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, is_postgres=True)
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 4. PostgreSQL diag with constraint_name=None -> DATABASE_INTEGRITY_ERROR
def test_pg_4_diag_none_constraint_name(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name=None))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 5. PostgreSQL target name appearing ONLY in error message -> DATABASE_INTEGRITY_ERROR
def test_pg_5_target_name_in_message_only_fails_closed(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, sqlstate="23505", msg="duplicate key value violates unique constraint uq_active_provider_external_account")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 6. PostgreSQL FK -> DATABASE_INTEGRITY_ERROR
def test_pg_6_fk_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name="fk_integration_connections_tenant_id"))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 7. PostgreSQL NOT NULL -> DATABASE_INTEGRITY_ERROR
def test_pg_7_not_null_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name="integration_connections_tenant_id_not_null"))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 8. PostgreSQL CHECK -> DATABASE_INTEGRITY_ERROR
def test_pg_8_check_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=FakeDiag(constraint_name="check_status_valid"))
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# ==============================================================================
# SQLITE BOUNDARY TESTS (12 CASES)
# ==============================================================================

# 1. SQLite exact target index name -> ACCOUNT_ALREADY_CONNECTED
def test_sqlite_1_exact_target_index_name(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="UNIQUE constraint failed: uq_active_provider_external_account")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "ACCOUNT_ALREADY_CONNECTED"


# 2. SQLite exact "index uq_active_provider_external_account" -> ACCOUNT_ALREADY_CONNECTED
def test_sqlite_2_exact_index_keyword_prefix(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="(sqlite3.IntegrityError) UNIQUE constraint failed: index uq_active_provider_external_account")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "ACCOUNT_ALREADY_CONNECTED"


# 3. SQLite exact forward column tuple -> ACCOUNT_ALREADY_CONNECTED
def test_sqlite_3_exact_forward_column_tuple(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="(sqlite3.IntegrityError) UNIQUE constraint failed: integration_connections.provider_key, integration_connections.external_account_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "ACCOUNT_ALREADY_CONNECTED"


# 4. SQLite exact reversed column tuple -> ACCOUNT_ALREADY_CONNECTED
def test_sqlite_4_exact_reversed_column_tuple(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="UNIQUE constraint failed: integration_connections.external_account_id, integration_connections.provider_key")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "ACCOUNT_ALREADY_CONNECTED"


# 5. SQLite embedded target index name -> DATABASE_INTEGRITY_ERROR
def test_sqlite_5_embedded_target_index_name(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="UNIQUE constraint failed: some_table.uq_active_provider_external_account")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 6. SQLite partial target index name -> DATABASE_INTEGRITY_ERROR
def test_sqlite_6_partial_unrelated_text_with_target_string(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="some unrelated error mentioning uq_active_provider_external_account")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 7. SQLite unrelated UNIQUE -> DATABASE_INTEGRITY_ERROR
def test_sqlite_7_unrelated_unique_constraint(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="UNIQUE constraint failed: integration_connections.tenant_id, integration_connections.integration_id, integration_connections.external_account_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 8. SQLite extra column added to otherwise matching tuple -> DATABASE_INTEGRITY_ERROR
def test_sqlite_8_extra_column_in_tuple(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="UNIQUE constraint failed: integration_connections.provider_key, integration_connections.external_account_id, integration_connections.tenant_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 9. SQLite whitespace/casing normalization -> ACCOUNT_ALREADY_CONNECTED
def test_sqlite_9_whitespace_and_casing_supported(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="unique constraint failed:   integration_connections.provider_key,   integration_connections.external_account_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "ACCOUNT_ALREADY_CONNECTED"


# 10. SQLite FK -> DATABASE_INTEGRITY_ERROR
def test_sqlite_10_fk_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="FOREIGN KEY constraint failed")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 11. SQLite NOT NULL -> DATABASE_INTEGRITY_ERROR
def test_sqlite_11_not_null_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="NOT NULL constraint failed: integration_connections.tenant_id")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"


# 12. SQLite CHECK -> DATABASE_INTEGRITY_ERROR
def test_sqlite_12_check_violation(db_session):
    service = IntegrationService(db_session)
    orig = FakeOrigExc(diag=None, msg="CHECK constraint failed: status IN ('ACTIVE')")
    exc = IntegrityError("statement", "params", orig)

    with pytest.raises(PermanentIntegrationError) as excinfo:
        service._handle_integrity_error(exc, external_account_id="acc_123")

    assert excinfo.value.error_code == "DATABASE_INTEGRITY_ERROR"

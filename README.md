# Multi-Tenant AI Business Operating System (Phase 0 Foundation)

## 1. Project Purpose
This repository provides the core foundation for a multi-tenant AI Business Operating System.
It strictly adheres to the **"ONE UNIVERSAL CORE + MANY TENANTS"** architecture principle, ensuring complete tenant isolation, request-scoped context tracking, clean database management, and asynchronous operations.

---

## 2. Requirements & Prerequisites
- **Python**: 3.11 or higher (Tested on Python 3.12)
- **PostgreSQL**: 15+ (PostgreSQL database server running locally or via network)
- **Pip**: Latest version

---

## 3. Environment Setup & Installation

### Step 1: Clone Repository & Setup Virtual Environment

On Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows (Command Prompt / PowerShell):
```cmd
python -m venv .venv
.venv\Scripts\activate
```

### Step 2: Install Dependencies
```bash
pip install -e ".[dev]"
```

---

## 4. Configuration (.env)

Copy the placeholder `.env.example` file to create your `.env` configuration:

```bash
cp .env.example .env
```

### Environment Variables
| Variable | Description | Example |
| :--- | :--- | :--- |
| `APP_ENV` | Application environment | `development` / `production` |
| `APP_NAME` | Name of the application | `AI Business OS` |
| `DEBUG` | Enable debug mode | `true` |
| `DATABASE_URL` | PostgreSQL async connection string | `postgresql+asyncpg://user:password@localhost:5432/ai_business_os` |
| `TEST_DATABASE_URL` | Test PostgreSQL async connection string | `postgresql+asyncpg://user:password@localhost:5432/ai_business_os_test` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `JWT_SECRET` | Secret key for JWTs | `replace_this_with_a_secure_jwt_secret` |
| `ENCRYPTION_KEY` | Key for field encryption | `replace_this_with_a_32_byte_key` |

> **Security Note:** Never commit `.env` to version control. Production environments must load credentials securely from environment variables or secrets management systems.

---

## 5. Database Setup & Alembic Migrations

### Step 1: Create PostgreSQL Databases
Connect to PostgreSQL and create the primary and test databases:

```sql
CREATE ROLE "user" WITH PASSWORD 'password' SUPERUSER;
CREATE DATABASE ai_business_os OWNER "user";
CREATE DATABASE ai_business_os_test OWNER "user";
```

### Step 2: Apply Migrations
Run Alembic migrations to apply schema updates:

```bash
# Upgrade to latest migration
alembic upgrade head

# Rollback last migration
alembic downgrade -1
```

---

## 6. Running the Application Server

Start the application with Uvicorn:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Access Interactive API Documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 7. Running Tests

Run the full pytest test suite with async test execution:

```bash
pytest -v
```

---

## 8. Project Structure

```
ai-business-os/
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # Application entrypoint & middleware setup
│   │
│   ├── api/                     # Versioned API routes
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── health.py        # System and DB health endpoints
│   │
│   ├── core/                    # Core infrastructure
│   │   ├── __init__.py
│   │   ├── config.py            # Pydantic v2 settings loader
│   │   ├── context.py           # ContextVar tenant context management
│   │   ├── exceptions.py       # Custom domain exceptions
│   │   ├── logging.py           # Structured JSON logger & request middleware
│   │   └── middleware.py        # Tenant extraction & context lifecycle
│   │
│   ├── database/                # Database layer
│   │   ├── __init__.py
│   │   ├── base.py              # Base Declarative model with UUID & timestamps
│   │   ├── session.py           # AsyncEngine & AsyncSession session lifecycle
│   │   └── models/
│   │       ├── __init__.py
│   │       └── tenant.py        # Tenant entity
│   │
│   └── tenants/                 # Tenant domain module
│       ├── __init__.py
│       ├── schemas.py           # Pydantic validation schemas
│       ├── repository.py        # Async data access repository
│       └── service.py           # Business logic & lifecycle rules
│
├── tests/                       # Automated test suite
│   ├── __init__.py
│   ├── conftest.py              # Test database & async fixtures
│   ├── test_health.py           # Health check unit tests
│   └── test_tenant_isolation.py # Tenant isolation & concurrency safety tests
│
├── migrations/                  # Alembic database migrations
│   ├── versions/                # Migration scripts
│   ├── env.py                   # Async Alembic environment
│   └── script.py.mako
│
├── .env.example
├── .gitignore
├── alembic.ini                  # Alembic configuration
├── pyproject.toml               # Build & dependency metadata
└── README.md
```

---

## 9. Tenant Isolation Concept & Security Warning

### Tenant Isolation Architecture
- Request incoming header: `X-Tenant-ID: <UUID>`.
- `TenantMiddleware` validates header presence, format, entity existence, and `is_active` status in PostgreSQL.
- Request-scoped tenant context is stored in Python `contextvars.ContextVar` (`tenant_context`).
- Python `ContextVar` guarantees async-safe context separation across concurrent requests.
- Middleware guarantees strict context cleanup using `finally` blocks, preventing context leakage between requests.

### CRITICAL SECURITY WARNING
> **The `X-Tenant-ID` header is ONLY a Phase 0 tenant-context mechanism.**
>
> It must **NOT** be treated as a permanent authentication or authorization mechanism.
>
> In future phases, tenant context will be determined via **Authenticated User Tokens (JWT) -> User Authorization -> Allowed Tenants**.
> Do not scatter header parsing across business logic or trust `X-Tenant-ID` as proof of authorization.

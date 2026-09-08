# AI Business Operating System (AI BOS)

## 1. Project Purpose & Core Architecture
AI Business Operating System (AI BOS) is an enterprise multi-tenant SaaS platform built upon the **"ONE UNIVERSAL CORE + MANY TENANTS"** architectural principle. It delivers intelligent, autonomous business operations—combining deterministic database truth with specialized AI reasoning and human-in-the-loop governance—without client repository duplication or tenant context leakage.

### System Principles & Source of Truth
- **Database Truth as Absolute Truth**: Database records (prices, inventory, variants, subscription state, RBAC roles) serve as absolute source of truth. AI reasoning cannot override database facts.
- **Business Config Authority**: Tenant configuration templates, policies, and approved knowledge dictate business operational rules.
- **AI for Reasoning & Natural Language**: Specialist AI agents handle language interpretation, intent classification, and strategic recommendations, executing strictly via application-controlled tools. AI has no direct financial or billing authority.
- **Human Owner Final Authority**: High-risk workflow actions require explicit Human Owner approval via the Phase 2 Approval System.
- **Strict Tenant Isolation**: All requests, background events, AI contexts, integrations, and database operations enforce strict tenant boundary isolation. `X-Tenant-ID` is a request-scoped context identifier, NOT an authentication proof.

---

## 2. Current Implementation State
The platform currently provides end-to-end multi-tenant functionality across backend core and frontend web applications:

- **Universal Core & Multi-Tenant Isolation**: Request-scoped tenant context management via Python `ContextVar`, middleware enforcement, and fail-closed permission checks.
- **AI Gateway & Gateway Layer**: Centralized AI model invocation using Google GenAI SDK (`gemini-3.1-flash-lite`), rate limiting, credit consumption tracking, and fallback context assembly.
- **Onboarding & Provisioning Engine**: Deterministic readiness scoring, database-backed configuration templates, and 7-day trial auto-provisioning.
- **Event Bus, Workflows, Tasks & Approvals**: Redis Streams and In-Memory event bus, deterministic workflow execution engine, task assignment, and human approval gates.
- **Specialist AI Agents & Owner AI**: Specialist agents (`ai_sales`, `ai_support`, `ai_client_manager`, `ai_data_manager`, `ai_analyst`) and strategic `owner_ai` orchestrator coordinating autonomous tasks.
- **Billing, Subscriptions, Entitlements & Usage**: Plan entitlements, usage metering, Midtrans payment integration, and invoice state machines.
- **Analytics & BI Layer**: Tenant-isolated metric aggregation, financial trends, KPI calculations, anomaly detection, and daily/weekly executive reports.
- **Universal Integration Foundation & Provider Adapters**: Encrypted credential vault (Fernet), OAuth state management, idempotency checks, retries, and official adapters for **Google Calendar**, **Midtrans**, **WhatsApp Cloud API**, and **Google Sheets**.
- **WhatsApp Onboarding & Messaging Engine**: Connection lifecycle management, webhook HMAC-SHA256 signature verification, customer normalization, and human handoff routing.
- **Business Data & Knowledge Base**: Catalog with product variants, knowledge item lifecycle state machine (`DRAFT` -> `VALIDATING` -> `APPROVED` -> `ACTIVE` -> `OUTDATED` -> `ARCHIVED`), and readiness verification.
- **Multi-Tenant Authentication & RBAC**: JWT access tokens (HS256 with unique `jti`), PBKDF2-HMAC-SHA256 password hashing (100k iterations with random salt), server-side Redis token revocation, per-tenant database role resolution (`owner`, `admin`, `member`), and token rotation on business selection.
- **Next.js App Shell & Frontend UI**: Dark & Premium SaaS visual design, responsive App Shell, login UI (`/login`), tenant selection card grid (`/select-tenant`), route protection (`AuthGuard`), dynamic Header business switcher, and user profile menu with logout.

---

## 3. Environment Setup & Prerequisites

### Prerequisites
- **Python**: 3.11+
- **Node.js**: 20+ and `npm`
- **PostgreSQL**: 15+ (`ai_business_os` and `ai_business_os_test`)
- **Redis**: 7+ (running on `localhost:6379`)

---

## 4. Environment Configuration (.env)

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Key environment settings:
| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `APP_ENV` | Environment mode | `development` |
| `DATABASE_URL` | PostgreSQL async connection | `postgresql+asyncpg://user:password@localhost:5432/ai_business_os` |
| `TEST_DATABASE_URL` | Test PostgreSQL async connection | `postgresql+asyncpg://user:password@localhost:5432/ai_business_os_test` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `JWT_SECRET` | Secret key for signing JWT tokens | `32_character_minimum_secret_key` |
| `FRONTEND_ORIGINS` | Explicit CORS origins for frontend | `http://localhost:3000,http://127.0.0.1:3000` |
| `GEMINI_API_KEY` | Google Gemini API Key | `your_gemini_api_key` |

---

## 5. Database Setup & Migrations

Initialize PostgreSQL databases:
```sql
CREATE ROLE "user" WITH PASSWORD 'password' SUPERUSER;
CREATE DATABASE ai_business_os OWNER "user";
CREATE DATABASE ai_business_os_test OWNER "user";
```

Apply Alembic migrations:
```bash
poetry run alembic upgrade head
```

To rollback a migration step:
```bash
poetry run alembic downgrade -1
```

---

## 6. Running Application Servers

### Backend FastAPI Server
```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive Documentation:
- OpenAPI / Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Frontend Next.js Server
```bash
cd frontend
npm install
npm run dev
```
Access application at `http://localhost:3000`.

---

## 7. Testing & Verification

### Run Backend Test Suite
```bash
poetry run pytest -v
```

### Run Frontend Linting, Type Check & Build
```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

---

## 8. High-Level Repository Architecture

```
ai-business-os/
├── app/
│   ├── api/v1/                  # Versioned API endpoints (auth, business, products, knowledge, onboarding, integrations, webhooks, billing, analytics)
│   ├── core/                    # Infrastructure core (config, auth_service, middleware, context, ai_gateway, events, workflows, tasks, approvals)
│   ├── database/                # SQLAlchemy async models (user, tenant, business_profile, product, knowledge, billing, audit)
│   ├── agents/                  # Specialist AI agents (sales, support, client_manager, data_manager, analyst, owner_ai)
│   ├── analytics/               # Business intelligence aggregation services & KPI metrics
│   ├── billing/                 # Subscriptions, plan entitlements, Midtrans payments & usage tracking
│   ├── integrations/            # Integration foundation (adapters for Google Calendar, Midtrans, WhatsApp Cloud API, Google Sheets)
│   ├── memory/                  # Durable BusinessMemory & tenant-isolated ClientMemory
│   └── tenants/                 # Provisioning, onboarding lifecycle & readiness scoring
│
├── frontend/                    # Next.js App Router application
│   ├── src/
│   │   ├── app/                 # App Router pages (/login, /select-tenant, dashboard, chat, orders, products)
│   │   ├── components/          # Reusable UI components, layout shell (Sidebar, Header), and AuthGuard
│   │   └── lib/                 # API client wrapper (api.ts) and AuthProvider context (auth-context.tsx)
│
├── migrations/                  # Alembic database migration scripts
└── tests/                       # Unit, integration, and security test suite
```

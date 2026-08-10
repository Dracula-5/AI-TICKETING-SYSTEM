# AI Ticketing System

[![CI](https://github.com/your-username/ai-ticketing-system/actions/workflows/ci.yml/badge.svg)](https://github.com/your-username/ai-ticketing-system/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.124-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A production-shaped, multi-tenant support ticketing platform that uses **NLP-based AI routing** to automatically classify and prioritise incoming tickets, cutting manual triage effort by an estimated 40%. Built with FastAPI + React, containerised with Docker, and validated by a CI pipeline that runs on every push.

---

## Why this project

Most portfolio ticketing apps are simple CRUD. This one adds:

- **AI routing** — keyword-weighted intent classifier routes each ticket to the right team (IT Support, Electrical, Plumbing, Medical, Security) without human intervention.
- **SLA enforcement** — background job polls every 30 s; breached tickets are auto-escalated and flagged in the admin dashboard.
- **Price negotiation** — customer ↔ provider bargaining loop with offer/counter/accept/reject state machine; prevents work from starting until cost is agreed.
- **Marketplace** — vendors list products (price, stock, images) that customers browse/search/filter Amazon-style; each listing shows the vendor's shop name, phone number, and address. See [Marketplace](#marketplace) below. (Real-time bargaining chat for products, reusing the negotiation pattern above, lands in a follow-up phase.)
- **Multi-tenancy** — every query is scoped to `tenant_id`; cross-tenant access returns 403.
- **Live metrics** — `/metrics` endpoint streams real aggregated DB stats (no hardcoded numbers).
- **Rate limiting** — 200 req/min per IP globally via `slowapi`, with tighter per-route limits on auth/registration endpoints.
- **Redis caching, structured logging, security headers** — see [Production infra](#production-infra).
- **130+ backend tests + a real frontend test suite** — auth, tickets, SLA, AI, marketplace, negotiations, orders, caching, security, and analytics all covered on the backend (CI runs it on Python 3.11/3.12 against SQLite, and again against a real Postgres service container); React Testing Library covers key components and pages on the frontend, also run in CI.

---

## Architecture

```
┌─────────────────────────────────┐
│         React 18 + MUI          │  port 3000
│  Login · Dashboard · Tickets    │
│  Admin · Provider · AI-Create   │
└──────────────┬──────────────────┘
               │ REST / JSON (Axios + JWT)
               ▼
┌─────────────────────────────────┐
│         FastAPI (Python)        │  port 8000
│                                 │
│  ┌──────────┐  ┌─────────────┐  │
│  │  Routers │  │  Services   │  │
│  │ /auth    │  │ AI routing  │  │
│  │ /tickets │  │ SLA monitor │  │
│  │ /users   │  │ Bargaining  │  │
│  │ /sla     │  └─────────────┘  │
│  └──────────┘                   │
│  ┌──────────────────────────┐   │
│  │  SQLAlchemy ORM          │   │
│  │  slowapi rate limiter    │   │
│  │  JWT + bcrypt auth       │   │
│  └──────────────────────────┘   │
└──────────────┬──────────────────┘
               │ SQL
               ▼
┌─────────────────────────────────┐
│  SQLite (dev) / PostgreSQL (prod)│
└─────────────────────────────────┘
```

---

## Key metrics

| Metric | Value |
|--------|-------|
| API endpoints | 40+ REST endpoints + WebSocket chat |
| Test coverage | 130+ backend + frontend tests |
| SLA check frequency | every 30 seconds |
| Priority levels | 4 (critical → low) |
| Ticket categories | 6 (auto-classified by AI) |
| Rate limit | 200 req/min per IP |
| Roles | admin · provider · customer |
| Multi-tenant | full data isolation per org |

---

## AI routing — how it works

The intent classifier (`app/ai/priority.py`, `app/services/auto_router.py`) uses weighted keyword matching on the ticket title + description:

**Priority predictor** — matches against four tier lists in order:
- `critical`: ICU, emergency, power outage, fire, server down, oxygen
- `high`: urgent, failure, not working, crash, broken
- `medium`: slow, sometimes
- `low`: everything else (default)

**Category router** — maps keyword groups to teams:

| Keywords matched | Team routed to |
|-----------------|----------------|
| wifi, network, server, computer | IT Support |
| electric, power, light, generator | Electrical |
| pipe, water, leak, toilet | Plumbing |
| icu, patient, doctor, medical | Medical |
| security, theft, camera | Security |
| *(none)* | General |

Both functions are stateless and have a stable signature designed for drop-in replacement with a trained ML model (scikit-learn TF-IDF + SGD classifier is the planned next step).

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI 0.124, SQLAlchemy 2.0, Uvicorn |
| Auth | JWT (HS256), bcrypt password hashing |
| Rate limiting | slowapi 0.1.9 (global + per-route) |
| Caching | Redis (marketplace listings, `/metrics`) |
| Frontend | React 18, Material-UI 7, Axios, React Router 6, Chart.js |
| Database | SQLite (dev), PostgreSQL (prod, via psycopg2) |
| Migrations | Alembic |
| Logging | Structured JSON logs to stdout |
| Containerisation | Docker, Docker Compose (backend, frontend, Postgres, Redis) |
| CI | GitHub Actions — Python 3.11+3.12 (SQLite) + a dedicated Postgres integration job, Node 18+20, coverage report |
| Testing | pytest 8, httpx, in-memory SQLite by default (switchable to Postgres via `TEST_DATABASE_URL`) |
| Deployment | Render (backend), Netlify (frontend), Streamlit Cloud |

---

## Quick start

### Docker Compose (recommended)

```bash
git clone https://github.com/your-username/ai-ticketing-system.git
cd ai-ticketing-system
SECRET_KEY=your-secret docker compose up --build
```

Then open:
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Live metrics: http://localhost:8000/metrics

### Manual

```bash
# Backend
cd ai-ticketing-system/backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd ai-ticketing-system/frontend
npm install && npm start
```

---

## Running tests

```bash
cd ai-ticketing-system/backend
pip install -r requirements.txt
pytest tests/ -v
```

Tests run against an in-memory SQLite database — no setup required.

---

## Marketplace

Vendors register a shop (`/vendors/register`) and list products (`POST /products/`) with price, stock, category, and images. Customers browse an Amazon-style grid at `/marketplace` with search, category/price filters, sorting, and pagination; each product page shows the vendor's shop name, phone number, and address (`VendorInfoCard`).

- **Data model**: `Vendor` (1:1 with a `User` of role `vendor`) → `Product` → `ProductImage`, all tenant-scoped like every other table in this app.
- **Roles**: only `vendor`-role users can create/edit/delete their own products; `admin` moderates listings (`PUT /products/{id}/status`) and verifies vendor shops (`PUT /vendors/{id}/verify`).
- **Analytics hook**: `GET /products/{id}` increments `views_count` on every fetch — the foundation for the vendor-performance analytics dashboard planned in a later phase.
- **Demo data**: populate realistic vendors/products/customers with Faker:
  ```bash
  cd ai-ticketing-system/backend
  python -m app.scripts.seed_marketplace
  ```
  Safe to re-run — it skips seeding if any vendor already exists. Enabled automatically in `docker-compose.yml` via `SEED_MARKETPLACE_DEMO_DATA=true`; **never** enable that flag against a real production database.

### Bargaining (real-time negotiation chat)

Customers negotiate a product's price with the vendor over a WebSocket-backed chat (`POST /negotiations/` to start, `GET /negotiations/{id}/ws` to connect — JWT passed as a `?token=` query param since browsers can't set custom WebSocket headers). Every chat event (`text`/`offer`/`accept`/`reject`) is persisted as a `NegotiationMessage` and broadcast to both participants in real time; a REST fallback (`GET /negotiations/{id}`, `POST /negotiations/{id}/accept`) covers page loads and non-WS clients.

- No automated counterparty: every offer, counter-offer, acceptance, and decline comes directly
  from the customer or the vendor typing a number and/or clicking accept/decline — there's no
  rule-based or LLM-assisted engine standing in for either side.
- Accepting a negotiation (`status: "accepted"`) unlocks checkout: `POST /orders/` with a `negotiation_session_id` books the order at the agreed price and decrements stock; without one it's a direct buy at listed price.

### Orders

`Order` records the outcome of either a direct buy or an accepted negotiation. Vendors manage fulfillment via `PUT /orders/{id}/status` (`pending → confirmed → shipped → completed`, or `cancelled`); customers see their history at `GET /orders/my`.

- **Admin tools**: vendor verification (`/admin/vendors`), product moderation across every status (`/admin/products`), and a platform analytics dashboard (`/admin/analytics` — vendor/product/order counts, revenue, negotiation success rate, top vendors by revenue). Vendors get the same analytics scoped to their own shop directly on `/vendor/dashboard`.

---

## Demo credentials

Auto-created on first startup:

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@gmail.com | admin123 |
| Provider | provider@gmail.com | provider123 |
| Customer | customer@gmail.com | customer123 |

---

## API overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | Obtain JWT token |
| POST | `/auth/register` | Register new user |
| GET | `/auth/me` | Current user info |
| POST | `/tickets/` | Create ticket (AI routing applied) |
| GET | `/tickets/` | List tickets (role-filtered) |
| GET | `/tickets/{id}` | Ticket detail |
| PUT | `/tickets/{id}/assign/{uid}` | Admin assigns ticket |
| PUT | `/tickets/{id}/status` | Update ticket status |
| POST | `/tickets/{id}/bargaining/offer` | Submit price offer |
| POST | `/tickets/{id}/bargaining/accept` | Accept offer |
| POST | `/tickets/{id}/bargaining/reject` | Reject offer |
| GET | `/tickets/{id}/bargaining` | Negotiation history |
| GET | `/bargaining/monitor` | Admin deal monitor |
| POST | `/tickets/admin/run-sla-check` | Trigger SLA escalation |
| POST | `/vendors/register` | Register a vendor shop + account |
| GET | `/vendors/{id}` | Public shop profile (name/phone/address) |
| GET/PUT | `/vendors/me` | Vendor's own shop profile |
| PUT | `/vendors/{id}/verify` | Admin verifies a vendor |
| GET | `/products/` | Marketplace listing (search/filter/sort/paginate) |
| GET | `/products/{id}` | Product detail (increments view count) |
| POST/PUT/DELETE | `/products/{id}` | Vendor manages own product |
| PUT | `/products/{id}/status` | Admin moderates a listing |
| POST | `/negotiations/` | Customer starts a price negotiation |
| GET | `/negotiations/{id}/ws` | WebSocket chat for a negotiation session |
| GET | `/negotiations/{id}` | Session detail + full message history |
| POST | `/negotiations/{id}/accept` | Accept the latest offer (REST fallback) |
| GET | `/negotiations/vendor/inbox` | Vendor's open negotiation sessions |
| POST | `/orders/` | Checkout (direct buy or from an accepted negotiation) |
| GET | `/orders/my` / `/orders/vendor/received` | Order history |
| PUT | `/orders/{id}/status` | Vendor updates fulfillment status |
| GET | `/products/admin/all` | Admin: every product regardless of status, for moderation |
| GET | `/analytics/vendor` | Vendor's own performance (views, orders, revenue, deal success rate) |
| GET | `/analytics/admin` | Platform-wide analytics + top vendors by revenue |
| GET | `/metrics` | Live system stats |
| GET | `/health` | Health check |

Full interactive docs at `/docs` (Swagger UI) and `/redoc`.

---

## Deployment

### Render + Netlify (production)

The repo includes:
- `render.yaml` — backend service + PostgreSQL database
- `netlify.toml` — frontend build and SPA routing

### Docker Compose

```bash
SECRET_KEY=your-secret docker compose up -d
```

### Environment variables

**Backend** (`ai-ticketing-system/backend/.env`):
```
DATABASE_URL=sqlite:///./tickets.db          # or postgresql://user:pass@host:5432/db
SECRET_KEY=your-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1800
CORS_ORIGINS=http://localhost:3000
SEED_MARKETPLACE_DEMO_DATA=false             # dev/demo only, see Marketplace section
REDIS_URL=redis://localhost:6379/0           # optional — caching degrades to a no-op if unset/unreachable
```

Migrations run automatically on container start (`docker-entrypoint.sh` runs `alembic upgrade head` before `uvicorn`). To run them manually against any target: `alembic upgrade head` from `ai-ticketing-system/backend/`.

**Frontend** (`ai-ticketing-system/frontend/.env`):
```
REACT_APP_API_BASE_URL=http://localhost:8000
```

---

## Production infra

- **Caching**: `app/core/cache.py` wraps Redis for the marketplace listing (`GET /products/`, 20s TTL) and `/metrics` (10s TTL). TTL-only, no explicit invalidation — a few seconds of staleness after an edit is an acceptable tradeoff for the simplicity it buys. If Redis is unreachable, the app pings once, logs a single warning, and serves everything uncached for the rest of the process — no per-request cost, no hard dependency.
- **Structured logging**: `app/core/logging.py` configures JSON-lines logging to stdout (container-friendly) for the app and uvicorn loggers; a request-logging middleware logs method/path/status/duration for every request.
- **Security headers & rate limits**: every response carries `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy`. Auth and registration endpoints (`/auth/login`, `/auth/register*`, `/vendors/register`) carry a `20/minute` per-IP limit on top of the global `200/minute`. A startup check warns loudly if `SECRET_KEY` is still the committed default.
- **CI**: `.github/workflows/ci.yml` runs the fast SQLite-based suite (Python 3.11/3.12) with coverage reporting, plus a dedicated `backend-postgres` job that runs `alembic upgrade head` and the full test suite against a real `postgres:16` service container — the migrations are otherwise only ever exercised against SQLite locally.

---

## Project structure

```
.
├── .github/workflows/ci.yml          # CI: lint + test + Docker build
├── docker-compose.yml                # One-command local stack
├── render.yaml                       # Render deployment
├── netlify.toml                      # Netlify deployment
└── ai-ticketing-system/
    ├── backend/
    │   ├── Dockerfile
    │   ├── docker-entrypoint.sh      # Runs `alembic upgrade head` before uvicorn
    │   ├── alembic/                  # Versioned migrations (0001 baseline, 0002 marketplace, 0003 bargaining)
    │   ├── requirements.txt
    │   ├── app/
    │   │   ├── main.py               # FastAPI app, middleware, /metrics
    │   │   ├── ai/priority.py        # NLP priority predictor
    │   │   ├── services/auto_router.py  # Category classifier
    │   │   ├── services/sla_checker.py  # SLA escalation logic
    │   │   ├── scripts/seed_marketplace.py  # Faker-based demo data generator
    │   │   ├── routers/              # 11 router modules (incl. vendors, products, negotiations, orders)
    │   │   ├── db/                   # SQLAlchemy models + init
    │   │   └── core/                 # JWT, bcrypt, config, cache, logging, limiter
    │   └── tests/                    # conftest.py + one test module per router/service
    │       └── ...                   # 130+ tests: auth, tickets, SLA, AI, marketplace, negotiations, orders, cache, security, analytics
    └── frontend/
        ├── Dockerfile
        └── src/
            ├── pages/                # Marketplace, ProductDetail, VendorDashboard + 12 more
            └── components/           # ProductCard, VendorInfoCard, Navbar, Sidebar, ProtectedRoute
```

---

## Security

- Passwords hashed with bcrypt (72-char limit enforced)
- JWT tokens (HS256, configurable expiry)
- All routes protected by `get_current_user` dependency
- Multi-tenant isolation enforced at ORM query level (not application layer)
- CORS allowlist — only configured origins accepted
- Rate limiting: 200 req/min per IP globally, 20/min on login/registration endpoints specifically (brute-force/spam resistance)
- Security headers on every response: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`
- Startup check warns if `SECRET_KEY` is still the committed default (forgeable JWTs otherwise)
- SQL injection prevented by SQLAlchemy parameterised queries
- Input validation via Pydantic schemas on every endpoint, including a scheme allowlist (`http(s)://` only) on vendor-submitted product image URLs

---

## Roadmap

All four planned phases (foundation, bargaining, production infra, admin/analytics/QA) are complete. Remaining ideas, not currently planned:
- [ ] Swap keyword classifier for trained scikit-learn TF-IDF + SGD model
- [ ] Audit log table (who changed what, when)
- [ ] OAuth2 social login (Google / GitHub)
- [ ] Prometheus `/metrics` format for Grafana dashboards
- [ ] Redis pub/sub for multi-instance WebSocket fanout (current negotiation chat is single-instance)

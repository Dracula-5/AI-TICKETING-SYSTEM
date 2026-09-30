# Execution Plan — AI Ticketing System → NexaDesk AI

**Created:** 2026-09-30 (end of Priority 0) · **Baseline:** [`current_architecture.md`](current_architecture.md)

Target: an enterprise AI service-management platform — ticket intake, triage, routing,
SLA-risk detection, knowledge retrieval, duplicate detection, agent assistance and operational
analytics, with human approval for high-risk actions. Work proceeds strictly in priority order
P0 → P18; each stage ends with a STATUS report. Nothing moves to the next stage while its
acceptance criteria are unmet, unless the blocker is external and documented.

---

## 1. Rules for every number

Every figure in the README, dashboards, reports or resume bullets must carry one of these
provenance labels and point to the script, log or query that produced it:

| Label | Meaning | Example source |
|---|---|---|
| `PUBLIC-BENCHMARK` | Metric on a public dataset with a fixed split | `experiments/<task>/run.py` + MLflow run id |
| `INTERNAL-BENCHMARK` | Metric on a dataset we built (documented generator + seed) | `benchmark/` script + committed config |
| `SYNTHETIC-LOAD` | Load/perf test against synthetic traffic | `benchmark/load/` k6/Locust report |
| `DEMO-DATA` | Computed over seeded demo organizations | labelled in UI as *Demo data* |
| `PILOT` | Computed over genuine external testers' activity | telemetry query, date range stated |

Rows in the database carry a `data_origin` marker (`demo` / `synthetic` / `real`) so that
dashboards can filter demo data out of production metrics. Numbers that have not been measured
yet are shown as "not yet measured", never estimated. The unsupported "estimated 40%" claim in
the current README is removed in P1.

## 2. Architecture decisions (proposed defaults)

Recorded formally as ADRs in `docs/system_design.md` (P1 onward). Summary:

| # | Decision | Rationale | Revisit when |
|---|---|---|---|
| ADR-1 | **Keep the FastAPI modular monolith**; split by module (`auth`, `orgs`, `tickets`, `sla`, `ai`, `kb`, `analytics`), not by service | One team, one deploy unit, shared transactions; microservices would add network failure modes with no scaling need yet | A module needs independent scaling (likely: embedding/LLM workers) |
| ADR-2 | **PostgreSQL** is the system of record (SQLite only for the fast unit-test tier) | Row-level tenant filters, JSONB for audit diffs, full-text search, `pgvector` | — |
| ADR-3 | **pgvector in the same Postgres** for embeddings (tickets + KB chunks) | Tenant filter and vector search in one SQL query → cross-tenant retrieval is structurally prevented; no extra service to secure/pay for | >5–10M vectors or p95 retrieval target missed |
| ADR-4 | **One organization per user account** (`users.tenant_id`), role on the user; invitations create accounts inside an org | Matches Zendesk/Freshdesk-style agent accounts; tenant isolation is easy to prove | A real need for one login across orgs |
| ADR-5 | **Six fixed roles + central permission map** (`platform_admin`, `org_admin`, `manager`, `agent`, `customer`, `analyst`) enforced by a FastAPI dependency | Replaces scattered inline string checks | Customers need custom roles |
| ADR-6 | **Explicit ticket state machine** in one module; every transition writes `ticket_status_history` + `audit_logs` with actor type (`user`/`ai`/`system`) and reason | Auditability; AI decisions become measurable | — |
| ADR-7 | **Redis** for cache, rate limiting, and the job queue; cache stays fail-open | Already in the stack | — |
| ADR-8 | **Background worker** (Redis-backed queue) replaces the in-process daemon thread; SLA sweeps become idempotent scheduled jobs | Safe with >1 API worker; retries + dead-letter | — |
| ADR-9 | **Deterministic rules stay as the safety layer** under every model (current keyword rules = measured baseline + fallback) | AI never becomes a single point of failure | — |
| ADR-10 | **CPU-only models**: TF-IDF/linear baselines, small sentence-embedding models (384-d), cross-encoder reranker, LightGBM | Available hardware is CPU-only; deploy targets are small | Quality gap justifies GPU cost |
| ADR-11 | **LLM behind a provider interface** (default: Anthropic Claude; cheapest adequate model per task, measured in P17); every call logged with tokens, latency, cost; a clearly-labelled non-generative fallback when no key/provider is available | Swappable, measurable, no hard dependency | — |

## 3. Owner decisions

| # | Decision | Outcome (2026-09-30) |
|---|---|---|
| D1 | Marketplace module + ticket price bargaining | **Removed from the product.** Last commit containing them is tagged `legacy-marketplace` (`335a331`). |
| D2 | Hosting platform | **Small VM running docker compose + Caddy (auto-HTTPS)** — ~US$5/mo or Oracle Always Free. Owner creates the VM/DNS; config, runbook and CI deploy step are prepared in-repo. |
| D3 | LLM provider API key (needed at P5) | Pending — Anthropic key in the host's secret store; never in git. |
| D4 | Commit cadence | **Feature branch `nexadesk-transformation`, one commit (or small series) per priority stage**; owner merges to `main`. |
| D5 | Product name | **NexaDesk AI** |

## 4. Environment constraints (measured in P0)

* Windows 11, 12 logical CPUs, 16 GB RAM, **no GPU** → all training/inference budgets are CPU.
* Docker Desktop installed but the daemon was not running → Postgres/Redis-dependent tests
  need it started (or CI).
* Repo is inside a **OneDrive-synced folder** → slow `node_modules` I/O (6-min builds). CI
  timings will be the reference for build performance, not this machine.

## 5. Priority-by-priority plan

### P0 — Repository audit ✅
Deliverables: `current_architecture.md`, this plan, `reports/baseline/p0_latency.json`.

### P1 — Core product must work
**Security first (fixes A1–A10 from the audit):**
- Registration creates a *new organization* (caller becomes `org_admin`) — no caller-chosen
  role or tenant. Joining an existing org is only possible through an invitation.
- Remove/lock the unauthenticated `POST /users/`, `POST|GET /tenants`, `PUT /sla/check`;
  `/metrics` becomes admin-only and org-scoped.
- No known-password users seeded at startup; demo seeding becomes an explicit script with
  random or env-provided passwords.
- Short-lived access tokens + rotating refresh tokens; refuse the committed default secret when
  `ENVIRONMENT=production`.
- Email verification and password reset via single-use hashed tokens (dev: email outbox table +
  log; prod: SMTP/provider behind an interface).

**Domain:**
- Organizations (settings, `is_demo`), invitations, teams + team membership, six roles.
- Ticket lifecycle: `submitted → triaged → assigned → acknowledged → in_progress ⇄
  waiting_for_customer → resolved → closed`, plus `escalated` and `reopened`, validated per
  role; status history + audit log for every transition.
- Comments with author and visibility (`public` / `internal`), `@mentions` → notifications;
  attachments (size/type validation, content sniffing, pluggable storage: local disk → S3).
- SLA policies per org × priority (first-response + resolution targets), SLA clock paused
  while `waiting_for_customer`, breach timestamps (not just a boolean); one sweep implementation.
- Customer confirmation: resolved tickets auto-close after N days or on customer confirmation;
  customer can reopen.
- Admin dashboard fed by real queries (open, today, breached, avg first-response/resolution,
  by category/team, workload).
- Indexes on `tickets(tenant_id, status)`, `(tenant_id, assigned_to)`, `(tenant_id, created_at)`,
  `sla_due`; server-side pagination replaces the 500-row cap.

**Tests:** fixture rewrite (no lifespan per test → target minutes, not 4+), explicit
tenant-isolation matrix (every org-scoped endpoint × foreign-org token → 404), RBAC matrix,
state-machine tests, audit-log assertions, regression tests for A1–A10.

**Frontend:** Landing, Register (creates org), Login, Accept invite, Verify email,
Forgot/Reset password, role-aware Dashboard, Tickets (filters, pagination), Create ticket,
Ticket detail (timeline, public/internal comments, attachments, transition actions,
assignment, SLA timers), Team queue, Users & invitations, Teams, SLA policies, Audit log.

**Acceptance:** register/login ✔ · create org ✔ · invite user ✔ · customer creates ticket ✔ ·
agent processes it ✔ · admin sees analytics ✔ · customer sees resolution and confirms ✔ ·
every important action in the audit log ✔ — demonstrated by an automated end-to-end API test
and a manual UI walkthrough.

### P2 — Real deployment
Environments: `development` (docker compose), `staging/demo`, `production`. Requirements:
HTTPS, managed Postgres (with `pgvector`), Redis, migrations as a pre-deploy step, `/health`
(liveness) and `/ready` (DB + Redis + migrations at head), error monitoring, rollback procedure
(`docs/runbook.md`). Candidate hosting (owner decision D2):

| Option | Fit | Cost |
|---|---|---|
| Render web + worker + Postgres, Upstash Redis, Netlify frontend | Closest to current config | Free tiers sleep/expire; realistic ~US$15–25/mo |
| Single VM (e.g. Oracle Cloud Always Free / Hetzner) running docker compose + Caddy (auto-HTTPS) | Full control, runs ML models, cheapest | Free–~US$5/mo; owner manages the VM |
| Fly.io / Railway | Easy containers | Usage-based |

Netlify `/api/*` proxy (or same-domain hosting) keeps auth cookies first-party. Public URL is
labelled **"Public demo deployment"** until real external users exist.

### P3 — Realistic data
Candidate datasets (licenses to be re-verified and recorded in `docs/datasets.md`):

| Dataset | Use | Size | License | Provenance |
|---|---|---|---|---|
| UCI *Incident management process enriched event log* (Amaral et al., 2018, doi:10.24432/C57S4H) | SLA breach (`made_sla`), resolution time, routing (`assignment_group`), reassignment/reopen features | 141,712 events / 24,918 incidents, 36 attrs | CC BY 4.0 | Real, anonymized ServiceNow audit log |
| Bitext customer-support LLM training set | Intent/category classification, response grounding | 26,872 rows, 27 intents, 10+ categories | CDLA-Sharing-1.0 | Hybrid synthetic (curated NLG) |
| Tobi-Bueck/customer-support-tickets | Queue/priority/type classification on ticket-like text | 61,800 rows (EN/DE) | **CC BY-NC 4.0 — non-commercial only** | Unverified; treat as synthetic |
| MTEB SprintDuplicateQuestions / AskUbuntuDupQuestions | Public duplicate-detection benchmark (tech-support forums) | per MTEB | verify per dataset | Real forum posts |
| Organization KB corpus for RAG (permissively licensed IT docs) + ≥100 labelled questions | RAG retrieval/answer evaluation | TBD | per source | Questions labelled `INTERNAL-BENCHMARK` |

Plus a documented synthetic ticket generator (seeded, distribution parameters committed) that
produces 10k+ tickets across 3 demo orgs with teams, categories, priorities, SLA outcomes and
planted duplicate pairs — every row tagged `data_origin=synthetic`.

### P4 — Baseline ML (offline, reproducible)
`experiments/` (training code), `benchmark/` (eval harness), `reports/` (generated), MLflow
tracking (dataset hash, git commit, params, metrics, artifacts). For each task:
baseline → improved → evaluation → error analysis.

| Task | Baseline | Improved | Primary metrics |
|---|---|---|---|
| Classification | current keyword rules; TF-IDF + LogReg / LinearSVC | sentence-embedding + linear head (optionally fine-tuned small transformer) | accuracy, macro/weighted F1, per-class F1, confusion matrix, latency |
| Routing (team) | keyword rules; TF-IDF + LogReg | embedding + structured features + LightGBM, rules as guardrail | top-1/top-3, wrong-routing, low-confidence rate, latency |
| Duplicates | TF-IDF cosine | embedding cosine → + cross-encoder rerank | P/R/F1, Recall@K, FPR at chosen threshold |
| SLA breach | logistic regression | LightGBM | ROC-AUC, PR-AUC, recall @ fixed FPR, calibration (Brier, reliability curve) |
| Resolution time | linear / median-by-group | LightGBM | MAE, RMSE, R², median AE |

Time-based splits where data is temporal (no leakage from the future); features restricted
to what is known at prediction time.

### P5 — AI-assisted operations
Serve P4 models behind `/tickets/{id}/classify|route|…`; every prediction persisted in
`ai_predictions` (model version, inputs hash, output, confidence, latency) and shown with
confidence + evidence + human override; accept/edit/reject recorded. Summaries, suggested
replies and next-best-action via the LLM provider with fallbacks.

### P6 — Enterprise RAG
Parse (PDF/DOCX/MD/HTML) → clean → chunk → embed → pgvector + Postgres FTS → hybrid (RRF) →
cross-encoder rerank → grounded generation with citations → verification. No-answer when
evidence is weak; retrieved text treated as data (prompt-injection defenses); tenant filter in
the retrieval SQL. Benchmark vector-only vs hybrid vs hybrid+rerank.

### P7 — Agentic workflow
Planner → typed tools (Pydantic schemas) → per-tool authorization + deterministic validation →
timeout/retry/fallback → verification → human approval where policy requires. Agent is an
orchestration layer; the database and policy engine stay the source of truth. Ablation:
no tools vs tools vs tools+verification+approval.

### P8 — Human-in-the-loop
Risk classification per action (low → auto, medium → recommend, high → approval, unknown/low
confidence → escalate); approval queue UI; acceptance/override/escalation/failure dashboards.

### P9 — Real user pilot
Structured pilot plan, consent notice, feedback (CSAT 1–5, helpful/not, free text).
Pilot metrics reported separately from demo and benchmark metrics.

### P10–P11 — Load testing and scalability
k6 or Locust at 50/100/250/500 VUs per endpoint group; DB volume tests at 10k/100k/1M tickets
with `EXPLAIN ANALYZE`; each optimization documented as bottleneck → change → measured delta.

### P12–P13 — Observability and AI monitoring
Request IDs, Prometheus metrics, Grafana dashboards, error monitoring, AI telemetry, drift and
regression jobs with a documented model-promotion gate.

### P14–P15 — Security hardening and CI/CD gates
`docs/security.md` threat model; tests for IDOR, injection, XSS, upload attacks, prompt
injection, cross-tenant retrieval; CI with lint, type checks, tests, `pip-audit`/`npm audit`,
Bandit, image build, benchmark smoke, deploy.

### P16–P18 — Business value, cost, polish
Business-impact metrics computed from real data only (simulations labelled as such);
parameterized cost model; UX polish last.

## 6. What "done" means for this program

A real user can use it → the business workflow works → AI provides measurable value → the
system is benchmarked → load-tested → observable → documented → reproducibly deployable.
Stages P9 (real pilot) and P16 (business value) depend on real users and cannot be completed
by engineering work alone; they will be reported honestly as in-progress until data exists.

---

## 7. Progress log

Stage reports, newest last. Numbers here are measured, with the command that produced them.

### P0 — Repository audit ✅ (2026-09-30)
See [`current_architecture.md`](current_architecture.md). Reproduced 13 authorization defects;
baseline 163 backend tests / 70% coverage; live backend unreachable.

### P1 — Core product ✅ (2026-09-30)
* **Completed:** marketplace and bargaining removed (tag `legacy-marketplace`); organizations,
  invitations, portal sign-up, six roles; ticket state machine with history, SLA clocks with
  pause/breach/escalation/auto-close; comments (public/internal), mentions, attachments;
  notifications (DB + WebSocket); email outbox; audit log; operations dashboard; new
  Vite/TypeScript frontend; demo seed (3 labelled orgs, 27 users, 54 tickets).
* **Measured:** backend 253 tests pass on SQLite and PostgreSQL 16, 94% line coverage
  (`pytest --cov`); suite runtime 17–25 s locally (was 264 s); frontend 24 unit tests;
  Playwright acceptance + mobile flows pass; production JS 250 kB gzip initial load
  (`npx vite build`); `pip-audit`: 32 advisories found → 0 after upgrades and replacing
  python-jose with PyJWT.
* **Acceptance criteria:** register/login ✔ · create org ✔ · invite ✔ · customer creates ticket ✔ ·
  agent processes ✔ · admin analytics ✔ · customer sees resolution ✔ · audit trail ✔ —
  automated in `backend/tests/test_acceptance_p1.py` and `frontend/e2e/p1-acceptance.spec.ts`.
* **Known issues:** SLA sweep and email delivery run in-process (worker in P2); WebSocket and
  rate limiting are single-instance; no email provider configured; dark mode not implemented.
* **Next:** P2 — deployment.

### P2 — Deployment ✅ engineering complete · ⏳ go-live blocked on owner (2026-09-30)
* **Completed:** worker process (`python -m app.worker`) for SLA sweep and email delivery;
  email outbox retry with exponential backoff and dead-lettering (migration `0002`); Redis
  pub/sub fan-out so live notifications work across API processes and from the worker; Redis
  rate-limit storage; optional Sentry (scrubbed) and S3-compatible storage; production compose
  (Caddy auto-HTTPS, one-shot migrate service + advisory lock, health checks everywhere);
  `bootstrap-vm.sh`, `deploy.sh` (auto-rollback), `rollback.sh`, `backup.sh`, `restore.sh`,
  `smoke.sh`, `verify_realtime.py`; CD workflow (GHCR images by SHA, SSH deploy behind an
  approval environment); psycopg 3.
* **Measured / verified (local rehearsal, `ENVIRONMENT=staging`, DOMAIN=localhost):** stack
  healthy; smoke test passes; 3/3 cross-process WebSocket pushes delivered; worker SLA-breach push
  delivered after 105 s; backup→restore round trip; deploy→rollback; broken image → automatic
  rollback with the site staying up. Backend: 266 tests pass on SQLite and PostgreSQL 16.
* **Blocked:** real public URL — needs VM, DNS record, GitHub secrets (`DEPLOY_HOST`,
  `DEPLOY_SSH_KEY`) — steps in [`deployment.md`](deployment.md). Let's Encrypt, GHCR pull and SSH
  deploy are therefore unverified.
* **Known issues:** backend image is 357 MB (boto3/botocore); backups stay on the VM until an
  off-site target is configured.
* **Next:** P3 — realistic data.

### P3 — Realistic data ✅ (2026-09-30)
* **Completed:** SHA-256-pinned downloads and deterministic preparation (`python -m nexadesk_ml.datasets
  all`) of three public datasets and one documented synthetic generator — full provenance,
  licenses and limitations in [`datasets.md`](datasets.md):
  UCI ServiceNow incident log (real, CC BY 4.0) · public support-ticket texts (LLM-generated,
  CC BY-NC 4.0) · CQADupStack *unix* (real duplicates, CC BY-SA 4.0) · 3 synthetic organizations.
* **Measured:** incidents 24,918 (time split 17,442 / 3,738 / 3,738; SLA-breach rate 42.3% train
  vs 23.4% test — a real base-rate shift; resolution p50 22.1 h, p90 381.5 h; the human
  dispatcher's first assignment was the resolving group for 65.1%); ticket texts 16,338 after
  exact-duplicate removal (11,433 / 2,450 / 2,455); CQADupStack 47,382 posts, 1,072 queries with
  1,693 duplicate links; synthetic 12,000 tickets (5,500 / 4,000 / 2,500), 480 planted duplicates.
* **Known issues:** the ticket-text dataset is LLM-generated and non-commercial; no public dataset
  has real ticket text *and* real routing/SLA outcomes together, so text tasks and operational tasks
  are evaluated on different data.
* **Next:** P4.

### P4 — Baseline ML ✅ (2026-09-30)
All numbers: test split scored once, models chosen on validation, reproducible with the scripts
in [`experiments/`](../experiments/README.md); JSON provenance (git SHA, dataset hashes, params,
environment) next to each `summary.md` under `reports/`.
* **Classification** (public LLM-generated tickets, macro-F1): TF-IDF+LinearSVC queue 0.676 /
  type 0.892 / priority 0.689 vs majority 0.045 / 0.144 / 0.189; sentence-embedding+LogReg much
  worse (queue 0.307). Per-organization learners (`production_classifier.md`), on the 2,169
  *novel* test tickets: kNN over TF-IDF 0.719 / 0.904 / 0.743, kNN over MiniLM (shipped)
  0.615 / 0.867 / 0.686. With ≤ 1,000 tickets of history every method is weak (queue ≤ 0.31).
* **Routing** (real incidents, 49 groups): logistic regression top-1 0.655, top-3 0.857, p50
  1.04 ms vs the human dispatcher's first assignment 0.673 and a category→group table 0.515.
  Selective routing at confidence ≥ 0.9 covers 16% of incidents at 0.937 accuracy (humans 0.928 on
  the same subset) — automation at parity on a slice, not better routing.
* **Duplicates** (CQADupStack, real): Recall@10 MiniLM 0.532 · BGE 0.478 · TF-IDF 0.324;
  cross-encoder reranking lifts pair precision 0.277 → 0.421 but not recall. Production flag
  threshold 0.75 (rule fixed before test: lowest threshold with validation precision ≥ 0.5): test
  precision 0.47, recall 0.18 (`reports/duplicates/threshold.md`).
* **SLA breach** (real): LR ROC-AUC 0.769, LightGBM 0.762 / PR-AUC 0.523; uncalibrated Brier
  0.190 is worse than a constant forecast (0.179) because of the base-rate shift; isotonic
  recalibration on the latest period → 0.151. **Resolution time:** LightGBM (median objective) MAE
  95.1 h vs global-median 98.9 h, R² 0.061 — 73% of the error comes from tickets open > 3 days.
* **Error analysis:** [`reports/error_analysis.md`](../reports/error_analysis.md).
* **Decision for P5:** ship per-organization kNN over MiniLM embeddings (one vector index serves
  triage, duplicates and "similar tickets" evidence). Known gap: TF-IDF kNN scored ~0.04–0.10
  macro-F1 higher on this benchmark — the top improvement candidate, to be decided through the
  P13 promotion gate, not assumed.
* **Known issues:** MLflow rejects some metric names with "·" (JSON records unaffected); CPU
  contention from parallel runs inflates some latency figures — latencies are indicative.
* **Next:** P5.

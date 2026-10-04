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

### P2 — Deployment ✅ public demo live on free tiers (2026-10-01) · VM path rehearsed, not live
* **Live (2026-10-01):** owner chose zero-cost hosting — API on Render Free
  (<https://nexadesk-api-qp6v.onrender.com>), PostgreSQL on Neon Free, SPA on Netlify
  (<https://nexadesk-api.netlify.app>, `netlify.toml`). Migrations and demo seed ran on first
  start; `/ready` reports database and migration head OK.
* **Measured for it:** local 512 MB / 0.1-CPU simulation found an OOM and a CPU-quota problem with
  default AI settings → `EMBEDDING_THREADS=1`, `EMBEDDING_BATCH_SIZE=4`, `MALLOC_ARENA_MAX=2`,
  one-process start-up (restart 6 min → 146–161 s); live checks: warm p50 0.31–0.36 s for
  reads, login 2.0 s; sign-up/login/refresh/WebSocket verified in a browser
  (`reports/render_free_tier.md`).
* **2026-10-04:** the Netlify site was still building the legacy app from `main`, so sign-in and
  sign-up failed there; with the owner's approval `main` was fast-forwarded to
  `nexadesk-transformation` (legacy app remains at tag `legacy-marketplace`). Verified on the live
  site in a browser: 13/13 steps (sign-up, ticket, sign-out/in, main pages, portal sign-up,
  WebSocket).
* **Not live:** the VM deployment below (Caddy, worker, Redis, backups, CD) — not needed for the
  free demo; still the production target.

#### P2 (VM path) — engineering complete (2026-09-30)
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
  vs 23.4% test — a real base-rate shift; resolution p50 22.1 h, p90 381.5 h; on the test period
  the dispatcher's first assignment was the resolving group for 67.3% and 37.1% of incidents were
  reassigned); ticket texts 16,338 after
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

### P5 — AI-assisted operations ✅ (2026-09-30 → 10-01)
* **Completed:** per-organization triage agent over MiniLM embeddings (FastEmbed ONNX, model baked
  into the image) and pgvector: category, priority, team, assignee, duplicate candidates, SLA-risk
  and resolution-time statistics, next steps — each a persisted recommendation with confidence,
  evidence (similar tickets), model version and latency; durable PostgreSQL job queue; human
  accept/edit/reject; opt-in auto-apply policy; history importer; optional LLM summaries and reply
  drafts (off unless `LLM_PROVIDER` + `LLM_API_KEY`; call ledger, per-org token budget).
* **Measured (SYNTHETIC replay, production code path on PostgreSQL 16 + pgvector,
  `reports/pipeline/`):** 3 organizations, 9,216 history / 2,400 replayed tickets. Category
  accuracy 0.46–0.53 vs majority 0.28–0.31; at confidence ≥ 0.7 coverage 6–10% at accuracy
  0.90–0.97. Agent run p50 107–159 ms (first replay; second replay on a busier machine 154–314 ms).
  **HNSW with pgvector defaults returned as few as 14 of 60 rows (recall 0.41) for a tenant in the
  shared table; with NexaDesk's per-query settings (`ef_search`, iterative scan) 60 rows, recall
  0.99–1.00.** Promotion-gate baseline recorded (`reports/pipeline/gate_baseline.json`).
* **Changed because of the measurements:** the neighbour-weighted resolution estimate was worse
  than a plain median → replaced by per-priority statistics (MAE now equal to the baseline, 130 vs
  131 h; median error still worse — known limitation); escalation proposals fired on 39% of new
  tickets (at creation the risk is just the base rate) → now require the ticket to be ≥ 25% into
  its window and ≥ 15 points above the base rate (0 proposals at creation in the second replay).
* **Known issues:** TF-IDF kNN beat the shipped MiniLM kNN on the public text benchmark (P4);
  duplicate flags are low-recall on real data; generated text unevaluated (no provider).

### P6 — Knowledge base and retrieval ✅
* **Completed:** PDF/DOCX/Markdown/HTML/text ingestion in the worker, heading-aware chunks,
  pgvector + PostgreSQL full-text, visibility (published vs internal) and tenant filters in SQL,
  grounded answers with citation/support check and a no-answer path (only with an LLM provider),
  article suggestions while writing a ticket, related articles for agents, KB telemetry.
* **Measured (CQADupStack, `reports/rag/`):** dense MiniLM nDCG@10 0.407 · equal-weight RRF 0.372 ·
  BM25 0.274 · dense + cross-encoder 0.408 at ~1.2 s/query. Lexical weight chosen on validation:
  **0** → shipped **dense-first with full-text fallback** (exact error codes), reranker off.
* **Known issues:** CQADupStack is a duplicate-retrieval proxy; no labelled KB answer set yet.

### P7 — Agentic workflow ✅
* **Completed:** deterministic playbook planner; typed tools (Pydantic) with per-organization
  domain validation, risk levels, policy gate, SAVEPOINT execution through the same path as a
  human accept, post-change verification with rollback, run/step log (`agent_runs`). No LLM
  planner (it could not be evaluated without a provider).
* **Measured — ablation (`reports/pipeline/agent_ablation.md`, SYNTHETIC):** no tools (static
  majority category) error 0.69–0.73; tools without a gate automate 100% with error 0.47–0.54;
  tools + gate 0.9 automate 5–6% (133 of 2,400 tickets) with no wrong change in that sample, the
  rest to people; gate 0.7 automates 6–10% with error 0.03–0.10.

### P8 — Human-in-the-loop ✅
* **Completed:** risk levels (low/medium/high) per action, approval queue across tickets with
  bulk decisions under each approver's own permissions, "how the AI decided" log, AI performance
  (acceptance, override, automation false-positive rate, latency) and drift status on the dashboard.
* **Not measured:** acceptance/override rates need real users (P9).

### P9 — Real-user pilot ⏳ tooling ready, pilot not started
* **Completed:** pilot plan with targets fixed before any data ([`pilot_plan.md`](pilot_plan.md)),
  CSAT on resolved tickets, in-app product feedback, "How NexaDesk uses AI" notice, computed pilot
  report (`/analytics/pilot`, `app.scripts.pilot_report`) that refuses rates below 5 observations
  and labels demo/synthetic organizations, imported-history baseline.
* **Blocked:** needs the live deployment and a consenting team (owner).

### P10 — Load testing ✅ local · P11 — Scalability ✅
* **Measured (`reports/load/README.md`, local laptop, 100k SYNTHETIC tickets, production compose):**
  within target at 100 concurrent users (~30 req/s, p95 150 ms, 0 errors); error-free but slower at
  250 users (~66 req/s, p95 970 ms → 540 ms with backpressure); saturation beyond ~65–70 successful
  req/s. Application memory under load ≈ 1.2 GiB.
* **Bottleneck → change → measured delta:** (1) connection-pool **deadlock** from a sync `yield`
  session dependency → async teardown on a dedicated limiter: errors at 100–250 users 3–14% → 0%;
  (2) dashboard aggregates (p50 530 ms at 250 users) → 30 s per-org Redis cache; (3) ticket search
  full scan 75 ms → trigram GIN indexes 20 ms (`EXPLAIN ANALYZE`, 100k tickets); (4) overload
  hangs (p95 43 s at 500 users) → `API_LIMIT_CONCURRENCY` backpressure: p95 0.82 s, successful
  req/s 3.2 → 43.8; (5) first KB search per process paid ~3 s model load → warm-up at start.
  More API processes (4 vs 2) did **not** add throughput on this machine.
* **Database volume (`reports/scale/README.md`, 10k → 100k → 1M tickets in one org):** point
  lookups flat; list views ≤ ~0.2 s p50 at 1M except "open by priority" (0.37 s); **ticket-number
  search 5.1 s → 27 ms** after making `#123` an exact index lookup; common-word search ~0.5 s at 1M
  (trigram indexes help at 100k, not for a term in 7% of tickets); uncached dashboard 2.2 s at 1M
  (cached 30 s in the app). 1M tickets ≈ 596 MB (+118 MB trigram indexes).
* **Known issues:** load generator shared the machine; no real-VM run; WebSockets not load-tested.

### P12 — Observability ✅ · P13 — AI evaluation/monitoring ✅ · P14 — Security ✅ · P15 — CI/CD gates ✅
See the detailed entries below. Verified under load: the provisioned Grafana dashboard shows the
load test's real traffic (`docs/screenshots/grafana-load-test.png`); the run exposed that
unhandled 500s were not counted → fixed and tested.

### P16 — Business value ✅ framework · not measured
[`business_value.md`](business_value.md): hypotheses mapped to evidence (routing automation at
parity on a 16% slice; no support yet for "fewer misroutes"); pilot measurements; value
calculator (`app.scripts.value_report`) that multiplies measured counts by the owner's stated
assumptions and says it is not a measured saving. **No saving is claimed.**

### P17 — Cost ✅ measured resources · no operating cost yet
[`cost.md`](cost.md): images 839 MB / 83.6 MB, ≈ 1.2 GiB memory under load, ≈ 3.6 kB per ticket
embedding, dated third-party VM prices (4 GB class from €4.97–€20.88/month excl. VAT), LLM cost =
ledger × configured prices, built-in budgets. Suggested start: 4 GB / 2 vCPU VM.

### P18 — Polish ✅
README, architecture diagrams, security/AI-evaluation/cost/business docs, setup checklist, E2E
screenshots (tickets, knowledge base, AI panel, approvals, Grafana).

### P12 — Observability ✅ (2026-09-30)
* **Completed:** Prometheus metrics from the API (`/metrics`, multi-process aggregation across
  uvicorn workers) and the worker (`:9101`), both bearer-protected by `METRICS_TOKEN` (boot refuses
  to start without it when deployed) and not routed by Caddy: request rate/latency by route
  template, job outcomes/duration, agent run time and step outcomes, human decisions, LLM calls and
  tokens, KB queries, plus backlog gauges read from PostgreSQL at scrape time. Opt-in
  `observability` compose profile: Prometheus (30-day retention, 8 alert rules) and Grafana
  (provisioned 19-panel dashboard generated by `deploy/observability/build_dashboard.py`, bound to
  127.0.0.1). Request ids in logs and responses (P1).
* **Verified:** metrics reflect real requests/jobs/backlog and never carry tenant data
  (`test_metrics_endpoint.py`, `test_security.py::test_a5_…`); dashboard verified with the P10 load test's traffic; unhandled 500s were not counted → fixed.
* **Known issues:** no Alertmanager receiver (needs the owner's channel); no Postgres/Redis exporters.

### P13 — AI evaluation and monitoring ✅ (2026-09-30)
* **Completed:** daily per-organization drift/agreement check (`app/ai/monitoring.py`: category PSI,
  embedding-centroid drift, novelty rate, acceptance trend; "insufficient data" below 20 tickets),
  exposed at `/analytics/ai-monitoring`, on the dashboard and as a Prometheus gauge/alert; model
  promotion gate `experiments/regression_gate.py` (fixed 300-ticket replay; fails on quality drops
  beyond tolerance) with a CI workflow (`ai-eval.yml`: AI code changes, weekly, on demand); process
  in [`ai_evaluation.md`](ai_evaluation.md).
* **Tests:** `test_ai_monitoring.py` (PSI, alerting, insufficient data, tenant scoping).

### P14 — Security hardening ✅ (2026-09-30)
* **Completed:** threat model with 16 threats mapped to controls and tests
  ([`security.md`](security.md)); `test_threats.py` (injection, stored XSS, upload tricks,
  cross-tenant access through every AI/KB endpoint, mass assignment, forged/expired/`alg=none`
  tokens, role claims not trusted); frontend guard against raw-HTML sinks; `/metrics` token.
* **Measured:** Bandit 1.9.4 — 0 medium/high findings after review (3 annotated false positives,
  9 low); gitleaks 8.28 over full history — 3 findings, all reviewed: 2 test fixtures and 1 **real
  legacy JWT default key in public history** (pre-rewrite code; unused by the current code, which
  refuses weak keys when deployed) → must be treated as public; history rewrite is an owner decision.
* **Known issues:** no WAF, no malware scanning of attachments, no external penetration test.

### P15 — CI/CD gates ✅ (2026-09-30)
* **Completed:** CI now gates on ruff, format, mypy, **Bandit**, backend tests on SQLite and
  PostgreSQL with a **coverage floor of 88%** (current 91%), migration drift, **gitleaks** history
  scan, `pip-audit`, `npm audit`, frontend lint/types/tests/build, Playwright (3 flows), Docker
  build + compose smoke; separate **AI evaluation gate** workflow; deploy runs only after CI passes
  on `main`, inside an approval environment (P2).
* **Not verified:** the workflows have not run on GitHub from this branch (no push in this
  session); each step was run locally.

### Verification (2026-10-01, this workspace, Windows 11 + Docker Desktop)
* Backend: ruff, format, mypy, Bandit (≥ medium) clean; **381 tests pass on SQLite (91.35% line
  coverage) and on PostgreSQL 16 + pgvector** (incl. migration drift test through 0009).
* Frontend: ESLint, TypeScript, **29 Vitest tests**, production build (initial JS 258 kB gzip),
  `npm audit --omit=dev` 0 vulnerabilities.
* Playwright: all 3 flows pass (AI assist, mobile, P1 acceptance + CSAT); the P1 flow failed once
  in a full-suite run ("Test ended" during a fill) and passed on re-run — CI retries once.
* gitleaks over full history: only the reviewed entries in `.gitleaksignore`.
* **GitHub Actions on the pushed branch: all 8 CI jobs pass** (run 36789072189, commit 95ae61b:
  lint/types/Bandit, gitleaks, backend SQLite + PostgreSQL, dependency audit, frontend, Playwright,
  Docker compose smoke). The first run had failed: `.gitignore`'s Python-template `lib/` rule had
  kept `frontend/src/lib/` out of git since P1 — fixed in 95ae61b.
* Not verified: the deploy workflow (needs the owner's VM and secrets), the AI-evaluation workflow
  (runs on AI changes to `main`/PRs and weekly), the public deployment, real users.

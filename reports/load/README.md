# P10 / P11 — Load tests: what broke, what changed, what it measured

**Setup (all runs):** the production compose stack (`deploy/docker-compose.prod.yml`, Caddy TLS →
API → PostgreSQL 16 + Redis, worker, Prometheus/Grafana) on one Windows 11 laptop under Docker
Desktop (VM: 12 CPUs, 7.6 GiB), with the Locust load generator **on the same machine**. One
SYNTHETIC organization with 100,000 tickets (`app/scripts/seed_volume.py`). Profile
(`loadtest/locustfile.py`): 60% requesters, 30% agents, 10% managers with 2–10 s think time.
2 minutes steady state per step after ramp-up. Target set before running: p95 < 500 ms for every
endpoint group, < 1% errors. **This is a local capacity test, not a statement about any server
you would deploy on.** Each folder holds `run.json`, `summary.md` and Locust's CSVs.

| Run | Change | 100 users: ok req/s · p95 · errors | 250 users: ok req/s · p95 · errors | 500 users: ok req/s · p95 · errors |
|---|---|---|---|---|
| `20260930T210737Z` | baseline (harness bugs: KB search 400, see below) | 26.3 · 140 ms · 8.9% | 64.0 · 360 ms · 9.4% | 2.4 · 60 s · 95.7% |
| `20260930T212319Z` | + dashboard cache, trigram search, model warm-up; harness fixed | 23.2 · 3.3 s · 3.1% | 21.4 · 40 s · 13.5% | 1.4 · 60 s · 96.9% |
| `20260930T213852Z` | + **async session teardown** (deadlock fix) | **29.6 · 150 ms · 0.0%** | 65.6 · 970 ms · 0.0% | 3.2 · 43 s · 91.3% |
| `20260930T215007Z` | 4 API processes instead of 2 (pool 10+10 each) | — | 64.5 · 2.2 s · 0.0% | 48.9 · 13 s · 41.2% |
| `20260930T215657Z` | 2 processes + **backpressure** (`--limit-concurrency 30`) | — | 67.7 · 540 ms · 1.2% | 43.8 · 820 ms · 66.9% (fast 503s) |

"ok req/s" = requests/s × (1 − error rate).

## Findings, in the order they were found

1. **Harness bugs (run 1).** KB search sent unencoded spaces (every call 400) and every virtual
   user shares one IP, so the per-IP limits on ticket creation (30/min) and KB search (60/min)
   trip by design. Fixed in the locustfile: queries URL-encoded; 429s are reported under their own
   name, not as failures.
2. **Slow endpoints (run 1).** At 250 users the dashboard overview (p50 530 ms) and ticket search
   (p95 560 ms) were slowest. Changes: dashboard aggregates cached per organization for 30 s in
   Redis (`routers/analytics.py`); trigram GIN indexes for `lower(title|description) LIKE`
   (migration 0009) — the search query went from a 75 ms parallel sequential scan to 20 ms of
   bitmap index scans on 100k tickets (`EXPLAIN ANALYZE`, same data).
3. **Deadlock (run 2).** With KB search now working the stack failed from 100 users while CPU was
   idle: PostgreSQL showed 30 connections "idle in transaction" and `/health` hung after the test.
   Cause: `get_db` was a synchronous `yield` dependency, so closing a session needed a threadpool
   thread; all threads were busy waiting for pool connections held by finished requests waiting
   for a thread. Change: async `get_db` closing sessions on a dedicated limiter
   (`app/db/database.py`), shorter pool timeout, guard test. Result (run 3): zero errors up to 250
   users and the stack recovers on its own.
4. **More processes did not add capacity (run 4).** Doubling API processes left successful
   throughput at ~65 req/s at 250 users and made p95 worse; neither PostgreSQL nor the API was
   CPU-bound in samples. Requests queue for threads while holding a connection taken in their
   first dependency, and the load generator competes for the same CPUs.
5. **Backpressure (run 5).** Capping in-flight requests per process (`API_LIMIT_CONCURRENCY`) turns
   overload into immediate 503s instead of 30–60 s hangs: at 500 users p95 fell from 43 s to
   0.82 s and successful throughput rose from 3.2 to 43.8 req/s; at 250 users p95 fell from 970 ms
   to 540 ms with 1.2% rejected.

## What the measurements support

* On this machine the stack serves the profile within target at **100 concurrent users (~30
  req/s, p95 150 ms, 0 errors)**; it stays error-free but slower at 250 users (~66 req/s); beyond
  ~65–70 successful req/s it saturates. With backpressure it degrades by rejecting quickly.
* Memory at the 250–500-user steps: API (2 processes, embedding model loaded) 550–600 MiB, worker
  230 MiB, PostgreSQL 300–370 MiB, Caddy 80–100 MiB, Redis 7 MiB, web 10 MiB, Prometheus 35 MiB,
  Grafana 135 MiB — about 1.2 GiB for the application and 1.4 GiB with observability.
* Not measured: a separate load generator, a real VM, WebSocket connection counts, attachment
  uploads.

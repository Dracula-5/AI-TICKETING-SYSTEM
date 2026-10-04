# Does the AI fit on Render's free tier? (local simulation, 2026-10-01)

**Question:** can the API run with AI enabled (MiniLM embeddings, triage, knowledge-base search) on
a Render free web service — 512 MB RAM, 0.1 CPU?

**Evidence type: local simulation, not a measurement on Render.** The backend image of this
commit ran in Docker Desktop (Windows 11 laptop) with `--memory 512m --memory-swap 512m
--cpus 0.1` (hard limit, no swap) and `PORT=10000`. PostgreSQL 16 + pgvector ran unrestricted in
a separate local container (Neon adds network latency). Docker's `--cpus` is a hard CPU quota;
Render's CPU type and the way it enforces 0.1 CPU may differ. Data: the three DEMO organizations
(54 tickets) plus SYNTHETIC tickets and a synthetic 0.6 MB / 800-chunk handbook. Memory is
the container's cgroup `memory.current` / `memory.peak`, sampled every few seconds. Scripts:
[`loadtest/render_free_tier/`](../loadtest/render_free_tier/).

## Answer

**Yes, after four changes** that are now in the image and in `render.yaml`:

| Setting | Why (measured) |
|---|---|
| `EMBEDDING_THREADS=1` | The container sees all 12 host cores; ONNX Runtime started a thread per core. The process was throttled in 6,005 of 6,008 CPU periods; re-indexing 54 demo tickets had not finished after ~8 min and logins took ~47 s. |
| `EMBEDDING_BATCH_SIZE=4` | With the default batch of 32, ingesting the 800-chunk document was **OOM-killed** (exit 137). At 1 CPU: batch 32 → 721 MB peak RSS, 153 ms CPU per chunk; batch 4 → 301 MB, 116 ms. |
| `MALLOC_ARENA_MAX=2` | Same 60-search + 10-ticket workload after a restart: 229 → 398 MB (peak 403) with the default allocator, 231 → 353 MB (peak 369) with 2 arenas. |
| Faster start-up | Migrations and the demo seed run in one Python process; the bcrypt "dummy hash" is computed on first use, not at import; the seed hashes the demo password only when it creates an organization. |

## Results with those settings (512 MB / 0.1 CPU)

| Measurement | Result |
|---|---|
| Memory after the model loads (idle) | ≈ 230 MB |
| Repeated search workload (3 rounds of 60 searches + 10 tickets) | levelled off at 353 → 360 → 357 MB; peaks 369 / 401 / 412 MB; **no OOM** |
| 800-chunk (0.6 MB) document ingestion | completed, peak 344 MB, **37 min** (2,235 s) — CPU-bound |
| Triage of 30 new tickets | all 30 had recommendations 151 s after the first was created (job ≈ 4.3 s each) |
| KB search | p50 0.71–0.80 s, p95 2.3–2.6 s (60 queries per round) |
| Related articles for a ticket / dashboard overview (uncached) | 2.3 s / 4.3 s |
| Login (bcrypt cost 12, ≈ 1.3 CPU-s here) | 13–15 s idle; 20–50 s while background jobs run |
| First start, empty database (migrate + seed + model) | ≈ 6 min before the start-up changes → **≈ 3 min** after |
| Restart with an existing database (what a wake-up from sleep does) | ≈ 6 min before → **146–161 s** after |

Before the changes, the same restart spent 81 s in the migration step (importing Alembic and the
models), 112 s checking the demo seed, and about 2.5 min importing the API.

## What this means for the demo

* The AI features fit in memory with ~100 MB headroom in these runs. A very large document, or
  ingestion and heavy searching at the same time, have not been measured beyond what is above.
* CPU, not memory, is the limit at 0.1 CPU. Expect a 2–3 minute wake-up after the service has
  slept, logins of 10–15 s or more, and a few seconds per AI request. Keep knowledge-base uploads
  small: a few pages take seconds to a minute, but a 0.6 MB handbook took 37 minutes.
* Re-check on Render itself: watch the service's memory graph and restart events after the first
  deploy, and note real wake-up and login times before quoting any of them.

## Live deployment checks (Render free + Neon, 2026-10-01)

**Evidence type: live public demo, warm instance, one client on another continent calling the
Oregon region** (`/health` alone takes ~0.3 s, so most of each number is network round trip). Accounts used were
throw-away requesters created through the Helix Health (Demo) portal.

| Request | n | p50 | max |
|---|---|---|---|
| `GET /health` | 10 | 330 ms | 810 ms |
| `GET /ready` (database + migration head) | 10 | 318 ms | 394 ms |
| `POST /auth/login` (bcrypt cost 12) | 5 | 2,015 ms | 2,186 ms |
| `GET /auth/me` | 10 | 320 ms | 499 ms |
| `GET /tickets` | 10 | 313 ms | 392 ms |
| `GET /kb/search` (empty knowledge base → full-text fallback) | 10 | 364 ms | 425 ms |
| `POST /tickets` | 1 | 560 ms | — |

* AI capabilities reported by the live API: triage on, `sentence-transformers/all-MiniLM-L6-v2`,
  text generation off.
* Login took 2.0 s on Render versus 13–15 s in the local 0.1-CPU simulation: Render's instance
  gives more CPU to a short burst than Docker's hard quota did, so the simulation's CPU-bound
  timings are pessimistic. The memory results are the part to rely on.
* Browser check (Playwright, Chromium) with the production build of the SPA served through a
  local stand-in for the Netlify rewrite and the live API: portal sign-up → "New ticket";
  reload restored the session from the refresh cookie; sign-out → sign-in; the notification
  WebSocket connected directly to the API and received `ready`; no CSP errors.
* **Live site, 2026-10-04** (<https://nexadesk-api.netlify.app>, after `main` was fast-forwarded
  so Netlify builds the new SPA): Playwright/Chromium against the real site — create-organization
  sign-up → dashboard; new ticket (rules triage + AI recommendations panel shown); reload keeps
  the session through Netlify's `/api` rewrite; sign-out; wrong password rejected with a
  message; sign-in; tickets, knowledge base, AI approvals, members and dashboard pages load;
  requester-portal sign-up; 7 notification WebSockets authenticated directly against the API.
  13 of 13 steps passed. The only console errors were Netlify's own injected script being
  blocked by the CSP (not part of the app) and the expected 401s of the session probe.
* **Wake-up after sleep, one observation (2026-10-04):** first `/health` after days idle answered
  in 42.7 s — much faster than the 146–161 s of the local hard-quota simulation.
* Not measured yet on the live demo: AI triage latency as seen by an agent, memory over days of
  use (Render's metrics page shows it).

## Web service (nginx)

Verified with the web image in the same setup: SPA and deep links served; `/api` proxied with a
trailing slash in `API_UPSTREAM` stripped; login through the proxy set a `Secure; HttpOnly;
SameSite=lax` refresh cookie on `/api/v1/auth`; the notification WebSocket answered `ready`
through the proxy; an `https://` upstream worked (TLS with SNI, DNS resolved at request time).
With a 0.1-CPU limit nginx now starts 1 worker instead of one per host core (12 workers used
≈ 34 MB here).

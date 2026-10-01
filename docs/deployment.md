# Deployment

Target (owner decision D2): **one Linux VM running Docker Compose, with Caddy for automatic
HTTPS.** The compose deployment and rollback were rehearsed locally; real DNS, public TLS and
GitHub-to-VM deployment still require owner-managed infrastructure and credentials.
For the actionable owner checklist, including private-repository setup and pilot onboarding, see
[`external_setup_checklist.md`](external_setup_checklist.md).

```mermaid
flowchart LR
    Dev[git push main] --> CI[GitHub Actions CI<br/>lint · types · tests · e2e · audit]
    CI -->|success| IMG[Build images<br/>tag = commit SHA<br/>push to GHCR]
    IMG --> GATE{production<br/>environment<br/>approval}
    GATE --> SSH[SSH: deploy.sh SHA]
    subgraph VM[VM — Docker Compose]
        C[Caddy :443<br/>Let's Encrypt] --> W[web: nginx + SPA]
        C --> A[backend: FastAPI ×2 processes]
        M[migrate one-shot] --> P[(PostgreSQL 16)]
        A --> P
        A --> R[(Redis: pub/sub,<br/>rate limits, cache)]
        K[worker: SLA sweep,<br/>email outbox] --> P
        K --> R
    end
    SSH --> M
```

## Environments

| Environment | Where | Config |
|---|---|---|
| Development | your machine: `docker compose up` or uvicorn + Vite | `backend/.env` (`ENVIRONMENT=development`) |
| Staging / public demo | a VM (can be the same one, second compose project and subdomain) | `.env` with `ENVIRONMENT=staging` |
| Production | a VM | `.env` with `ENVIRONMENT=production` |

`staging` and `production` enforce the same guard: the API and worker refuse to start with the
development secret, insecure cookies, SQLite or a low bcrypt cost.

## First deployment (one time)

1. **Create a VM**: Ubuntu 22.04 or 24.04, public IPv4, and enough CPU/RAM for the embedding
   model and database. The old 2 vCPU / 4 GB suggestion predates the AI stages and is not a
   measured capacity recommendation. Check current provider pricing and run load tests before
   selecting a long-term size.
2. **Make the repository available to the VM.** For a public repository, the HTTPS clone below
   works directly. For a private repository, first SSH to the VM as root and create the `deploy`
   account and its `.ssh` directory; generate a dedicated read-only GitHub repository deploy key
   for that account; add its public half under the GitHub repository's **Settings → Deploy keys**;
   and configure the VM's GitHub host key and SSH client to use it. Verify the GitHub host key
   fingerprint from GitHub's official documentation before trusting it. Clone the private
   repository as `deploy` into `/opt/nexadesk`. Keep this repository-read key separate from the
   CI-to-VM SSH login key in step 6.
3. **DNS**: create an `A` record for the domain pointing at the VM's public IPv4. Add an `AAAA`
   record only if IPv6 is configured and reachable. Wait until DNS resolves correctly before
   expecting Caddy to issue a public certificate.
4. **Bootstrap** (as root on the VM):
   ```bash
   # For a public repository, clone it here. A private repository should already
   # have been cloned as deploy in step 3.
   git clone https://github.com/<you>/<repo>.git /opt/nexadesk
   /opt/nexadesk/deploy/bootstrap-vm.sh nexadesk.example.com you@example.com ghcr.io/<you>
   ```
   This installs Docker, enables the firewall (22/80/443 only) and automatic security updates,
   creates a `deploy` user, generates `/opt/nexadesk/.env` with random secrets, and schedules a
   nightly database backup.
5. **Review `/opt/nexadesk/.env`** — optional: SMTP (without it, verification and reset emails
   stay in the outbox table), S3 storage, `SENTRY_DSN`, `DEMO_PASSWORD`.
6. **GitHub**:
   * make the GHCR packages readable by the VM (public packages, or `docker login ghcr.io` on the
     VM with a read-only token);
   * add repository secrets `DEPLOY_HOST` (VM IP/hostname) and `DEPLOY_SSH_KEY` (private key whose
     matching public key is in `/home/deploy/.ssh/authorized_keys`); `DEPLOY_USER` is optional and
     defaults to `deploy`;
   * create an environment named `production` and add yourself as a required reviewer.
7. **Deploy**: merge a CI-passing commit to `main`. CI builds and publishes SHA-tagged images;
   the production environment reviewer approves the deploy job; the VM backs up, migrates,
   starts the stack, and runs the smoke check. Avoid manual dispatch until that commit has a
   successful CI run.
8. **Demo data** (optional, labelled as demo everywhere):
   ```bash
   cd /opt/nexadesk && docker compose --env-file .env -f deploy/docker-compose.prod.yml \
     exec backend python -m app.scripts.seed_demo
   ```
9. **Verify** from anywhere:
   ```bash
   ./deploy/smoke.sh nexadesk.example.com
   python deploy/verify_realtime.py https://nexadesk.example.com   # ~2 min, creates a throwaway org
   ```

## Routine operations

| Task | Command (on the VM, in `/opt/nexadesk`) |
|---|---|
| Deploy a build | `./deploy/deploy.sh <sha>` — backup → pull → migrate → start → smoke test; **automatic rollback** if start or smoke fails |
| Roll back code | `./deploy/rollback.sh` (previous) or `./deploy/rollback.sh <sha>` |
| Undo a schema change | `./deploy/restore.sh backups/pre-deploy-<sha>.dump` (destructive, asks for confirmation) |
| Manual backup | `./deploy/backup.sh manual` → `backups/*.dump` + attachments `.tgz`, 14-day retention |
| Logs | `docker compose --env-file .env -f deploy/docker-compose.prod.yml logs -f backend worker` |
| Status | `… ps` — every service has a health check (the worker's fails if its loop stops ticking) |

**Migrations policy.** Migrations run once per deploy in the one-shot `migrate` service (with a
PostgreSQL advisory lock as a second guard). Schema changes follow *expand → migrate code →
contract* across releases so the previous release keeps working against the new schema; that is
what makes code-only rollback safe. A change that cannot follow this pattern needs a restore
from the pre-deploy backup to roll back.

**Backups.** Nightly at 03:15 plus before every deploy, on the VM's disk. Copy them off the VM
(e.g. `rclone copy backups remote:nexadesk-backups`) — a backup on the same disk does not
survive losing the VM.

## What has been verified (local rehearsal, 2026-09-30)

On Windows 11 + Docker Desktop, with `DOMAIN=localhost` (Caddy internal CA) and
`ENVIRONMENT=staging`:

| Check | Result |
|---|---|
| Production stack starts (migrate → backend ×2 processes, worker, web, Caddy) | ✔ all healthy |
| `smoke.sh` — `/ready` (DB + migration head), SPA, API docs, 401 on anonymous API | ✔ |
| HTTPS headers — HSTS from Caddy, strict CSP on the SPA | ✔ |
| Live notifications across 2 API processes via Redis (3 of 3 pushes delivered) | ✔ `verify_realtime.py` |
| Worker-originated push (SLA breach recorded by the worker, delivered over WebSocket) | ✔ arrived 105 s after ticket creation (1-min SLA + up-to-60-s sweep) |
| Backup → mutate → restore returns the database to the backup | ✔ |
| Deploy new tag → rollback to previous tag | ✔ |
| Deploy a deliberately broken image → automatic rollback, site stays up | ✔ |

**Not yet verified:** Let's Encrypt issuance (needs a real domain), GHCR pull, SSH deploy job,
SMTP delivery — all depend on the owner-created VM, domain and secrets.

## Render (free tier) — zero-cost public demo

An alternative to the VM when there is no budget: two Render **web services** from this
repository plus a free **Neon** PostgreSQL database. [`render.yaml`](../render.yaml) describes
both services.

```mermaid
flowchart LR
    B[Browser] --> W[nexadesk-web<br/>nginx + SPA]
    W -->|/api + WebSocket<br/>API_UPSTREAM| A[nexadesk-api<br/>FastAPI, inline jobs]
    A --> N[(Neon PostgreSQL<br/>+ pgvector)]
```

The browser only talks to `nexadesk-web`; its nginx forwards `/api` to the API service. The site
therefore has one origin, so the login cookie and CSP work without CORS changes.

**1. Database (Neon, free).** Create a project in region *AWS US West 2 (Oregon)* (next to
Render's Oregon region). Copy the **direct** connection string (host without `-pooler`), e.g.
`postgresql://user:password@ep-xxx.us-west-2.aws.neon.tech/neondb?sslmode=require`. The
migrations create the `vector` and `pg_trgm` extensions themselves. A `postgresql://` or
`postgres://` URL is accepted as is (the API switches it to the psycopg 3 driver).

**2. Services.** Either *New → Blueprint*, pick this repository and branch
`nexadesk-transformation` (Render reads `render.yaml` and asks for the `sync: false` values), or
create two *New → Web Service* entries by hand:

| Field | API | Web |
|---|---|---|
| Name | `nexadesk-api` | `nexadesk-web` |
| Language | Docker | Docker |
| Branch | `nexadesk-transformation` (or `main` after merging) | same |
| Root Directory | *(empty)* | *(empty)* |
| Dockerfile Path | `./backend/Dockerfile` | `./frontend/Dockerfile` |
| Docker Build Context Directory | `./backend` | `./frontend` |
| Health Check Path | `/health` | `/` |
| Instance type | Free | Free |

API environment variables:

| Key | Value |
|---|---|
| `ENVIRONMENT` | `staging` |
| `DATABASE_URL` | the Neon connection string |
| `SECRET_KEY` | random, ≥ 32 characters (Render's *Generate*, or `python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `METRICS_TOKEN` | random, ≥ 24 characters (same way) |
| `COOKIE_SECURE` | `true` |
| `BACKGROUND_MODE` | `inline` |
| `EMAIL_BACKEND` | `console` |
| `AI_ENABLED` | `true` |
| `EMBEDDING_THREADS` | `1` (more threads only use up the 0.1-CPU quota) |
| `EMBEDDING_BATCH_SIZE` | `4` (the default 32 exceeded 512 MB on a large document — see below) |
| `MALLOC_ARENA_MAX` | `2` (less memory growth under load) |
| `LLM_PROVIDER` | `none` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `3` / `2` |
| `API_LIMIT_CONCURRENCY` | `20` |
| `SEED_DEMO_ON_START` | `true` to create the three demo organizations on first start |
| `DEMO_PASSWORD` | the shared demo password (required for the seed) |
| `FRONTEND_BASE_URL` | `https://nexadesk-web.onrender.com` (the web service's URL) |

Web environment variables:

| Key | Value |
|---|---|
| `API_UPSTREAM` | `https://nexadesk-api.onrender.com` (the API service's URL) |
| `VITE_DEMO_PASSWORD` | same as `DEMO_PASSWORD`; read at build time, shows "Explore the demo" |

Render may add a suffix to a service URL if the name is taken; use the URLs shown on each
service's page. Create the API first, then the web service with its URL, then set
`FRONTEND_BASE_URL` on the API. Changing `VITE_DEMO_PASSWORD` needs a rebuild of the web service.

**Frontend on Netlify instead (what the live demo uses).** A static host serves the SPA without
sleeping. [`netlify.toml`](../netlify.toml) builds `frontend/`, rewrites `/api/*` to the API
(the login cookie stays first-party) and sets the security headers. Netlify does not proxy
WebSockets, so the build sets `VITE_API_ORIGIN` and the notification socket connects to the API
directly (it authenticates with a token message, not the cookie). Netlify gives up on a
proxied request after 26 s, shorter than the API's wake-up, so with `VITE_API_ORIGIN` set the SPA
pings the API's `/health` and shows a "server is starting" notice until it answers. In the
Netlify site settings:

* *Build & deploy → Branches*: production branch = the branch with `netlify.toml`
  (`nexadesk-transformation` until merged). Build settings in the file override the UI.
* *Environment variables*: `VITE_DEMO_PASSWORD` (optional, same as the API's `DEMO_PASSWORD`).
* If the API URL changes, edit it in the three places in `netlify.toml`.
* Set the API's `FRONTEND_BASE_URL` to the Netlify URL.

**3. Check.** Open the web URL and sign in (demo buttons, or a demo account listed in the API's
start-up log). `https://<web>/api/docs` shows the API; `https://<api>/ready` reports database and
migration state.

**Limits of the free tier — say so on the demo:**

* **AI fits, CPU is the limit.** Simulated locally with the same limits (512 MB, no swap,
  0.1 CPU — [`reports/render_free_tier.md`](../reports/render_free_tier.md), not measured on
  Render itself): with the settings above memory levelled off at ~360 MB (peaks ≤ 412 MB) under
  repeated search and triage; a restart took 146–161 s; login 13–15 s; KB search p50
  ~0.8 s; a 0.6 MB / 800-chunk document took 37 minutes to index. Keep uploads to a few pages
  and check Render's memory graph after the first deploy.
* Both services sleep after about 15 minutes without traffic; the next visit waits for the web
  service and then the API to start (the API needed ~2.5 min in the simulation). Free instance
  hours are shared across a workspace each month — check Render's current free-tier page.
* No persistent disk: ticket attachments are lost on every restart or redeploy (set
  `STORAGE_BACKEND=s3` with an S3-compatible bucket to keep them). Tickets, knowledge-base
  text and embeddings live in the Neon database and are not affected.
* No Redis: caching is per process and live notifications are delivered in process, which is
  correct with the single API process used here. Per-IP rate limits are in memory and
  best-effort, because the API's own public URL lets clients supply `X-Forwarded-For`.
* Emails (verification, password reset) are only written to the API log.
* If Render ever restarts the API for exceeding memory, set `AI_ENABLED=false`: tickets, rules
  and search keep working without the model.
* Metrics/Grafana are not part of this setup; `/metrics` stays protected by `METRICS_TOKEN`.

## Status label

Once live, the URL is a **public demo deployment**. It becomes "production usage" only when real
external users use it (P9), and usage metrics are reported from `data_origin = real` rows only.

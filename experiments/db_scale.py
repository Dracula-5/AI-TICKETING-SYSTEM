"""
P11 — Database scalability: endpoint latency and query plans at 10k / 100k / 1M tickets.

    EVAL_DATABASE_URL=postgresql+psycopg://user:pw@host:port/nexadesk_scale \\
        backend/.venv/Scripts/python experiments/db_scale.py --sizes 10000,100000,1000000 [--revision head]

Wipes the target database, migrates it (to --revision), then grows one
SYNTHETIC load-test organization (app/scripts/seed_volume.py) to each size in
turn and, at each size, calls the real API endpoints in-process (FastAPI
TestClient → SQLAlchemy → PostgreSQL) 30 times each, recording p50/p95. The
SQL behind the slowest endpoints is re-run under EXPLAIN (ANALYZE, BUFFERS).

`--measure-only --label optimized` re-measures an existing database, e.g. after
`alembic upgrade head` adds indexes — the before/after pair is the evidence for
each optimization. Latency is in-process (no HTTP/proxy); machine noted in the report.
"""

import argparse
import json
import os
import platform
import secrets
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUT = ROOT / "reports" / "scale"

p = argparse.ArgumentParser()
p.add_argument("--sizes", default="10000,100000,1000000")
p.add_argument("--revision", default="head")
p.add_argument("--measure-only", action="store_true")
p.add_argument("--label", default="baseline")
p.add_argument("--reps", type=int, default=30)
ARGS = p.parse_args()
URL = os.environ.get("EVAL_DATABASE_URL", "")
if not URL.startswith("postgresql"):
    sys.exit("Set EVAL_DATABASE_URL to a PostgreSQL database that may be wiped.")
os.environ.update(DATABASE_URL=URL, ENVIRONMENT="development", SECRET_KEY=secrets.token_hex(32),
                  EMBEDDING_MODEL="test-hashing", JOB_RUNNER_ENABLED="false", SLA_SWEEP_ENABLED="false",
                  REDIS_URL="redis://127.0.0.1:1/0", RATE_LIMIT_DEFAULT="1000000/minute",
                  ACCESS_TOKEN_EXPIRE_MINUTES="600", LOG_LEVEL="WARNING")
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event, text  # noqa: E402

from app.db.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.scripts import seed_volume  # noqa: E402

ENDPOINTS = [  # (name, role, path)
    ("queue (open, unassigned)", "agent", "/api/v1/tickets?status=open&assignee=unassigned&page_size=25"),
    ("my work (open, mine)", "agent", "/api/v1/tickets?status=open&assignee=me&page_size=25"),
    ("requester's tickets", "customer", "/api/v1/tickets?requester=me&page_size=25"),
    ("all tickets, newest", "manager", "/api/v1/tickets?page_size=25"),
    ("open by priority", "manager", "/api/v1/tickets?status=open&sort=-priority&page_size=25"),
    ("SLA at risk", "manager", "/api/v1/tickets?sla=at_risk&page_size=25"),
    ("SLA breached", "manager", "/api/v1/tickets?sla=breached&page_size=25"),
    ("search 'printer'", "agent", "/api/v1/tickets?q=printer&page_size=25"),
    ("search '#123'", "agent", "/api/v1/tickets?q=%23123&page_size=25"),
    ("dashboard overview", "manager", "/api/v1/analytics/overview"),
    ("ticket detail", "agent", "/api/v1/tickets/{tid}"),
    ("ticket history", "agent", "/api/v1/tickets/{tid}/history"),
]


def reset_and_migrate():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", ARGS.revision], cwd=BACKEND, check=True,
                   env={**os.environ}, capture_output=True)


def pct(xs, q):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(q / 100 * (len(xs) - 1))))], 2)


def measure(size: int) -> dict:
    tokens = seed_volume.tokens(
        next(iter(engine.connect().execute(text("SELECT slug FROM tenants WHERE name = :n"),
                                           {"n": seed_volume.ORG_NAME}))).slug)
    tok = {role: users[0]["token"] for role, users in tokens["users"].items()}
    tid = engine.connect().execute(text("SELECT max(id) FROM tickets")).scalar()
    client = TestClient(app)
    captured: list[tuple[float, str, object]] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        context._t0 = time.perf_counter()

    def after(conn, cursor, statement, parameters, context, executemany):
        captured.append(((time.perf_counter() - context._t0) * 1000, statement, parameters))

    results, plans = [], {}
    for name, role, path in ENDPOINTS:
        url = path.format(tid=tid)
        headers = {"Authorization": f"Bearer {tok[role]}"}
        assert client.get(url, headers=headers).status_code == 200, (name, url)  # warm-up
        samples = []
        for _ in range(ARGS.reps):
            t0 = time.perf_counter()
            r = client.get(url, headers=headers)
            samples.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200
        captured.clear()
        event.listen(engine, "before_cursor_execute", before)
        event.listen(engine, "after_cursor_execute", after)
        client.get(url, headers=headers)
        event.remove(engine, "before_cursor_execute", before)
        event.remove(engine, "after_cursor_execute", after)
        slowest = max(captured, key=lambda c: c[0]) if captured else None
        results.append({"endpoint": name, "path": path, "p50_ms": pct(samples, 50), "p95_ms": pct(samples, 95),
                        "mean_ms": round(statistics.mean(samples), 2), "sql_statements": len(captured),
                        "slowest_sql_ms": round(slowest[0], 2) if slowest else None})
        if slowest and slowest[1].lstrip().upper().startswith("SELECT"):
            with engine.connect() as conn:
                raw = conn.connection.cursor()
                raw.execute("EXPLAIN (ANALYZE, BUFFERS) " + slowest[1], slowest[2])
                plans[name] = [r[0] for r in raw.fetchall()]
    sizes = {}
    with engine.connect() as conn:
        for table in ("tickets", "ticket_status_history", "ticket_comments", "ticket_embeddings"):
            sizes[table] = conn.execute(text("SELECT pg_total_relation_size(:t)"), {"t": table}).scalar()
        sizes["database"] = conn.execute(text("SELECT pg_database_size(current_database())")).scalar()
    return {"tickets": size, "endpoints": results, "plans": plans, "bytes": sizes}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runs = []
    if ARGS.measure_only:
        with engine.connect() as conn:
            n = conn.execute(text("SELECT count(*) FROM tickets")).scalar()
        runs.append(measure(n))
    else:
        reset_and_migrate()
        have = 0
        for size in [int(s) for s in ARGS.sizes.split(",")]:
            t0 = time.perf_counter()
            seed_volume.seed(size - have)
            have = size
            with engine.begin() as conn:
                conn.execute(text("ANALYZE"))
            print(f"seeded {size:,} in {time.perf_counter() - t0:.0f}s", flush=True)
            runs.append(measure(size))
            print(json.dumps([(e["endpoint"], e["p50_ms"], e["p95_ms"]) for e in runs[-1]["endpoints"]]), flush=True)
    with engine.connect() as conn:
        pg = conn.execute(text("SHOW server_version")).scalar()
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    payload = {"label": ARGS.label, "timestamp": datetime.now(timezone.utc).isoformat(), "git": git,
               "alembic_revision": rev, "postgres": pg, "reps": ARGS.reps, "data_origin": "synthetic",
               "environment": {"platform": platform.platform(), "processor": platform.processor(),
                               "cpu_count": os.cpu_count()}, "runs": runs}
    (OUT / f"db_scale_{ARGS.label}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT / f'db_scale_{ARGS.label}.json'}")


if __name__ == "__main__":
    main()

"""
P5 — End-to-end evaluation of the AI triage pipeline NexaDesk ships, on the
three SYNTHETIC organizations (docs/datasets.md §3).

    EVAL_DATABASE_URL=postgresql+psycopg://user:pw@host:port/nexadesk_eval \\
        backend/.venv/Scripts/python experiments/pipeline_eval.py [--model sentence-transformers/all-MiniLM-L6-v2]

Unlike the offline experiments (P4), this drives the production code: the
history importer, the FastEmbed ONNX embedder, the pgvector HNSW index on
PostgreSQL 16, similarity-weighted voting, duplicate detection and SLA-risk
statistics, exactly as the worker runs them.

Protocol (per organization; nothing here is tuned on the replayed tickets):
1. Migrate an empty database (alembic upgrade head — includes pgvector + HNSW).
2. Time split at T = the 80th percentile of created_at. History = tickets
   resolved before T (imported through the CSV importer, embedded by the
   `ai.reindex_tenant` job — throughput measured). Replay = tickets created at
   or after T. Tickets open across T are in neither, so no label from the
   future leaks into the history.
3. Replay in time order with a simulated clock: each ticket is created through
   the ticket service with its recorded priority, then analyzed by
   the triage agent (`app.agent.runner.run`, timed: plan + validate + policy
   + record). Recommendations are compared with the recorded
   queue / priority / resolution time / duplicate link.
4. ANN recall: HNSW results vs exact search for sampled replay queries, with
   and without NexaDesk's search settings (ef_search, iterative scan).

Outputs reports/pipeline/p5_pipeline_synthetic.json and summary.md.
The data is synthetic (public ticket texts re-timed and re-labelled by a
simulation); these numbers describe the pipeline, not real users.
"""

import argparse
import hashlib
import json
import os
import platform
import random
import secrets
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
CSV_DIR = ROOT / "data" / "synthetic" / "import"
OUT = ROOT / "reports" / "pipeline"
ORGS = {
    "helix-health": "Helix Health (Synthetic)",
    "brightline-retail": "Brightline Retail (Synthetic)",
    "orbital-engineering": "Orbital Engineering (Synthetic)",
}
THRESHOLDS = (0.5, 0.7, 0.9)
DUP_SWEEP = (0.80, 0.85, 0.90, 0.95)
ANN_SAMPLE = 200
SEED = 5


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    p.add_argument("--limit-replay", type=int, default=0, help="cap replayed tickets per org (0 = all)")
    p.add_argument("--orgs", default="", help="comma-separated org slugs (default: all three)")
    p.add_argument("--out", default="", help="output directory (default: reports/pipeline)")
    return p.parse_args()


ARGS = parse_args()
if ARGS.out:
    OUT = Path(ARGS.out).resolve()
if ARGS.orgs:
    ORGS = {k: v for k, v in ORGS.items() if k in ARGS.orgs.split(",")}
URL = os.environ.get("EVAL_DATABASE_URL")
if not URL or not URL.startswith("postgresql"):
    sys.exit("Set EVAL_DATABASE_URL to an empty PostgreSQL database (it will be wiped).")
os.environ.update(
    DATABASE_URL=URL,
    ENVIRONMENT="development",
    SECRET_KEY=secrets.token_hex(32),
    AI_ENABLED="true",
    EMBEDDING_MODEL=ARGS.model,
    MODEL_CACHE_DIR=str(ROOT / "data" / "cache" / "fastembed"),
    SLA_SWEEP_ENABLED="false",
    REDIS_URL="redis://127.0.0.1:1/0",
    LOG_LEVEL="WARNING",
)
sys.path.insert(0, str(BACKEND))

import csv  # noqa: E402

import numpy as np  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.agent import runner  # noqa: E402
from app.ai import index, triage  # noqa: E402
from app.ai.embedder import get_embedder, ticket_text  # noqa: E402
from app.db.database import SessionLocal, engine  # noqa: E402
from app.db.models import AIPrediction, Job, SlaPolicy, Tenant, Ticket, User  # noqa: E402
from app.scripts.import_history import import_rows  # noqa: E402
from app.services import tickets as svc  # noqa: E402
from app.services.jobs import run_due_jobs  # noqa: E402
from app.services.organizations import create_organization  # noqa: E402


def parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def pct(values, q):
    return float(np.percentile(values, q)) if len(values) else None


def reset_database():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True,
                   env={**os.environ, "DATABASE_URL": URL}, capture_output=True)


def load(slug):
    with open(CSV_DIR / f"{slug}.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["_created"] = parse_time(r["created_at"])
        r["_resolved"] = parse_time(r["resolved_at"]) if r["resolved_at"] else None
    rows.sort(key=lambda r: r["_created"])
    cutoff = sorted(r["_created"] for r in rows)[int(0.8 * len(rows))]
    history = [r for r in rows if r["_resolved"] is not None and r["_resolved"] < cutoff]
    replay = [r for r in rows if r["_created"] >= cutoff]
    return rows, cutoff, history, replay


def macro_f1(y, p):
    labels = sorted(set(y))
    f1s = []
    for c in labels:
        tp = sum(1 for a, b in zip(y, p, strict=True) if a == c and b == c)
        fp = sum(1 for a, b in zip(y, p, strict=True) if a != c and b == c)
        fn = sum(1 for a, b in zip(y, p, strict=True) if a == c and b != c)
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(f1s) / len(f1s) if f1s else None


def evaluate_org(slug, name, embedder):
    rows, cutoff, history, replay = load(slug)
    if ARGS.limit_replay:
        replay = replay[: ARGS.limit_replay]
    db = SessionLocal()
    tenant = create_organization(db, name, is_demo=True, data_origin="synthetic",
                                 settings_overrides={"ai_duplicate_threshold": 0.5})  # sweep thresholds offline
    db.commit()

    t0 = time.perf_counter()
    report = import_rows(db, tenant, history, origin="synthetic", create_missing=True)
    db.commit()
    import_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    run_due_jobs(limit=5)  # ai.reindex_tenant
    index_s = time.perf_counter() - t0
    job = db.query(Job).filter(Job.kind == "ai.reindex_tenant", Job.tenant_id == tenant.id).one()
    assert job.status == "done", job.last_error

    by_sid = {}  # synthetic_id -> ticket id (history + replayed so far)
    for t, r in zip(db.query(Ticket).filter(Ticket.tenant_id == tenant.id).order_by(Ticket.number), history,
                    strict=True):
        by_sid[r["synthetic_id"]] = t.id
    policies = {p.priority: p.resolution_minutes for p in db.query(SlaPolicy).filter(SlaPolicy.tenant_id == tenant.id)}
    requester = db.query(User).filter(User.tenant_id == tenant.id, User.role == "customer").first()
    majority = Counter(r["category"] for r in history).most_common(1)[0][0]
    hist_hours = sorted(((r["_resolved"] - r["_created"]).total_seconds() / 3600) for r in history)

    records, latencies, embed_ms = [], [], []
    outcomes: Counter = Counter()
    real_utcnow = triage.utcnow
    try:
        for r in replay:
            triage.utcnow = lambda r=r: r["_created"]  # simulated clock
            ticket = svc.create_ticket(db, requester=requester, title=r["title"], description=r["description"],
                                       priority=r["priority"], data_origin="synthetic", created_at=r["_created"],
                                       analyze=False)
            db.flush()
            t0 = time.perf_counter()
            agent_run = runner.run(db, ticket, trigger="replay")
            ids = [st["prediction_id"] for st in agent_run.steps]
            preds = {p.kind: p for p in db.query(AIPrediction).filter(AIPrediction.id.in_(ids))}
            outcomes.update(f"{st['kind']}:{st.get('outcome')}" for st in agent_run.steps)
            latencies.append((time.perf_counter() - t0) * 1000)
            db.commit()
            by_sid[r["synthetic_id"]] = ticket.id
            dup = preds.get("duplicate")
            orig = r["duplicate_of"] or None
            records.append({
                "org": slug,
                "synthetic_id": r["synthetic_id"],
                "rules_category": ticket.category,
                "category_true": r["category"],
                "category_pred": preds["category"].value["category"] if "category" in preds else None,
                "category_conf": preds["category"].confidence if "category" in preds else None,
                "priority_true": r["priority"],
                "priority_pred": preds["priority"].value["priority"] if "priority" in preds else None,
                "priority_conf": preds["priority"].confidence if "priority" in preds else None,
                "hours_true": (r["_resolved"] - r["_created"]).total_seconds() / 3600 if r["_resolved"] else None,
                "hours_pred": preds["resolution_time"].value["hours"] if "resolution_time" in preds else None,
                "breach_true": (r["_resolved"] - r["_created"]).total_seconds() / 60 > policies[r["priority"]]
                if r["_resolved"] else None,
                "breach_prob": preds["sla_risk"].value["breach_probability"] if "sla_risk" in preds else None,
                "dup_true_id": by_sid.get(orig) if orig else None,
                "dup_has_original": bool(orig) and orig in by_sid,
                "dup_pred_id": dup.value["ticket_id"] if dup else None,
                "dup_sim": dup.confidence if dup else None,
            })
        for r in replay[:100]:
            t0 = time.perf_counter()
            embedder.embed([ticket_text(r["title"], r["description"])])
            embed_ms.append((time.perf_counter() - t0) * 1000)
        ann = ann_recall(db, tenant.id, embedder, replay)
    finally:
        triage.utcnow = real_utcnow
        db.close()

    with open(OUT / f"p5_replay_records_{slug}.jsonl", "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, default=str) + "\n")
    return {
        "org": name, "cutoff": cutoff.isoformat(), "tickets_total": len(rows), "history": len(history),
        "replayed": len(replay), "categories": len({r["category"] for r in history}),
        "import_seconds": round(import_s, 2), "index_seconds": round(index_s, 2),
        "index_tickets_per_second": round(len(history) / index_s, 1),
        "skipped_on_import": len(report.skipped),
        "latency_ms": {"n": len(latencies), "p50": pct(latencies, 50), "p95": pct(latencies, 95), "p99": pct(latencies, 99)},
        "embed_only_ms": {"n": len(embed_ms), "p50": pct(embed_ms, 50), "p95": pct(embed_ms, 95)},
        "metrics": score(records, majority, hist_hours),
        "agent_step_outcomes": dict(outcomes),
        "ann": ann,
    }


def score(records, majority, hist_hours):
    out = {}
    n = len(records)
    for task in ("category", "priority"):
        cov = [r for r in records if r[f"{task}_pred"] is not None]
        y = [r[f"{task}_true"] for r in cov]
        p = [r[f"{task}_pred"] for r in cov]
        sel = {}
        for thr in THRESHOLDS:
            keep = [r for r in cov if r[f"{task}_conf"] >= thr]
            sel[str(thr)] = {"coverage": len(keep) / n if n else None,
                             "accuracy": sum(r[f"{task}_true"] == r[f"{task}_pred"] for r in keep) / len(keep) if keep else None}
        out[task] = {"coverage": len(cov) / n if n else None,
                     "accuracy": sum(a == b for a, b in zip(y, p, strict=True)) / len(cov) if cov else None,
                     "macro_f1": macro_f1(y, p), "selective": sel}
    out["category"]["majority_baseline_accuracy"] = sum(r["category_true"] == majority for r in records) / n
    # Resolution time (tickets resolved in the data)
    rt = [r for r in records if r["hours_pred"] is not None and r["hours_true"] is not None]
    med = statistics.median(hist_hours)
    out["resolution_time"] = {
        "n": len(rt), "coverage": len(rt) / n if n else None,
        "mae_hours": float(np.mean([abs(r["hours_pred"] - r["hours_true"]) for r in rt])) if rt else None,
        "median_ae_hours": float(np.median([abs(r["hours_pred"] - r["hours_true"]) for r in rt])) if rt else None,
        "baseline_global_median_mae_hours": float(np.mean([abs(med - r["hours_true"]) for r in rt])) if rt else None,
        "baseline_global_median_median_ae_hours": float(np.median([abs(med - r["hours_true"]) for r in rt])) if rt else None,
    }
    # SLA risk at creation time
    sr = [r for r in records if r["breach_prob"] is not None and r["breach_true"] is not None]
    if sr:
        y = np.array([r["breach_true"] for r in sr], dtype=float)
        pr = np.array([r["breach_prob"] for r in sr])
        base = np.full_like(pr, y.mean())
        out["sla_risk"] = {"n": len(sr), "coverage": len(sr) / n, "breach_rate": float(y.mean()),
                           "brier": float(np.mean((pr - y) ** 2)),
                           "brier_constant_test_rate": float(np.mean((base - y) ** 2)),
                           "auc": auc(y, pr)}
    # Duplicates: positives = replayed tickets whose planted original was in the DB
    pos = [r for r in records if r["dup_has_original"]]
    sweep = {}
    for thr in DUP_SWEEP:
        flagged = [r for r in records if r["dup_sim"] is not None and r["dup_sim"] >= thr]
        tp = sum(1 for r in flagged if r["dup_pred_id"] == r["dup_true_id"] and r["dup_true_id"] is not None)
        sweep[str(thr)] = {"flagged": len(flagged), "true_positives": tp,
                           "precision": tp / len(flagged) if flagged else None,
                           "recall": tp / len(pos) if pos else None,
                           "false_flag_rate_on_non_duplicates": sum(1 for r in flagged if not r["dup_has_original"])
                           / max(1, sum(1 for r in records if not r["dup_has_original"]))}
    out["duplicates"] = {"positives": len(pos), "sweep": sweep}
    return out


def auc(y, s):
    order = np.argsort(s)
    ranks = np.empty(len(s))
    ranks[order] = np.arange(1, len(s) + 1)
    # average ranks for ties
    for v in np.unique(s):
        m = s == v
        ranks[m] = ranks[m].mean()
    npos, nneg = y.sum(), len(y) - y.sum()
    if not npos or not nneg:
        return None
    return float((ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def ann_recall(db, tenant_id, embedder, replay, k=60):
    rng = random.Random(SEED)
    sample = rng.sample(replay, min(ANN_SAMPLE, len(replay)))
    q = embedder.embed([ticket_text(r["title"], r["description"]) for r in sample])
    res = {"k": k, "queries": len(sample)}
    for label, settings_sql in (("nexadesk_settings", None),
                                ("pgvector_defaults", ["SET LOCAL hnsw.ef_search = 40", "SET LOCAL hnsw.iterative_scan = off"])):
        recalls, returned, ms = [], [], []
        for vec in q:
            vec_s = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
            exact = db.execute(text("SET LOCAL enable_indexscan = off"))
            exact = [r[0] for r in db.execute(text(
                "SELECT ticket_id FROM ticket_embeddings WHERE tenant_id = :t ORDER BY embedding <=> CAST(:q AS vector) "
                "LIMIT :k"), {"t": tenant_id, "q": vec_s, "k": k})]
            db.rollback()
            t0 = time.perf_counter()
            if settings_sql is None:
                got = [n.ticket_id for n in index.search(db, tenant_id=tenant_id, vector=vec, model=embedder.name, k=k)]
            else:
                for s in settings_sql:
                    db.execute(text(s))
                got = [r[0] for r in db.execute(text(
                    "SELECT ticket_id FROM ticket_embeddings WHERE tenant_id = :t AND model = :m "
                    "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"),
                    {"t": tenant_id, "m": embedder.name, "q": vec_s, "k": k})]
            ms.append((time.perf_counter() - t0) * 1000)
            db.rollback()
            returned.append(len(got))
            recalls.append(len(set(got) & set(exact)) / max(1, len(exact)))
        res[label] = {"mean_recall_at_k": float(np.mean(recalls)), "min_rows_returned": int(min(returned)),
                      "mean_rows_returned": float(np.mean(returned)), "p50_ms": pct(ms, 50), "p95_ms": pct(ms, 95)}
    plan = db.execute(text(
        "EXPLAIN SELECT ticket_id FROM ticket_embeddings WHERE tenant_id = :t AND model = :m "
        "ORDER BY embedding <=> CAST(:q AS vector) LIMIT 60"),
        {"t": tenant_id, "m": embedder.name, "q": "[" + ",".join("0" for _ in range(384)) + "]"}).all()
    res["plan_uses_hnsw"] = any("ix_ticket_embeddings_hnsw" in r[0] for r in plan)
    db.rollback()
    return res


def git_sha():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return None


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    reset_database()
    embedder = get_embedder()
    assert embedder is not None and embedder.name == ARGS.model, "embedder failed to load"
    results = [evaluate_org(slug, name, embedder) for slug, name in ORGS.items()]
    with engine.connect() as conn:
        pg_version = conn.execute(text("SHOW server_version")).scalar()
        vec_version = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar()
    payload = {
        "task": "pipeline", "run": "p5_pipeline_synthetic", "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.time() - started, 1), "git": git_sha(),
        "datasets_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(CSV_DIR.glob("*.csv"))},
        "params": {"model": ARGS.model, "thresholds": THRESHOLDS, "duplicate_sweep": DUP_SWEEP,
                   "min_similarity": triage.MIN_SIMILARITY, "k": triage.K, "vote_power": triage.VOTE_POWER,
                   "engine_version": triage.ENGINE_VERSION, "planner": runner.PLANNER,
                   "limit_replay": ARGS.limit_replay, "orgs": list(ORGS)},
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "processor": platform.processor(), "cpu_count": os.cpu_count(),
                        "postgres": pg_version, "pgvector": vec_version},
        "data_origin": "synthetic",
        "results": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "p5_pipeline_synthetic.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    write_summary(payload)
    print(json.dumps([{k: v for k, v in r.items() if k in ("org", "latency_ms", "ann")} for r in results], indent=1,
                     default=str))


def f(v, spec=".3f"):
    return "—" if v is None else format(v, spec)


def write_summary(p):
    L = ["# P5 — Shipped AI triage pipeline, end to end (SYNTHETIC organizations)", "",
         f"Model `{p['params']['model']}` (FastEmbed ONNX, CPU) · PostgreSQL {p['environment']['postgres']} + pgvector "
         f"{p['environment']['pgvector']} · engine `{p['params']['engine_version']}` · planner "
         f"`{p['params']['planner']}` · git `{(p['git'] or '')[:10]}`. "
         "Replays each synthetic organization's newest 20% of tickets, in time order with a simulated clock, against a "
         "history of tickets resolved before the cutoff, through the production code path (importer → reindex job → "
         "the triage agent). **Synthetic data: this measures the pipeline, not real users.** "
         "Provenance: `reports/pipeline/p5_pipeline_synthetic.json`.", "",
         "## Recommendations vs recorded outcomes", "",
         "| Organization | History / replayed | Category: coverage · accuracy · macro-F1 | Majority baseline | "
         "Category at conf ≥ 0.7: coverage · accuracy | Priority: coverage · accuracy |",
         "|---|---|---|---|---|---|"]
    for r in p["results"]:
        c, pr = r["metrics"]["category"], r["metrics"]["priority"]
        s7 = c["selective"]["0.7"]
        L.append(f"| {r['org']} | {r['history']:,} / {r['replayed']:,} | {f(c['coverage'])} · {f(c['accuracy'])} · "
                 f"{f(c['macro_f1'])} | {f(c['majority_baseline_accuracy'])} | {f(s7['coverage'])} · {f(s7['accuracy'])} | "
                 f"{f(pr['coverage'])} · {f(pr['accuracy'])} |")
    L += ["", "Team routing equals category in this data (one team per queue), so it is not reported separately.", "",
          "## Resolution time and SLA risk", "",
          "| Organization | Resolution time MAE / MedAE (h) | Global-median baseline MAE / MedAE (h) | "
          "SLA risk: Brier · constant-rate Brier · ROC AUC |", "|---|---|---|---|"]
    for r in p["results"]:
        rt, sr = r["metrics"]["resolution_time"], r["metrics"].get("sla_risk", {})
        L.append(f"| {r['org']} | {f(rt['mae_hours'], '.1f')} / {f(rt['median_ae_hours'], '.1f')} | "
                 f"{f(rt['baseline_global_median_mae_hours'], '.1f')} / {f(rt['baseline_global_median_median_ae_hours'], '.1f')} | "
                 f"{f(sr.get('brier'))} · {f(sr.get('brier_constant_test_rate'))} · {f(sr.get('auc'))} |")
    L += ["", "## Duplicate flags (planted resubmissions — easier than real duplicates)", "",
          "| Organization | Positives | " + " | ".join(f"≥ {t}: precision · recall" for t in DUP_SWEEP) + " |",
          "|---|---|" + "---|" * len(DUP_SWEEP)]
    for r in p["results"]:
        d = r["metrics"]["duplicates"]
        cells = [f"{f(d['sweep'][str(t)]['precision'])} · {f(d['sweep'][str(t)]['recall'])}" for t in DUP_SWEEP]
        L.append(f"| {r['org']} | {d['positives']} | " + " | ".join(cells) + " |")
    L += ["", "## Latency and indexing", "",
          "| Organization | Analysis p50 / p95 / p99 (ms) | Embedding only p50 (ms) | Index throughput (tickets/s) | "
          "HNSW recall@60 NexaDesk settings / pgvector defaults | Rows returned (min) NexaDesk / defaults |",
          "|---|---|---|---|---|---|"]
    for r in p["results"]:
        lat, a = r["latency_ms"], r["ann"]
        L.append(f"| {r['org']} | {f(lat['p50'], '.1f')} / {f(lat['p95'], '.1f')} / {f(lat['p99'], '.1f')} | "
                 f"{f(r['embed_only_ms']['p50'], '.1f')} | {f(r['index_tickets_per_second'], '.1f')} | "
                 f"{f(a['nexadesk_settings']['mean_recall_at_k'])} / {f(a['pgvector_defaults']['mean_recall_at_k'])} | "
                 f"{a['nexadesk_settings']['min_rows_returned']} / {a['pgvector_defaults']['min_rows_returned']} |")
    env = p["environment"]
    L += ["", f"Hardware: {env['processor']} ({env['cpu_count']} logical CPUs), {env['platform']}; single process; "
          "database in a local Docker container. Analysis latency = embed + vector search + votes + SLA statistics + "
          "knowledge-base lookup + validation + policy + writing the recommendations, measured around "
          "`app.agent.runner.run`.", ""]
    (OUT / "summary.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()

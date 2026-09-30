"""
Run the load profile at increasing concurrency and write a report (P10).

    python loadtest/run_load.py --host https://localhost --steps 50,100,250,500 --duration 180 \\
        --label "10k tickets, API_WORKERS=2"

For each step: Locust (headless) ramps to N users, statistics are reset once
the ramp completes (`--reset-stats`), then the steady state runs for
`--duration` seconds. Container CPU/memory is sampled half-way through. Output:
reports/load/<timestamp>/{run.json,summary.md,step_<N>_*.csv}.

SLO used to call a step "within target" (set before running): p95 < 500 ms for
every endpoint group and < 1% failed requests. This is a local single-machine
test — the load generator shares the CPU with the stack — not a statement about
any production server.
"""

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCUST = Path(sys.executable).with_name("locust.exe" if sys.platform == "win32" else "locust")
P95_SLO_MS = 500
ERROR_SLO = 0.01


def docker_stats() -> list[dict]:
    out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}"], capture_output=True, text=True)
    rows = []
    for line in out.stdout.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append({"name": d.get("Name"), "cpu": d.get("CPUPerc"), "mem": d.get("MemUsage")})
    return rows


def parse_stats(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            n = int(r["Request Count"] or 0)
            rows.append({
                "name": r["Name"], "requests": n, "failures": int(r["Failure Count"] or 0),
                "rps": float(r["Requests/s"] or 0), "p50_ms": float(r["50%"] or 0), "p95_ms": float(r["95%"] or 0),
                "p99_ms": float(r["99%"] or 0), "max_ms": float(r["Max Response Time"] or 0),
            })
    return rows


def run_step(args, users: int, out: Path) -> dict:
    prefix = out / f"step_{users}"
    ramp = 12  # spawn rate users/10 per second → ~10 s ramp
    cmd = [str(LOCUST), "-f", str(ROOT / "loadtest" / "locustfile.py"), "--headless", "--host", args.host,
           "-u", str(users), "-r", str(max(5, users // 10)), "-t", f"{args.duration + ramp}s", "--reset-stats",
           "--csv", str(prefix), "--only-summary", "--stop-timeout", "10"]
    samples: list = []
    timer = threading.Timer(ramp + args.duration / 2, lambda: samples.append(docker_stats()))
    timer.start()
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "TOKENS": args.tokens})
    timer.cancel()
    (out / f"step_{users}.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    stats = parse_stats(Path(f"{prefix}_stats.csv"))
    agg = next((s for s in stats if s["name"] == "Aggregated"), None)
    groups = [s for s in stats if s["name"] != "Aggregated"]
    err = (agg["failures"] / agg["requests"]) if agg and agg["requests"] else None
    within = bool(agg) and err is not None and err < ERROR_SLO and all(g["p95_ms"] < P95_SLO_MS for g in groups)
    return {"users": users, "wall_seconds": round(time.time() - started, 1), "aggregate": agg, "endpoints": groups,
            "error_rate": err, "within_slo": within, "container_stats_midrun": samples[0] if samples else []}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="https://localhost")
    p.add_argument("--steps", default="50,100,250,500")
    p.add_argument("--duration", type=int, default=180)
    p.add_argument("--tokens", default=str(ROOT / "loadtest" / "tokens.json"))
    p.add_argument("--label", default="")
    p.add_argument("--tickets", type=int, default=None, help="ticket count in the load-test org (for the report)")
    args = p.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "reports" / "load" / stamp
    out.mkdir(parents=True, exist_ok=True)
    info = subprocess.run(["docker", "info", "--format", "{{.NCPU}} {{.MemTotal}}"], capture_output=True, text=True)
    ncpu, mem = (info.stdout.split() + ["?", "0"])[:2]
    steps = []
    for users in [int(x) for x in args.steps.split(",")]:
        print(f"step {users} users …", flush=True)
        result = run_step(args, users, out)
        steps.append(result)
        agg = result["aggregate"] or {}
        print(f"  rps {agg.get('rps', 0):.1f} p95 {agg.get('p95_ms', 0):.0f} ms errors {result['error_rate']}", flush=True)
        if result["error_rate"] is not None and result["error_rate"] > 0.2:
            print("  >20% errors — stopping the ramp", flush=True)
            break
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    run = {"timestamp": stamp, "label": args.label, "host": args.host, "duration_seconds_per_step": args.duration,
           "tickets_in_org": args.tickets, "git": git, "slo": {"p95_ms": P95_SLO_MS, "error_rate": ERROR_SLO},
           "environment": {"docker_cpus": ncpu, "docker_mem_bytes": int(mem or 0), "host": platform.platform(),
                           "processor": platform.processor(), "generator": "locust (same machine)"},
           "data_origin": "synthetic", "steps": steps}
    (out / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    (out / "summary.md").write_text(summary(run), encoding="utf-8")
    print(out / "summary.md")


def summary(run: dict) -> str:
    env = run["environment"]
    L = [f"# Load test — {run['label'] or run['timestamp']}", "",
         f"Local, single machine ({env['processor']}; Docker VM {env['docker_cpus']} CPUs, "
         f"{int(env['docker_mem_bytes']) / 2**30:.1f} GiB), production compose stack behind Caddy, load generator on "
         f"the same machine. SYNTHETIC load-test organization with {run['tickets_in_org'] or '?'} tickets. "
         f"Steady state {run['duration_seconds_per_step']} s per step after ramp-up. git `{run['git'][:10]}`. "
         f"SLO: p95 < {run['slo']['p95_ms']} ms per endpoint group, < {run['slo']['error_rate']:.0%} errors.", "",
         "| Users | Requests/s | p50 (ms) | p95 (ms) | p99 (ms) | Errors | Within SLO | Slowest group (p95) |",
         "|---|---|---|---|---|---|---|---|"]
    for s in run["steps"]:
        a = s["aggregate"] or {}
        slow = max(s["endpoints"], key=lambda g: g["p95_ms"], default=None)
        L.append(f"| {s['users']} | {a.get('rps', 0):.1f} | {a.get('p50_ms', 0):.0f} | {a.get('p95_ms', 0):.0f} | "
                 f"{a.get('p99_ms', 0):.0f} | {(s['error_rate'] or 0):.2%} | {'yes' if s['within_slo'] else 'no'} | "
                 f"{slow['name'] + ' (' + str(int(slow['p95_ms'])) + ' ms)' if slow else '—'} |")
    last = run["steps"][-1]
    L += ["", f"## Endpoint groups at {last['users']} users", "",
          "| Endpoint | Requests | Req/s | p50 | p95 | p99 | Failures |", "|---|---|---|---|---|---|---|"]
    for g in sorted(last["endpoints"], key=lambda g: -g["p95_ms"]):
        L.append(f"| {g['name']} | {g['requests']} | {g['rps']:.1f} | {g['p50_ms']:.0f} | {g['p95_ms']:.0f} | "
                 f"{g['p99_ms']:.0f} | {g['failures']} |")
    L += ["", "Container CPU / memory half-way through the last step: " + "; ".join(
        f"{c['name']} {c['cpu']} {c['mem']}" for c in last["container_stats_midrun"]) + ".", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()

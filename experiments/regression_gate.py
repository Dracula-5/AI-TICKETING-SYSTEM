"""
P13 — Model-promotion regression gate.

    EVAL_DATABASE_URL=postgresql+psycopg://... python experiments/regression_gate.py [--update-baseline]

Replays a fixed slice of one SYNTHETIC organization (Orbital Engineering, first
300 replayed tickets) through the production pipeline (experiments/
pipeline_eval.py) and compares quality with the committed baseline
reports/pipeline/gate_baseline.json. Exit code 1 if any quality metric drops by
more than its tolerance — a change to the embedding model, the triage engine
or the agent must pass this before it ships (docs/ai_evaluation.md).

Latency is reported but never gates: it depends on the machine.
`--update-baseline` records the current numbers as the new baseline (do this
only in the same pull request that justifies the change).
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "reports" / "pipeline" / "gate_baseline.json"
ORG = "orbital-engineering"
LIMIT = 300
TOLERANCE = {  # maximum allowed absolute drop
    "category_accuracy": 0.02,
    "category_macro_f1": 0.02,
    "priority_accuracy": 0.02,
    "category_selective_0.7_accuracy": 0.03,
}


def extract(result: dict) -> dict:
    m = result["metrics"]
    return {
        "category_accuracy": m["category"]["accuracy"],
        "category_macro_f1": m["category"]["macro_f1"],
        "category_coverage": m["category"]["coverage"],
        "category_selective_0.7_accuracy": m["category"]["selective"]["0.7"]["accuracy"],
        "priority_accuracy": m["priority"]["accuracy"],
        "analysis_p95_ms": result["latency_ms"]["p95"],
        "replayed": result["replayed"],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--update-baseline", action="store_true")
    p.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    args = p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [sys.executable, str(ROOT / "experiments" / "pipeline_eval.py"), "--orgs", ORG,
               "--limit-replay", str(LIMIT), "--out", tmp, "--model", args.model]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout[-2000:], proc.stderr[-4000:], sep="\n")
            return 2
        payload = json.loads((Path(tmp) / "p5_pipeline_synthetic.json").read_text(encoding="utf-8"))
    current = extract(payload["results"][0])
    current.update(model=args.model, engine=payload["params"]["engine_version"], planner=payload["params"]["planner"])
    if args.update_baseline or not BASELINE.exists():
        BASELINE.write_text(json.dumps({**current, "git": payload["git"], "org": ORG, "limit": LIMIT}, indent=2),
                            encoding="utf-8")
        print(f"baseline written: {BASELINE}")
        return 0
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    failed = []
    print(f"{'metric':38} {'baseline':>9} {'current':>9} {'allowed drop':>12}")
    for key, tol in TOLERANCE.items():
        b, c = base.get(key), current.get(key)
        ok = b is None or c is not None and c >= b - tol
        print(f"{key:38} {b if b is None else round(b, 4):>9} {c if c is None else round(c, 4):>9} {tol:>12}"
              f"  {'ok' if ok else 'REGRESSION'}")
        if not ok:
            failed.append(key)
    print(f"{'analysis_p95_ms (informational)':38} {base.get('analysis_p95_ms')!s:>9} "
          f"{round(current['analysis_p95_ms'], 1)!s:>9}")
    if failed:
        print(f"\nGate FAILED: {', '.join(failed)}")
        return 1
    print("\nGate passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

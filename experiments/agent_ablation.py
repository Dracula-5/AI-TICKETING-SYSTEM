"""
P7 — Agent ablation from the P5 pipeline replay (SYNTHETIC organizations).

    python experiments/agent_ablation.py

Uses the per-ticket records written by experiments/pipeline_eval.py
(reports/pipeline/p5_replay_records_<org>.jsonl) — the category the triage
agent proposed, its confidence and the recorded ground truth — and simulates
three operating modes on the same tickets:

A. no tools      — every ticket gets the organization's most common category
                   (a static default, what a desk without triage does);
B. tools, no gate — every AI category is applied automatically;
C. tools + gate + approval — applied automatically only at confidence >= t
                   (the org policy); everything else goes to the approval queue.

Reports automation rate (share changed without a person), error rate among
those automatic changes, and the human queue size. No new model run.
"""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPE = ROOT / "reports" / "pipeline"
GATES = (0.7, 0.9)


def main():
    rows = []
    for path in sorted(PIPE.glob("p5_replay_records_*.jsonl")):
        recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        n = len(recs)
        majority = Counter(r["category_true"] for r in recs).most_common(1)[0][0]
        a_err = sum(r["category_true"] != majority for r in recs) / n
        pred = [r for r in recs if r["category_pred"] is not None]
        b_err = sum(r["category_pred"] != r["category_true"] for r in pred) / len(pred) if pred else None
        out = {"org": path.stem.replace("p5_replay_records_", ""), "n": n,
               "A_no_tools": {"automation_rate": 1.0, "error_rate": a_err,
                              "note": "majority category of the replayed tickets (optimistic for A)"},
               "B_tools_no_gate": {"automation_rate": len(pred) / n, "error_rate": b_err}}
        for t in GATES:
            auto = [r for r in pred if (r["category_conf"] or 0) >= t]
            out[f"C_gate_{t}"] = {"automation_rate": len(auto) / n,
                                  "error_rate": sum(r["category_pred"] != r["category_true"] for r in auto) / len(auto)
                                  if auto else None,
                                  "queued_for_people": (n - len(auto)) / n}
        rows.append(out)
    (PIPE / "agent_ablation.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    L = ["# P7 — Agent ablation (category step, SYNTHETIC replay)", "",
         "Simulated on the per-ticket records of the P5 replay (`reports/pipeline/p5_replay_records_*.jsonl`). "
         "Automation = category changed without a person; error = automatic change differs from the recorded "
         "category. Mode A uses the replayed tickets' own majority category, which flatters it. "
         "Provenance: `reports/pipeline/agent_ablation.json`.", "",
         "| Organization | Tickets | A · no tools: error | B · tools, no gate: automated · error | "
         + " | ".join(f"C · gate {t}: automated · error · to people" for t in GATES) + " |",
         "|---|---|---|---|" + "---|" * len(GATES)]
    for r in rows:
        cells = []
        for t in GATES:
            c = r[f"C_gate_{t}"]
            err = "—" if c["error_rate"] is None else f"{c['error_rate']:.3f}"
            cells.append(f"{c['automation_rate']:.3f} · {err} · {c['queued_for_people']:.3f}")
        b = r["B_tools_no_gate"]
        L.append(f"| {r['org']} | {r['n']:,} | {r['A_no_tools']['error_rate']:.3f} | "
                 f"{b['automation_rate']:.3f} · {b['error_rate']:.3f} | " + " | ".join(cells) + " |")
    L += ["", "Reading: without the confidence gate every ticket is changed automatically and roughly half of "
          "those changes are wrong; with the default gate (0.9) a small share is automated with few errors and "
          "the rest waits for a person — the trade the approval queue exists for.", ""]
    (PIPE / "agent_ablation.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()

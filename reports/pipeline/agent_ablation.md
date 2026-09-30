# P7 — Agent ablation (category step, SYNTHETIC replay)

Simulated on the per-ticket records of the P5 replay (`reports/pipeline/p5_replay_records_*.jsonl`). Automation = category changed without a person; error = automatic change differs from the recorded category. Mode A uses the replayed tickets' own majority category, which flatters it. Provenance: `reports/pipeline/agent_ablation.json`.

| Organization | Tickets | A · no tools: error | B · tools, no gate: automated · error | C · gate 0.7: automated · error · to people | C · gate 0.9: automated · error · to people |
|---|---|---|---|---|---|
| brightline-retail | 800 | 0.714 | 1.000 · 0.530 | 0.091 · 0.096 · 0.909 | 0.055 · 0.000 · 0.945 |
| helix-health | 1,100 | 0.725 | 1.000 · 0.471 | 0.099 · 0.055 · 0.901 | 0.059 · 0.000 · 0.941 |
| orbital-engineering | 500 | 0.688 | 1.000 · 0.538 | 0.062 · 0.032 · 0.938 | 0.048 · 0.000 · 0.952 |

Reading: without the confidence gate every ticket is changed automatically and roughly half of those changes are wrong; with the default gate (0.9) a small share is automated with few errors and the rest waits for a person — the trade the approval queue exists for.

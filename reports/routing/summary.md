# P4.2 Routing — results (UCI ServiceNow incident log, real data)

Target: the assignment group that resolved the incident (49 classes incl. 'Other' for groups with <20 training incidents). Time-based split; test = the most recent 15% of incidents (n=3738). Provenance: `reports/routing/p4_routing_uci.json`.

| Router | Top-1 accuracy | Top-3 accuracy | p50 latency |
|---|---|---|---|
| Human dispatcher (first assignment, measured) | 0.673 |  |  |
| Category → group table (rules) | 0.515 |  |  |
| One-hot + Logistic regression | 0.655 | 0.857 | 1.04 ms |
| LightGBM (categorical) | 0.634 | 0.839 | 29.67 ms |

## Selective routing (logistic regression)

Auto-route only when the model's top probability clears a threshold; everything else goes to human triage. The human column is the dispatcher's first-assignment accuracy on the *same* tickets.

| Confidence ≥ | Auto-routed share | Model accuracy on them | Human accuracy on the same tickets |
|---|---|---|---|
| 0.3 | 0.926 | 0.685 | 0.684 |
| 0.5 | 0.673 | 0.779 | 0.759 |
| 0.7 | 0.437 | 0.873 | 0.852 |
| 0.9 | 0.160 | 0.937 | 0.928 |

## Where the logistic-regression router errs (test)

1289 wrong routes of 3738; the human dispatcher was also wrong on 829 of them. Most frequent confusions (true → predicted):

| True group | Predicted group | Count |
|---|---|---|
| Group 39 | Group 70 | 81 |
| Group 25 | Group 70 | 55 |
| Group 24 | Group 70 | 54 |
| Group 20 | Group 70 | 35 |
| Group 70 | Group 39 | 34 |
| Group 70 | Group 25 | 32 |
| Group 28 | Group 70 | 28 |
| Group 70 | Group 65 | 28 |

Lowest-recall groups with ≥ 30 test incidents: Group 54 (0.00 of 45), Other (0.04 of 51), Group 56 (0.06 of 32), Group 20 (0.09 of 46), Group 31 (0.26 of 35).

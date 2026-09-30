# P4.1b — Which classifier ships: per-organization learners compared

Same public benchmark and splits as P4.1 (LLM-generated support tickets, CC BY-NC 4.0; see docs/datasets.md). Each method learns only from a sampled 'organization history' of N training tickets; hyperparameters chosen on validation with full history; test split (n=2,455) scored once per cell. Latency = one ticket end to end (embedding or vectorizing + vote/predict) against the full history, CPU, p50 over 100 tickets. Provenance: `reports/classification/p4_production_classifier.json`.

**Novel macro-F1** is scored on the 2,169 of 2,455 test tickets with no training ticket at TF-IDF cosine ≥ 0.8 — nearest-neighbour methods can score well by finding near-copies, so this column is the fairer comparison for genuinely new tickets.

## queue

| Method | Params | Macro F1 @ N=50 · 200 · 1000 · 5000 · 11,433 | Accuracy (full) | Macro F1 full (95% CI) | Novel macro-F1 | Coverage / accuracy at conf ≥ 0.7 | p50 latency |
|---|---|---|---|---|---|---|---|
| kNN · all-MiniLM-L6-v2 | k=5, power=8 | 0.17 · 0.19 · 0.28 · 0.47 · 0.65 | 0.685 | 0.652 (0.629–0.681) | 0.615 | 0.44 / 0.901 | 42.7 ms |
| kNN · bge-small-en-v1.5 | k=5, power=8 | 0.16 · 0.18 · 0.28 · 0.42 · 0.57 | 0.618 | 0.573 (0.544–0.601) | 0.541 | 0.32 / 0.844 | 95.5 ms |
| kNN · TF-IDF | k=40, power=4 | 0.15 · 0.18 · 0.29 · 0.55 · 0.76 | 0.761 | 0.756 (0.733–0.779) | 0.719 | 0.57 / 0.991 | 76.6 ms |
| Tenant model · TF-IDF + LogReg | C=100 | 0.14 · 0.18 · 0.31 · 0.51 · 0.65 | 0.658 | 0.653 (0.628–0.681) | 0.605 | 0.54 / 0.832 | 2.1 ms |

## type

| Method | Params | Macro F1 @ N=50 · 200 · 1000 · 5000 · 11,433 | Accuracy (full) | Macro F1 full (95% CI) | Novel macro-F1 | Coverage / accuracy at conf ≥ 0.7 | p50 latency |
|---|---|---|---|---|---|---|---|
| kNN · all-MiniLM-L6-v2 | k=5, power=8 | 0.58 · 0.61 · 0.72 · 0.82 · 0.88 | 0.881 | 0.880 (0.866–0.893) | 0.867 | 0.82 / 0.934 | 43.2 ms |
| kNN · bge-small-en-v1.5 | k=5, power=8 | 0.54 · 0.62 · 0.73 · 0.81 · 0.86 | 0.865 | 0.863 (0.850–0.877) | 0.851 | 0.76 / 0.926 | 109.4 ms |
| kNN · TF-IDF | k=40, power=4 | 0.60 · 0.66 · 0.74 · 0.84 · 0.91 | 0.914 | 0.915 (0.903–0.925) | 0.904 | 0.84 / 0.975 | 27.1 ms |
| Tenant model · TF-IDF + LogReg | C=100 | 0.57 · 0.70 · 0.79 · 0.85 · 0.88 | 0.872 | 0.882 (0.870–0.892) | 0.871 | 0.91 / 0.912 | 3.8 ms |

## priority

| Method | Params | Macro F1 @ N=50 · 200 · 1000 · 5000 · 11,433 | Accuracy (full) | Macro F1 full (95% CI) | Novel macro-F1 | Coverage / accuracy at conf ≥ 0.7 | p50 latency |
|---|---|---|---|---|---|---|---|
| kNN · all-MiniLM-L6-v2 | k=5, power=8 | 0.35 · 0.36 · 0.41 · 0.57 · 0.72 | 0.726 | 0.717 (0.701–0.736) | 0.686 | 0.57 / 0.849 | 69.9 ms |
| kNN · bge-small-en-v1.5 | k=5, power=8 | 0.35 · 0.35 · 0.40 · 0.55 · 0.67 | 0.678 | 0.665 (0.647–0.685) | 0.635 | 0.43 / 0.828 | 158.7 ms |
| kNN · TF-IDF | k=5, power=8 | 0.36 · 0.37 · 0.42 · 0.61 · 0.77 | 0.784 | 0.774 (0.757–0.790) | 0.743 | 0.83 / 0.867 | 63.2 ms |
| Tenant model · TF-IDF + LogReg | C=100 | 0.34 · 0.34 · 0.41 · 0.56 · 0.67 | 0.689 | 0.674 (0.657–0.692) | 0.633 | 0.75 / 0.753 | 2.8 ms |

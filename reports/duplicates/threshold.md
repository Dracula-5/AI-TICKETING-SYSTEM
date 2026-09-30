# P4.3b — Production duplicate-flag threshold (all-MiniLM-L6-v2 cosine)

Same candidate pairs as P4.3 (every top-10 retrieved post). Rule set before looking at test: the lowest threshold whose **validation** precision is ≥ 0.5 → **0.75**. Provenance: `reports/duplicates/p4_duplicate_threshold.json`.

| Threshold | CQADupStack test precision | recall | false-positive rate | Synthetic precision | recall |
|---|---|---|---|---|---|
| 0.65 | 0.187 | 0.543 | 0.1834 | 0.919 | 0.998 |
| 0.7 | 0.296 | 0.340 | 0.0629 | 0.956 | 0.992 |
| 0.75 ← chosen | 0.470 | 0.184 | 0.0162 | 0.979 | 0.990 |
| 0.8 | 0.607 | 0.088 | 0.0044 | 0.989 | 0.969 |
| 0.85 | 0.812 | 0.034 | 0.0006 | 0.998 | 0.917 |
| 0.9 | 1.000 | 0.003 | 0.0000 | 0.997 | 0.821 |
| 0.95 | 0.000 | 0.000 | 0.0000 | 0.997 | 0.596 |

Real duplicates (different people describing one problem in different words) are far harder than the synthetic resubmissions; the public column is the one to plan with.

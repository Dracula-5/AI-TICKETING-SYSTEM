# P5 — Shipped AI triage pipeline, end to end (SYNTHETIC organizations)

Model `sentence-transformers/all-MiniLM-L6-v2` (FastEmbed ONNX, CPU) · PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) + pgvector 0.8.6 · engine `triage-knn-2` · planner `triage-playbook-1` · git `80f1e0d4a1`. Replays each synthetic organization's newest 20% of tickets, in time order with a simulated clock, against a history of tickets resolved before the cutoff, through the production code path (importer → reindex job → the triage agent). **Synthetic data: this measures the pipeline, not real users.** Provenance: `reports/pipeline/p5_pipeline_synthetic.json`.

## Recommendations vs recorded outcomes

| Organization | History / replayed | Category: coverage · accuracy · macro-F1 | Majority baseline | Category at conf ≥ 0.7: coverage · accuracy | Priority: coverage · accuracy |
|---|---|---|---|---|---|
| Helix Health (Synthetic) | 4,219 / 1,100 | 1.000 · 0.529 · 0.453 | 0.275 | 0.099 · 0.945 | 1.000 · 0.570 |
| Brightline Retail (Synthetic) | 3,070 / 800 | 1.000 · 0.470 · 0.384 | 0.286 | 0.091 · 0.904 | 1.000 · 0.552 |
| Orbital Engineering (Synthetic) | 1,927 / 500 | 1.000 · 0.462 · 0.374 | 0.312 | 0.062 · 0.968 | 1.000 · 0.470 |

Team routing equals category in this data (one team per queue), so it is not reported separately.

## Resolution time and SLA risk

| Organization | Resolution time MAE / MedAE (h) | Global-median baseline MAE / MedAE (h) | SLA risk: Brier · constant-rate Brier · ROC AUC |
|---|---|---|---|
| Helix Health (Synthetic) | 130.2 / 51.6 | 131.3 / 27.1 | 0.223 · 0.243 · 0.656 |
| Brightline Retail (Synthetic) | 139.7 / 46.4 | 140.7 / 27.0 | 0.226 · 0.245 · 0.654 |
| Orbital Engineering (Synthetic) | 131.2 / 67.0 | 131.5 / 32.8 | 0.241 · 0.249 · 0.623 |

## Duplicate flags (planted resubmissions — easier than real duplicates)

| Organization | Positives | ≥ 0.8: precision · recall | ≥ 0.85: precision · recall | ≥ 0.9: precision · recall | ≥ 0.95: precision · recall |
|---|---|---|---|---|---|
| Helix Health (Synthetic) | 40 | 0.072 · 0.925 | 0.107 · 0.900 | 0.143 · 0.750 | 0.140 · 0.525 |
| Brightline Retail (Synthetic) | 30 | 0.074 · 0.867 | 0.106 · 0.767 | 0.185 · 0.667 | 0.162 · 0.367 |
| Orbital Engineering (Synthetic) | 23 | 0.115 · 0.913 | 0.159 · 0.783 | 0.315 · 0.739 | 0.382 · 0.565 |

## Latency and indexing

| Organization | Analysis p50 / p95 / p99 (ms) | Embedding only p50 (ms) | Index throughput (tickets/s) | HNSW recall@60 NexaDesk settings / pgvector defaults | Rows returned (min) NexaDesk / defaults |
|---|---|---|---|---|---|
| Helix Health (Synthetic) | 154.4 / 663.4 / 1095.4 | 41.5 | 44.9 | 0.993 / 0.830 | 60 / 43 |
| Brightline Retail (Synthetic) | 187.4 / 582.9 / 916.5 | 29.7 | 25.2 | 1.000 / 0.412 | 60 / 14 |
| Orbital Engineering (Synthetic) | 314.2 / 747.3 / 1039.9 | 47.9 | 23.3 | 1.000 / 1.000 | 60 / 60 |

Hardware: Intel64 Family 6 Model 186 Stepping 3, GenuineIntel (12 logical CPUs), Windows-11-10.0.26300-SP0; single process; database in a local Docker container. Analysis latency = embed + vector search + votes + SLA statistics + knowledge-base lookup + validation + policy + writing the recommendations, measured around `app.agent.runner.run`.

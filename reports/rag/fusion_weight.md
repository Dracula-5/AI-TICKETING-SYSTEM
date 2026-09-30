# P6b — Lexical weight in hybrid retrieval (BM25 + all-MiniLM-L6-v2)

score = 1/(k+rank_dense) + w/(k+rank_lexical), k=60. w chosen on the validation half (n=539) by nDCG@10 → **w = 0.0**; test half (n=533) reported once. Provenance: `reports/rag/p6_fusion_weight.json`.

| w | Validation nDCG@10 | Test nDCG@10 | Test Recall@10 | Test MRR@10 |
|---|---|---|---|---|
| 0.0 ← chosen | 0.419 | 0.407 | 0.532 | 0.392 |
| 0.1 | 0.418 | 0.413 | 0.544 | 0.397 |
| 0.25 | 0.407 | 0.406 | 0.545 | 0.385 |
| 0.5 | 0.394 | 0.395 | 0.535 | 0.373 |
| 0.75 | 0.393 | 0.395 | 0.535 | 0.373 |
| 1.0 | 0.377 | 0.382 | 0.509 | 0.364 |

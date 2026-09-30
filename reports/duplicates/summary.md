# P4.3 Duplicate detection — results

## Public benchmark: CQADupStack unix (real, human-annotated duplicates)

Corpus 47,382 posts; 1072 queries with ≥1 annotated duplicate, split 50/50 into validation (threshold selection) and test. Retrieval metrics on test queries. The pair decision treats every top-10 candidate as a (query, candidate) pair: duplicate if similarity ≥ threshold. Provenance: `reports/duplicates/p4_duplicates.json`.

| Method | Recall@10 | MRR | Pair precision | Pair recall | Pair F1 | False-positive rate | p50 latency |
|---|---|---|---|---|---|---|---|
| tfidf_cosine | 0.324 | 0.268 | 0.406 | 0.332 | 0.365 | 0.0197 | 149.8 ms |
| all-MiniLM-L6-v2_cosine | 0.532 | 0.402 | 0.277 | 0.364 | 0.315 | 0.0738 | 26.2 ms |
| bge-small-en-v1.5_cosine | 0.478 | 0.366 | 0.290 | 0.319 | 0.304 | 0.0510 | 31.8 ms |
| all-MiniLM-L6-v2_plus_crossencoder_rerank | 0.508 | 0.395 | 0.421 | 0.369 | 0.393 | 0.0362 | 3374.3 ms |

## Internal sanity check (SYNTHETIC planted resubmissions)

Perturbation-based duplicates are much easier than real ones — reported only as a sanity check.

| Embedder | Precision | Recall | F1 | FPR |
|---|---|---|---|---|
| all-MiniLM-L6-v2 | 0.996 | 0.992 | 0.994 | 0.0014 |

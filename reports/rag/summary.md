# P6 — Knowledge-base retrieval: lexical vs dense vs hybrid vs hybrid + rerank

CQADupStack unix (real posts, human-annotated duplicates). Corpus 47,382 posts; 533 test queries (same split as P4.3). Candidates 30 per retriever, RRF k=60, cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2` over the fused top 20 — the candidate designs for `app/kb/search.py` (dense-first was chosen, see fusion_weight.md). Lexical = BM25 with the production stop list (production uses PostgreSQL full-text search with stemming). Provenance: `reports/rag/p6_retrieval_cqadupstack.json`.

| Retrieval | Recall@5 | Recall@10 | Recall@20 | MRR@10 | nDCG@10 |
|---|---|---|---|---|---|
| BM25 (lexical) | 0.304 | 0.342 | 0.395 | 0.269 | 0.274 |
| Dense · all-MiniLM-L6-v2 | 0.466 | 0.532 | 0.618 | 0.392 | 0.407 |
| Hybrid RRF · BM25 + all-MiniLM-L6-v2 | 0.392 | 0.505 | 0.594 | 0.352 | 0.372 |
| Dense · bge-small-en-v1.5 | 0.409 | 0.478 | 0.569 | 0.355 | 0.366 |
| Hybrid RRF · BM25 + bge-small-en-v1.5 | 0.380 | 0.471 | 0.554 | 0.333 | 0.351 |
| Hybrid RRF + rerank · BM25 + all-MiniLM-L6-v2 | 0.423 | 0.497 | 0.594 | 0.378 | 0.390 |
| Hybrid RRF + rerank · BM25 + bge-small-en-v1.5 | 0.393 | 0.476 | 0.554 | 0.368 | 0.377 |
| Dense + rerank · all-MiniLM-L6-v2 | 0.431 | 0.528 | 0.618 | 0.394 | 0.408 |

Cross-encoder cost: p50 1154 ms, p95 1813 ms per query for 20 candidates (PyTorch, CPU; production runs the ONNX export through FastEmbed).

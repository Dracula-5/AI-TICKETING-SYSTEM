"""
P6 — Retrieval benchmark for the knowledge base: lexical vs dense vs hybrid
(Reciprocal Rank Fusion) vs hybrid + cross-encoder reranking.

    python experiments/rag_retrieval.py

Data: CQADupStack unix (real StackExchange posts, human-annotated duplicates,
CC BY-SA 4.0; docs/datasets.md). Task: for a new post, retrieve the existing
posts that address the same problem — the retrieval step behind "related
articles" and grounded answers. Same corpus, queries, self-match masking and
50/50 split as P4.3 (experiments/duplicates.py); metrics on the test half.

Candidate designs for app/kb/search.py: 30 candidates per retriever, RRF with k=60,
cross-encoder over the fused top 20. Lexical here is BM25 over lower-cased
tokens with the production stop list; production uses PostgreSQL full-text
search (English stemming), so lexical numbers are indicative, not identical.
No answer generation is evaluated here (no LLM provider configured).
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from rank_bm25 import BM25Okapi  # noqa: E402

from duplicates import CORPUS, EMBEDDERS, QRELS, QUERIES, RERANKER, SEED, doc_text, mask_self  # noqa: E402
from nexadesk_ml import embeddings, metrics, tracking  # noqa: E402
from nexadesk_ml.paths import REPORTS  # noqa: E402

CANDIDATES = 30
RRF_K = 60
RERANK_TOP = 20
STOP = set(
    "a an and are as at be by can do does for from how i in is it my of on or our so the this to was what when where "
    "which who why will with you your".split()
)


def tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOP and len(t) > 1]


def rrf(*rankings, k=RRF_K):
    scores = {}
    for ranking in rankings:
        for rank, i in enumerate(ranking, start=1):
            scores[i] = scores.get(i, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda i: -scores[i])


def main():
    corpus = pd.read_parquet(CORPUS)
    queries = pd.read_parquet(QUERIES)
    rel = pd.read_parquet(QRELS).groupby("query_id")["doc_id"].apply(set)
    queries = queries[queries["query_id"].isin(rel.index)].reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    test = np.where(~(rng.random(len(queries)) < 0.5))[0]  # identical split to P4.3
    doc_ids = corpus["doc_id"].to_numpy()
    docs = corpus.apply(doc_text, axis=1).tolist()
    position = {d: i for i, d in enumerate(doc_ids)}
    self_idx = np.array([position.get(q, -1) for q in queries["query_id"]])
    relevant = [rel[q] for q in queries["query_id"]]
    qtext = queries["text"].tolist()

    t0 = time.perf_counter()
    bm25 = BM25Okapi([tokens(d) for d in docs])
    lexical = {}
    for qi in test:
        s = bm25.get_scores(tokens(qtext[qi]))
        if self_idx[qi] >= 0:
            s[self_idx[qi]] = -np.inf
        top = np.argpartition(-s, CANDIDATES)[:CANDIDATES]
        lexical[qi] = top[np.argsort(-s[top])].tolist()
    bm25_seconds = time.perf_counter() - t0

    dense = {}
    for model in EMBEDDERS:
        dvec = embeddings.encode(model, docs, batch_size=64)
        qvec = embeddings.encode(model, qtext)
        S = qvec[test] @ dvec.T
        mask_self(S, self_idx[test])
        top = np.argpartition(-S, CANDIDATES, axis=1)[:, :CANDIDATES]
        order = np.argsort(-np.take_along_axis(S, top, axis=1), axis=1)
        ranked = np.take_along_axis(top, order, axis=1)
        dense[model.split("/")[-1]] = {qi: ranked[j].tolist() for j, qi in enumerate(test)}

    from sentence_transformers import CrossEncoder

    ce = CrossEncoder(RERANKER, device="cpu")
    rerank_ms = []

    def rerank(qi, cand):
        t = time.perf_counter()
        s = ce.predict([(qtext[qi], docs[i][:1000]) for i in cand[:RERANK_TOP]], batch_size=32, show_progress_bar=False)
        rerank_ms.append((time.perf_counter() - t) * 1000)
        head = [cand[i] for i in np.argsort(-s)]
        return head + cand[RERANK_TOP:]

    systems = {"BM25 (lexical)": lexical}
    for short, ranking in dense.items():
        systems[f"Dense · {short}"] = ranking
        systems[f"Hybrid RRF · BM25 + {short}"] = {qi: rrf(lexical[qi], ranking[qi]) for qi in test}
    for short in dense:
        hyb = systems[f"Hybrid RRF · BM25 + {short}"]
        systems[f"Hybrid RRF + rerank · BM25 + {short}"] = {qi: rerank(qi, hyb[qi]) for qi in test}
    systems["Dense + rerank · all-MiniLM-L6-v2"] = {qi: rerank(qi, dense["all-MiniLM-L6-v2"][qi]) for qi in test}

    results = {}
    with tracking.run("rag", "p6_retrieval_cqadupstack", [CORPUS, QUERIES, QRELS]) as run:
        run.log_params(candidates=CANDIDATES, rrf_k=RRF_K, rerank_top=RERANK_TOP, reranker=RERANKER,
                       test_queries=len(test), corpus=len(docs), lexical="BM25Okapi, stop-listed lower-case tokens")
        for name, ranking in systems.items():
            ranked_ids = [[doc_ids[i] for i in ranking[qi]] for qi in test]
            r = metrics.ranking(ranked_ids, [relevant[qi] for qi in test])
            r["ndcg_at_10"] = ndcg([ranking[qi] for qi in test], [relevant[qi] for qi in test], doc_ids)
            results[name] = r
        lat = {"rerank_top20_p50_ms": float(np.percentile(rerank_ms, 50)),
               "rerank_top20_p95_ms": float(np.percentile(rerank_ms, 95)),
               "bm25_mean_ms_per_query_python": bm25_seconds / len(test) * 1000}
        run.log_metrics(systems=results, latency=lat)

    lines = ["# P6 — Knowledge-base retrieval: lexical vs dense vs hybrid vs hybrid + rerank", "",
             f"CQADupStack unix (real posts, human-annotated duplicates). Corpus {len(docs):,} posts; {len(test)} test "
             "queries (same split as P4.3). Candidates 30 per retriever, RRF k=60, cross-encoder "
             f"`{RERANKER}` over the fused top 20 — candidate designs for `app/kb/search.py` (dense-first was chosen: fusion_weight.md). Lexical = BM25 with the "
             "production stop list (production uses PostgreSQL full-text search with stemming). "
             "Provenance: `reports/rag/p6_retrieval_cqadupstack.json`.", "",
             "| Retrieval | Recall@5 | Recall@10 | Recall@20 | MRR@10 | nDCG@10 |", "|---|---|---|---|---|---|"]
    for name, r in results.items():
        lines.append(f"| {name} | {r['recall_at_5']:.3f} | {r['recall_at_10']:.3f} | {r['recall_at_20']:.3f} | "
                     f"{r['mrr_at_10']:.3f} | {r['ndcg_at_10']:.3f} |")
    lines += ["", f"Cross-encoder cost: p50 {lat['rerank_top20_p50_ms']:.0f} ms, p95 {lat['rerank_top20_p95_ms']:.0f} ms "
              "per query for 20 candidates (PyTorch, CPU; production runs the ONNX export through FastEmbed).", ""]
    (REPORTS / "rag").mkdir(exist_ok=True)
    (REPORTS / "rag" / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def ndcg(rankings, relevant, doc_ids, k=10):
    vals = []
    for ranking, rel in zip(rankings, relevant, strict=True):
        gains = [1.0 if doc_ids[i] in rel else 0.0 for i in ranking[:k]]
        dcg = sum(g / np.log2(r + 2) for r, g in enumerate(gains))
        ideal = sum(1.0 / np.log2(r + 2) for r in range(min(k, len(rel))))
        vals.append(dcg / ideal if ideal else 0.0)
    return float(np.mean(vals))


if __name__ == "__main__":
    main()

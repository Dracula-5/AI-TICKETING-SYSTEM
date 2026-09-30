"""
P6b — Choosing the lexical weight in hybrid retrieval.

    python experiments/rag_fusion_weight.py

P6 showed equal-weight RRF (BM25 + MiniLM) below dense-only on CQADupStack.
This sweeps the lexical weight w in  score = 1/(k+rank_dense) + w/(k+rank_lexical),
chooses w on the VALIDATION half of the queries (the half P6 did not report) and
reports the test half once. Same corpus, split, candidates and stop list as P6.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from rank_bm25 import BM25Okapi  # noqa: E402

from duplicates import CORPUS, QRELS, QUERIES, SEED, doc_text, mask_self  # noqa: E402
from nexadesk_ml import embeddings, metrics, tracking  # noqa: E402
from nexadesk_ml.paths import REPORTS  # noqa: E402
from rag_retrieval import CANDIDATES, RRF_K, ndcg, tokens  # noqa: E402

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
WEIGHTS = [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]


def fuse(dense, lexical, w):
    scores = {}
    for rank, i in enumerate(dense, start=1):
        scores[i] = scores.get(i, 0.0) + 1.0 / (RRF_K + rank)
    for rank, i in enumerate(lexical, start=1):
        scores[i] = scores.get(i, 0.0) + w / (RRF_K + rank)
    return sorted(scores, key=lambda i: -scores[i])


def main():
    corpus, queries = pd.read_parquet(CORPUS), pd.read_parquet(QUERIES)
    rel = pd.read_parquet(QRELS).groupby("query_id")["doc_id"].apply(set)
    queries = queries[queries["query_id"].isin(rel.index)].reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    val_mask = rng.random(len(queries)) < 0.5
    doc_ids = corpus["doc_id"].to_numpy()
    docs = corpus.apply(doc_text, axis=1).tolist()
    position = {d: i for i, d in enumerate(doc_ids)}
    self_idx = np.array([position.get(q, -1) for q in queries["query_id"]])
    relevant = [rel[q] for q in queries["query_id"]]
    qtext = queries["text"].tolist()

    bm25 = BM25Okapi([tokens(d) for d in docs])
    dvec = embeddings.encode(MODEL, docs, batch_size=64)
    qvec = embeddings.encode(MODEL, qtext)
    S = qvec @ dvec.T
    mask_self(S, self_idx)
    lexical, dense = {}, {}
    for qi in range(len(queries)):
        s = bm25.get_scores(tokens(qtext[qi]))
        if self_idx[qi] >= 0:
            s[self_idx[qi]] = -np.inf
        top = np.argpartition(-s, CANDIDATES)[:CANDIDATES]
        lexical[qi] = top[np.argsort(-s[top])].tolist()
        top = np.argpartition(-S[qi], CANDIDATES)[:CANDIDATES]
        dense[qi] = top[np.argsort(-S[qi][top])].tolist()

    def evaluate(idx, w):
        ranked = [fuse(dense[q], lexical[q], w) for q in idx]
        r = metrics.ranking([[doc_ids[i] for i in rk] for rk in ranked], [relevant[q] for q in idx])
        r["ndcg_at_10"] = ndcg(ranked, [relevant[q] for q in idx], doc_ids)
        return r

    val, test = np.where(val_mask)[0], np.where(~val_mask)[0]
    sweep = {str(w): {"validation": evaluate(val, w), "test": evaluate(test, w)} for w in WEIGHTS}
    chosen = max(WEIGHTS, key=lambda w: sweep[str(w)]["validation"]["ndcg_at_10"])
    with tracking.run("rag", "p6_fusion_weight", [CORPUS, QUERIES, QRELS]) as run:
        run.log_params(model=MODEL, weights=WEIGHTS, rrf_k=RRF_K, candidates=CANDIDATES)
        run.log_metrics(sweep=sweep, chosen_weight=chosen)
    L = ["# P6b — Lexical weight in hybrid retrieval (BM25 + all-MiniLM-L6-v2)", "",
         f"score = 1/(k+rank_dense) + w/(k+rank_lexical), k={RRF_K}. w chosen on the validation half "
         f"(n={len(val)}) by nDCG@10 → **w = {chosen}**; test half (n={len(test)}) reported once. "
         "Provenance: `reports/rag/p6_fusion_weight.json`.", "",
         "| w | Validation nDCG@10 | Test nDCG@10 | Test Recall@10 | Test MRR@10 |", "|---|---|---|---|---|"]
    for w in WEIGHTS:
        v, t = sweep[str(w)]["validation"], sweep[str(w)]["test"]
        mark = " ← chosen" if w == chosen else ""
        L.append(f"| {w}{mark} | {v['ndcg_at_10']:.3f} | {t['ndcg_at_10']:.3f} | {t['recall_at_10']:.3f} | "
                 f"{t['mrr_at_10']:.3f} |")
    (REPORTS / "rag" / "fusion_weight.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("chosen", chosen)


if __name__ == "__main__":
    main()

"""
P4.3 — Duplicate detection.

    python experiments/duplicates.py

Two evaluations, reported separately:

1. PUBLIC BENCHMARK — CQADupStack "unix" (real StackExchange posts, human-
   annotated duplicates, CC BY-SA 4.0): for each query post, retrieve earlier
   posts from a 47k-post corpus. Retrieval metrics (Recall@K, MRR@10), then a
   duplicate/not-duplicate decision on (query, candidate) pairs with a
   similarity threshold chosen on a validation half of the queries and applied
   to the test half (precision, recall, F1, false-positive rate).
2. INTERNAL (SYNTHETIC) — planted resubmissions in the synthetic ticket history
   vs hard negatives from the same queue and time window. Perturbation-based,
   therefore easier than real duplicates; a sanity check, not a headline.

Methods: TF-IDF cosine → sentence embeddings (MiniLM, BGE-small) → embeddings
+ cross-encoder reranking of the top candidates.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402

from nexadesk_ml import embeddings, metrics, tracking  # noqa: E402
from nexadesk_ml.paths import PROCESSED, REPORTS, SYNTHETIC  # noqa: E402

CORPUS = PROCESSED / "dup_unix_corpus.parquet"
QUERIES = PROCESSED / "dup_unix_queries.parquet"
QRELS = PROCESSED / "dup_unix_qrels.parquet"
SYN_TICKETS = SYNTHETIC / "tickets.parquet"
SYN_PAIRS = SYNTHETIC / "duplicate_pairs.parquet"
EMBEDDERS = ["sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-small-en-v1.5"]
RERANKER = "cross-encoder/ms-marco-MiniLM-L-6-v2"
TOP_K = 100
RERANK_K = 30
SEED = 7


def doc_text(row) -> str:
    return f"{row['title']}\n{row['text']}"[:2000]


def rank_dense(q_vecs: np.ndarray, d_vecs: np.ndarray, k: int, self_idx=None) -> tuple[np.ndarray, np.ndarray]:
    scores = q_vecs @ d_vecs.T
    mask_self(scores, self_idx)
    idx = np.argpartition(-scores, k, axis=1)[:, :k]
    part = np.take_along_axis(scores, idx, axis=1)
    order = np.argsort(-part, axis=1)
    return np.take_along_axis(idx, order, axis=1), np.take_along_axis(part, order, axis=1)


def mask_self(scores: np.ndarray, self_idx) -> None:
    """A query post is itself in the corpus; like BEIR (ignore_identical_ids)
    it must never count as its own duplicate."""
    if self_idx is None:
        return
    rows = np.where(self_idx >= 0)[0]
    scores[rows, self_idx[rows]] = -np.inf


def pair_metrics(scores_pos, scores_neg, threshold) -> dict:
    tp = int((scores_pos >= threshold).sum())
    fn = len(scores_pos) - tp
    fp = int((scores_neg >= threshold).sum())
    tn = len(scores_neg) - fp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"threshold": float(threshold), "precision": precision, "recall": recall, "f1": f1,
            "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0, "n_pos": len(scores_pos), "n_neg": len(scores_neg)}


def choose_threshold(pos, neg) -> float:
    candidates = np.unique(np.concatenate([pos, neg]))
    best = max(candidates, key=lambda t: pair_metrics(pos, neg, t)["f1"])
    return float(best)


def pairs_from_ranking(ranked_idx, ranked_scores, doc_ids, relevant):
    """Candidate pairs a duplicate detector would actually see: every retrieved
    top-10 candidate. Positive if it is an annotated duplicate."""
    pos, neg = [], []
    for row_idx, row_scores, rel in zip(ranked_idx, ranked_scores, relevant, strict=True):
        for i, s in zip(row_idx[:10], row_scores[:10], strict=True):
            (pos if doc_ids[i] in rel else neg).append(s)
    return np.array(pos), np.array(neg)


def main():
    corpus = pd.read_parquet(CORPUS)
    queries = pd.read_parquet(QUERIES)
    qrels = pd.read_parquet(QRELS)
    rel = qrels.groupby("query_id")["doc_id"].apply(set)
    queries = queries[queries["query_id"].isin(rel.index)].reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    val_mask = rng.random(len(queries)) < 0.5
    doc_ids = corpus["doc_id"].to_numpy()
    docs = corpus.apply(doc_text, axis=1).tolist()
    relevant = [rel[q] for q in queries["query_id"]]
    position = {d: i for i, d in enumerate(doc_ids)}
    self_idx = np.array([position.get(q, -1) for q in queries["query_id"]])
    rows = []

    with tracking.run("duplicates", "p4_duplicates", [CORPUS, QUERIES, QRELS, SYN_TICKETS, SYN_PAIRS]) as run:
        run.log_params(queries_present_in_corpus_excluded_as_self_match=int((self_idx >= 0).sum()),
                       corpus_size=len(corpus), queries=len(queries), val_queries=int(val_mask.sum()),
                       test_queries=int((~val_mask).sum()), top_k=TOP_K, rerank_k=RERANK_K, reranker=RERANKER)

        def record(name, ranked_idx, ranked_scores, latency=None):
            ranked_ids = [[doc_ids[i] for i in r] for r in ranked_idx]
            test_idx = np.where(~val_mask)[0]
            ret = metrics.ranking([ranked_ids[i] for i in test_idx], [relevant[i] for i in test_idx])
            pos_v, neg_v = pairs_from_ranking(ranked_idx[val_mask], ranked_scores[val_mask], doc_ids,
                                              [relevant[i] for i in np.where(val_mask)[0]])
            pos_t, neg_t = pairs_from_ranking(ranked_idx[~val_mask], ranked_scores[~val_mask], doc_ids,
                                              [relevant[i] for i in test_idx])
            thr = choose_threshold(pos_v, neg_v)
            pairs = pair_metrics(pos_t, neg_t, thr)
            run.log_metrics(**{name: {"retrieval_test": ret, "pair_decision_test": pairs, "latency": latency}})
            rows.append((name, ret, pairs, latency))

        # TF-IDF baseline
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=300_000)
        D = vec.fit_transform(docs)
        Q = vec.transform(queries["text"])
        S = (Q @ D.T).toarray()
        mask_self(S, self_idx)
        idx = np.argsort(-S, axis=1)[:, :TOP_K]
        record("tfidf_cosine", idx, np.take_along_axis(S, idx, axis=1),
               metrics.latency(lambda t: (vec.transform([t]) @ D.T), queries["text"].tolist()[:100]))

        dense = {}
        for model_name in EMBEDDERS:
            short = model_name.split("/")[-1]
            dvec = embeddings.encode(model_name, docs, batch_size=64)
            qvec = embeddings.encode(model_name, queries["text"].tolist())
            ridx, rsc = rank_dense(qvec, dvec, TOP_K, self_idx)
            dense[short] = (ridx, rsc)
            enc = embeddings.load(model_name)
            lat = metrics.latency(lambda t, e=enc, d=dvec: rank_dense(e.encode([t], normalize_embeddings=True), d, 10),
                                  queries["text"].tolist()[:100])
            record(f"{short}_cosine", ridx, rsc, lat)

        # Rerank the best dense model's top candidates with a cross-encoder.
        best_dense = max(rows[1:], key=lambda r: r[1]["mrr"])[0].replace("_cosine", "")
        ridx, _ = dense[best_dense]
        from sentence_transformers import CrossEncoder

        ce = CrossEncoder(RERANKER, device="cpu")
        rr_idx, rr_scores = [], []
        for qi, row in enumerate(ridx):
            cand = row[:RERANK_K]
            s = ce.predict([(queries["text"].iloc[qi], docs[i][:1000]) for i in cand], batch_size=32, show_progress_bar=False)
            order = np.argsort(-s)
            rr_idx.append(np.concatenate([cand[order], row[RERANK_K:]]))
            rr_scores.append(np.concatenate([s[order], np.full(len(row) - RERANK_K, s.min() - 1)]))
        lat = metrics.latency(lambda qi: ce.predict([(queries["text"].iloc[qi], docs[i][:1000]) for i in ridx[qi][:RERANK_K]],
                                                    batch_size=32, show_progress_bar=False), list(range(30)))
        record(f"{best_dense}_plus_crossencoder_rerank", np.array(rr_idx), np.array(rr_scores), {**lat, "note": f"rerank of top-{RERANK_K} only"})

        # Internal synthetic sanity check
        syn = pd.read_parquet(SYN_TICKETS)
        pairs = pd.read_parquet(SYN_PAIRS)
        text = (syn["subject"].fillna("") + "\n" + syn["body"].fillna("")).tolist()
        syn_results = {}
        for model_name in EMBEDDERS[:1]:
            vecs = embeddings.encode(model_name, text)
            sims = np.einsum("ij,ij->i", vecs[pairs["a"]], vecs[pairs["b"]])
            half = rng.random(len(pairs)) < 0.5
            thr = choose_threshold(sims[half & (pairs["label"] == 1)], sims[half & (pairs["label"] == 0)])
            syn_results[model_name.split("/")[-1]] = pair_metrics(sims[~half & (pairs["label"] == 1)],
                                                                  sims[~half & (pairs["label"] == 0)], thr)
        run.log_metrics(synthetic_in_domain=syn_results)

    lines = [
        "# P4.3 Duplicate detection — results", "",
        "## Public benchmark: CQADupStack unix (real, human-annotated duplicates)", "",
        f"Corpus {len(corpus):,} posts; {len(queries)} queries with ≥1 annotated duplicate, split 50/50 into "
        "validation (threshold selection) and test. Retrieval metrics on test queries. The pair decision treats "
        "every top-10 candidate as a (query, candidate) pair: duplicate if similarity ≥ threshold. "
        "Provenance: `reports/duplicates/p4_duplicates.json`.", "",
        "| Method | Recall@10 | MRR | Pair precision | Pair recall | Pair F1 | False-positive rate | p50 latency |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, ret, pairs_, lat in rows:
        lines.append(f"| {name} | {ret['recall_at_10']:.3f} | {ret['mrr']:.3f} | {pairs_['precision']:.3f} | "
                     f"{pairs_['recall']:.3f} | {pairs_['f1']:.3f} | {pairs_['false_positive_rate']:.4f} | "
                     f"{'' if not lat else f'{lat['p50_ms']:.1f} ms'} |")
    lines += ["", "## Internal sanity check (SYNTHETIC planted resubmissions)", "",
              "Perturbation-based duplicates are much easier than real ones — reported only as a sanity check.", "",
              "| Embedder | Precision | Recall | F1 | FPR |", "|---|---|---|---|---|"]
    for name, r in syn_results.items():
        lines.append(f"| {name} | {r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} | {r['false_positive_rate']:.4f} |")
    lines.append("")
    (REPORTS / "duplicates" / "summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

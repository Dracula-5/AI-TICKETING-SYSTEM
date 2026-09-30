"""
P4.3b — Choosing the production duplicate-flag threshold.

    python experiments/duplicate_threshold.py

P4.3 picks the F1-optimal cosine threshold; a "possible duplicate" flag shown to
agents needs higher precision than that. This sweeps thresholds for the
production embedder (all-MiniLM-L6-v2) over the same top-10 candidate pairs as
P4.3, on the validation half (to choose) and the test half (to report), for the
public CQADupStack benchmark and the SYNTHETIC planted duplicates.
Uses the embedding cache written by experiments/duplicates.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from duplicates import CORPUS, QRELS, QUERIES, SEED, SYN_PAIRS, SYN_TICKETS, doc_text, pair_metrics, rank_dense  # noqa: E402
from nexadesk_ml import embeddings, tracking  # noqa: E402
from nexadesk_ml.paths import REPORTS  # noqa: E402

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
THRESHOLDS = [0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
MIN_PRECISION = 0.5  # target for a flag an agent must review


def main():
    corpus, queries = pd.read_parquet(CORPUS), pd.read_parquet(QUERIES)
    rel = pd.read_parquet(QRELS).groupby("query_id")["doc_id"].apply(set)
    queries = queries[queries["query_id"].isin(rel.index)].reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    val = rng.random(len(queries)) < 0.5  # identical split to P4.3
    doc_ids = corpus["doc_id"].to_numpy()
    position = {d: i for i, d in enumerate(doc_ids)}
    self_idx = np.array([position.get(q, -1) for q in queries["query_id"]])
    dvec = embeddings.encode(MODEL, corpus.apply(doc_text, axis=1).tolist(), batch_size=64)
    qvec = embeddings.encode(MODEL, queries["text"].tolist())
    idx, sc = rank_dense(qvec, dvec, 10, self_idx)
    relevant = [rel[q] for q in queries["query_id"]]
    labels = np.array([[doc_ids[i] in relevant[q] for i in row] for q, row in enumerate(idx)])

    def sweep(mask):
        pos, neg = sc[mask][labels[mask]], sc[mask][~labels[mask]]
        return {str(t): pair_metrics(pos, neg, t) for t in THRESHOLDS}

    public = {"validation": sweep(val), "test": sweep(~val)}
    chosen = next((t for t in THRESHOLDS if public["validation"][str(t)]["precision"] >= MIN_PRECISION), THRESHOLDS[-1])

    syn, pairs = pd.read_parquet(SYN_TICKETS), pd.read_parquet(SYN_PAIRS)
    vecs = embeddings.encode(MODEL, (syn["subject"].fillna("") + "\n" + syn["body"].fillna("")).tolist())
    sims = np.einsum("ij,ij->i", vecs[pairs["a"]], vecs[pairs["b"]])
    lab = pairs["label"].to_numpy() == 1
    synthetic = {str(t): pair_metrics(sims[lab], sims[~lab], t) for t in THRESHOLDS}

    with tracking.run("duplicates", "p4_duplicate_threshold", [CORPUS, QUERIES, QRELS, SYN_TICKETS, SYN_PAIRS]) as run:
        run.log_params(model=MODEL, thresholds=THRESHOLDS, min_precision=MIN_PRECISION)
        run.log_metrics(public=public, synthetic=synthetic, chosen_threshold=chosen)

    L = ["# P4.3b — Production duplicate-flag threshold (all-MiniLM-L6-v2 cosine)", "",
         "Same candidate pairs as P4.3 (every top-10 retrieved post). Rule set before looking at test: the lowest "
         f"threshold whose **validation** precision is ≥ {MIN_PRECISION} → **{chosen}**. "
         "Provenance: `reports/duplicates/p4_duplicate_threshold.json`.", "",
         "| Threshold | CQADupStack test precision | recall | false-positive rate | Synthetic precision | recall |",
         "|---|---|---|---|---|---|"]
    for t in THRESHOLDS:
        p, s = public["test"][str(t)], synthetic[str(t)]
        mark = " ← chosen" if t == chosen else ""
        L.append(f"| {t}{mark} | {p['precision']:.3f} | {p['recall']:.3f} | {p['false_positive_rate']:.4f} | "
                 f"{s['precision']:.3f} | {s['recall']:.3f} |")
    L += ["", "Real duplicates (different people describing one problem in different words) are far harder than the "
          "synthetic resubmissions; the public column is the one to plan with.", ""]
    (REPORTS / "duplicates" / "threshold.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()

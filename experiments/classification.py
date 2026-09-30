"""
P4.1 — Ticket classification (queue / type / priority) from ticket text.

    python experiments/classification.py

Data: public support-ticket texts (LLM-generated, CC BY-NC 4.0), English,
exact duplicates removed before a stratified 70/15/15 split
(docs/datasets.md). Models are selected on the validation split; the test
split is scored once. Output: reports/classification/*.json + summary.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.dummy import DummyClassifier  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import f1_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.svm import LinearSVC  # noqa: E402

from nexadesk_ml import embeddings, metrics, tracking  # noqa: E402
from nexadesk_ml.paths import PROCESSED, REPORTS  # noqa: E402

TASKS = ["queue", "type", "priority"]
EMBEDDERS = ["sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-small-en-v1.5"]
DATA = PROCESSED / "tickets_en.parquet"


def load():
    df = pd.read_parquet(DATA)
    return {s: df[df["split"] == s].reset_index(drop=True) for s in ("train", "val", "test")}


def tfidf_model(kind: str, C: float):
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=200_000)
    clf = LogisticRegression(C=C, max_iter=2000, class_weight="balanced") if kind == "logreg" else LinearSVC(C=C, class_weight="balanced")
    return make_pipeline(vec, clf)


def macro_f1(y, p):
    return f1_score(y, p, average="macro", zero_division=0)


def select_tfidf(kind, tr, va, task):
    best = None
    for C in (0.3, 1.0, 3.0, 10.0):
        m = tfidf_model(kind, C).fit(tr["text"], tr[task])
        score = macro_f1(va[task], m.predict(va["text"]))
        if best is None or score > best[0]:
            best = (score, C, m)
    return best


def select_embed_head(Xtr, ytr, Xva, yva):
    best = None
    for C in (0.3, 1.0, 3.0, 10.0):
        m = LogisticRegression(C=C, max_iter=3000, class_weight="balanced").fit(Xtr, ytr)
        score = macro_f1(yva, m.predict(Xva))
        if best is None or score > best[0]:
            best = (score, C, m)
    return best


def leakage_check(tr, te) -> np.ndarray:
    """Max TF-IDF cosine of each test ticket to any train ticket."""
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True).fit(tr["text"])
    A = vec.transform(te["text"])
    B = vec.transform(tr["text"])
    out = np.zeros(A.shape[0])
    for i in range(0, A.shape[0], 500):
        out[i : i + 500] = (A[i : i + 500] @ B.T).max(axis=1).toarray().ravel()
    return out


def evaluate(name, task, model_predict, predict_proba, classes, te, run, latency_fn=None, novel_mask=None):
    pred = model_predict(te)
    res = metrics.classification(te[task], pred, classes)
    res["macro_f1_ci95"] = metrics.bootstrap_ci(macro_f1, te[task].to_numpy(), np.asarray(pred))
    if predict_proba is not None:
        proba = predict_proba(te)
        res["top2_accuracy"] = metrics.top_k_accuracy(te[task], proba, classes, 2)
        conf = proba.max(axis=1)
        res["mean_confidence"] = float(conf.mean())
        for thr in (0.5, 0.7):
            keep = conf >= thr
            res[f"coverage_at_conf_{thr}"] = float(keep.mean())
            res[f"accuracy_at_conf_{thr}"] = float((np.asarray(pred)[keep] == te[task].to_numpy()[keep]).mean()) if keep.any() else None
    if novel_mask is not None and novel_mask.any():
        res["macro_f1_on_novel_test_subset"] = macro_f1(te[task][novel_mask], np.asarray(pred)[novel_mask])
        res["novel_subset_size"] = int(novel_mask.sum())
    if latency_fn is not None:
        res["latency_single_ticket"] = latency_fn
    run.log_metrics(**{name: res})
    return res


def main():
    splits = load()
    tr, va, te = splits["train"], splits["val"], splits["test"]
    sims = leakage_check(tr, te)
    novel = sims < 0.8
    summary_rows = []

    with tracking.run("classification", "p4_text_classification", [DATA]) as run:
        run.log_params(split_sizes={k: len(v) for k, v in splits.items()}, seed=42,
                       selection_metric="validation macro-F1", embedders=EMBEDDERS)
        run.log_metrics(leakage_check={
            "test_max_cosine_to_train_p50": float(np.median(sims)),
            "test_max_cosine_to_train_p95": float(np.percentile(sims, 95)),
            "share_test_with_near_duplicate_in_train_cos_ge_0.8": float((sims >= 0.8).mean()),
            "share_test_with_near_duplicate_in_train_cos_ge_0.95": float((sims >= 0.95).mean()),
        })
        run.note("Test tickets with a near-duplicate (TF-IDF cosine >= 0.8) in train are reported separately; "
                 "'macro_f1_on_novel_test_subset' excludes them.")

        emb = {}
        for model_name in EMBEDDERS:
            emb[model_name] = {s: embeddings.encode(model_name, d["text"].tolist()) for s, d in splits.items()}

        sample = te["text"].tolist()[:200]
        for task in TASKS:
            classes = sorted(tr[task].unique())

            dummy = DummyClassifier(strategy="most_frequent").fit(tr["text"], tr[task])
            r = evaluate(f"{task}.majority_class", task, lambda d: dummy.predict(d["text"]), None, classes, te, run)
            summary_rows.append((task, "Majority class", r, None))

            for kind in ("logreg", "linearsvc"):
                val_score, C, m = select_tfidf(kind, tr, va, task)
                run.log_params(**{f"{task}.tfidf_{kind}.C": C, f"{task}.tfidf_{kind}.val_macro_f1": round(val_score, 4)})
                lat = metrics.latency(lambda t, m=m: m.predict([t]), sample)
                proba = (lambda d, m=m: m.predict_proba(d["text"])) if kind == "logreg" else None
                r = evaluate(f"{task}.tfidf_{kind}", task, lambda d, m=m: m.predict(d["text"]), proba, classes, te, run, lat, novel)
                summary_rows.append((task, f"TF-IDF + {'LogReg' if kind == 'logreg' else 'LinearSVC'}", r, lat))

            for model_name in EMBEDDERS:
                E = emb[model_name]
                val_score, C, head = select_embed_head(E["train"], tr[task], E["val"], va[task])
                short = model_name.split("/")[-1]
                run.log_params(**{f"{task}.{short}.C": C, f"{task}.{short}.val_macro_f1": round(val_score, 4)})
                encoder = embeddings.load(model_name)
                lat = metrics.latency(
                    lambda t, enc=encoder, h=head: h.predict(enc.encode([t], normalize_embeddings=True)), sample)
                r = evaluate(f"{task}.{short}_logreg", task, lambda d, h=head, X=E["test"]: h.predict(X),
                             lambda d, h=head, X=E["test"]: h.predict_proba(X), classes, te, run, lat, novel)
                summary_rows.append((task, f"{short} embeddings + LogReg", r, lat))

    write_summary(summary_rows, sims)


def write_summary(rows, sims):
    lines = [
        "# P4.1 Ticket classification — results",
        "",
        "Dataset: public support-ticket texts (LLM-generated, CC BY-NC 4.0), English, exact duplicates removed, "
        "stratified 70/15/15 split. Models selected on validation macro-F1; **test split scored once**. "
        "Latency: single ticket, CPU, p50 over 200 test tickets (includes embedding for embedding models). "
        "Provenance: `reports/classification/p4_text_classification.json`.",
        "",
        f"Leakage check: median max TF-IDF cosine of a test ticket to the train set = {np.median(sims):.2f}; "
        f"{(sims >= 0.8).mean() * 100:.1f}% of test tickets have a train near-duplicate (cosine ≥ 0.8). "
        "'Novel macro-F1' is computed on the remaining test tickets.",
        "",
    ]
    for task in TASKS:
        lines += [f"## {task}", "", "| Model | Accuracy | Macro F1 (95% CI) | Weighted F1 | Novel macro-F1 | p50 latency |",
                  "|---|---|---|---|---|---|"]
        for t, name, r, lat in rows:
            if t != task:
                continue
            ci = r["macro_f1_ci95"]
            novel = r.get("macro_f1_on_novel_test_subset")
            lines.append(
                f"| {name} | {r['accuracy']:.3f} | {r['macro_f1']:.3f} ({ci['low']:.3f}–{ci['high']:.3f}) | "
                f"{r['weighted_f1']:.3f} | {'' if novel is None else f'{novel:.3f}'} | "
                f"{'' if lat is None else f'{lat['p50_ms']:.1f} ms'} |")
        lines.append("")
    (REPORTS / "classification" / "summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

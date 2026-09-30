"""
P4.1b — Choosing the classifier NexaDesk ships.

    python experiments/production_classifier.py

Constraint that shapes the choice: every organization has its own taxonomy, so
one global model trained on one dataset's labels cannot serve every tenant.
Whatever ships must learn from a single organization's resolved tickets,
starting from very little history. Candidates:

* kNN over sentence embeddings (MiniLM, BGE-small) — no training step, the
  neighbours double as "similar tickets" evidence, reuses the duplicate index.
* kNN over TF-IDF vectors of the org's history.
* A per-tenant TF-IDF + logistic-regression model, retrained in the background
  as history grows (probabilities → a confidence for the auto-apply policy).

Each is measured on the public ticket benchmark (queue / type / priority) with
a learning curve over history size N (the cold-start picture for a new
organization), selective accuracy at confidence thresholds, and single-ticket
latency. Hyperparameters are chosen on validation with full history; the test
split is scored once per (method, task, N).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402

from nexadesk_ml import embeddings, metrics, tracking  # noqa: E402
from nexadesk_ml.paths import PROCESSED, REPORTS  # noqa: E402

DATA = PROCESSED / "tickets_en.parquet"
EMBEDDERS = ["sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-small-en-v1.5"]
TASKS = ["queue", "type", "priority"]
HISTORY_SIZES = [50, 200, 1000, 5000, None]  # None = all training tickets
THRESHOLDS = (0.5, 0.7, 0.9)
NEAR_DUP = 0.8  # same definition as P4.1's leakage check
SEED = 11


def tfidf(min_df: int = 1) -> TfidfVectorizer:
    return TfidfVectorizer(ngram_range=(1, 2), min_df=min_df, sublinear_tf=True, max_features=200_000)


def knn_vote(sims: np.ndarray, yh: np.ndarray, classes: list[str], k: int, power: float):
    """Similarity-weighted vote over the top-k neighbours; weights = max(sim, 0) ** power."""
    k = min(k, sims.shape[1])
    idx = np.argpartition(-sims, k - 1, axis=1)[:, :k]
    top = np.take_along_axis(sims, idx, axis=1)
    w = np.clip(top, 0, None) ** power
    cidx = {c: i for i, c in enumerate(classes)}
    lab = np.vectorize(cidx.get)(yh[idx])
    scores = np.zeros((sims.shape[0], len(classes)))
    np.add.at(scores, (np.repeat(np.arange(sims.shape[0]), k), lab.ravel()), w.ravel())
    proba = scores / np.maximum(scores.sum(axis=1, keepdims=True), 1e-12)
    return np.asarray(classes)[proba.argmax(axis=1)], proba


class EmbedKNN:
    def __init__(self, model: str, E: dict, k: int = 20, power: float = 4.0):
        self.model, self.E, self.k, self.power = model, E, k, power

    def fit(self, pick, y):
        self.Xh, self.yh = self.E["train"][pick], y
        return self

    def predict(self, split, classes):
        return knn_vote(self.E[split] @ self.Xh.T, self.yh, classes, self.k, self.power)

    def predict_one(self, text, classes):
        q = embeddings.load(self.model).encode([text], normalize_embeddings=True)
        return knn_vote(q @ self.Xh.T, self.yh, classes, self.k, self.power)


class TfidfKNN:
    def __init__(self, texts: dict, k: int = 20, power: float = 4.0):
        self.texts, self.k, self.power = texts, k, power

    def fit(self, pick, y):
        self.vec = tfidf().fit(self.texts["train"][pick])
        self.Xh, self.yh = self.vec.transform(self.texts["train"][pick]), y
        return self

    def predict(self, split, classes):
        return knn_vote((self.vec.transform(self.texts[split]) @ self.Xh.T).toarray(), self.yh, classes, self.k, self.power)

    def predict_one(self, text, classes):
        return knn_vote((self.vec.transform([text]) @ self.Xh.T).toarray(), self.yh, classes, self.k, self.power)


class TenantLogReg:
    def __init__(self, texts: dict, C: float = 10.0):
        self.texts, self.C = texts, C

    def fit(self, pick, y):
        self.vec = tfidf(min_df=1 if len(pick) < 1000 else 2).fit(self.texts["train"][pick])
        self.clf = LogisticRegression(C=self.C, max_iter=3000, class_weight="balanced")
        self.clf.fit(self.vec.transform(self.texts["train"][pick]), y)
        return self

    def _proba(self, X, classes):
        p = self.clf.predict_proba(X)
        full = np.zeros((X.shape[0], len(classes)))  # classes absent from a small history get 0
        cols = [classes.index(c) for c in self.clf.classes_]
        full[:, cols] = p
        return np.asarray(classes)[full.argmax(axis=1)], full

    def predict(self, split, classes):
        return self._proba(self.vec.transform(self.texts[split]), classes)

    def predict_one(self, text, classes):
        return self._proba(self.vec.transform([text]), classes)


def novel_mask(tr, te) -> np.ndarray:
    """True where a test ticket has no train ticket with TF-IDF cosine >= NEAR_DUP.
    kNN can win by looking up near-copies; this subset shows what it does on new text."""
    vec = tfidf().fit(tr["text"])
    A, B = vec.transform(te["text"]), vec.transform(tr["text"])
    best = np.concatenate([(A[i : i + 500] @ B.T).max(axis=1).toarray().ravel() for i in range(0, A.shape[0], 500)])
    return best < NEAR_DUP


def selective(pred, proba, y):
    conf = proba.max(axis=1)
    out = {}
    for thr in THRESHOLDS:
        keep = conf >= thr
        out[str(thr)] = {"coverage": float(keep.mean()),
                         "accuracy": float((pred[keep] == y[keep]).mean()) if keep.any() else None}
    return out


def main():
    df = pd.read_parquet(DATA)
    tr, va, te = (df[df["split"] == s].reset_index(drop=True) for s in ("train", "val", "test"))
    texts = {s: d["text"].to_numpy() for s, d in (("train", tr), ("val", va), ("test", te))}
    all_idx = np.arange(len(tr))
    rng = np.random.default_rng(SEED)
    picks = {str(n or len(tr)): (rng.choice(len(tr), n, replace=False) if n else all_idx) for n in HISTORY_SIZES}
    novel = novel_mask(tr, te)

    methods = {}
    for m in EMBEDDERS:
        E = {s: embeddings.encode(m, d["text"].tolist()) for s, d in (("train", tr), ("val", va), ("test", te))}
        methods[f"kNN · {m.split('/')[-1]}"] = lambda k, p, m=m, E=E: EmbedKNN(m, E, k, p)
    methods["kNN · TF-IDF"] = lambda k, p: TfidfKNN(texts, k, p)
    methods["Tenant model · TF-IDF + LogReg"] = lambda C, _: TenantLogReg(texts, C)
    grids = {name: ([(k, p) for k in (5, 10, 20, 40) for p in (1.0, 4.0, 8.0)] if name.startswith("kNN")
                    else [(C, None) for C in (1.0, 10.0, 100.0)]) for name in methods}

    rows = []
    with tracking.run("classification", "p4_production_classifier", [DATA]) as run:
        run.log_params(methods=list(methods), history_sizes=list(picks), thresholds=THRESHOLDS, seed=SEED,
                       novel_test_tickets=int(novel.sum()), near_duplicate_cosine=NEAR_DUP)
        for task in TASKS:
            classes = sorted(tr[task].unique())
            ytr, yte = tr[task].to_numpy(), te[task].to_numpy()
            for name, make in methods.items():
                best = None
                for a, b in grids[name]:
                    pred, _ = make(a, b).fit(all_idx, ytr).predict("val", classes)
                    f1 = metrics.classification(va[task], pred, classes)["macro_f1"]
                    if best is None or f1 > best[0]:
                        best = (f1, a, b)
                _, a, b = best
                curve = {}
                for n, pick in picks.items():
                    t0 = time.perf_counter()
                    model = make(a, b).fit(pick, ytr[pick])
                    fit_s = time.perf_counter() - t0
                    pred, proba = model.predict("test", classes)
                    res = metrics.classification(yte, pred, classes)
                    curve[n] = {"accuracy": res["accuracy"], "macro_f1": res["macro_f1"], "weighted_f1": res["weighted_f1"],
                                "selective": selective(pred, proba, yte), "fit_seconds": round(fit_s, 3)}
                    if n == str(len(tr)):
                        res["macro_f1_ci95"] = metrics.bootstrap_ci(
                            lambda y, p: metrics.classification(y, p, classes)["macro_f1"], yte, pred, n=300)
                        res["novel"] = metrics.classification(yte[novel], pred[novel], classes)
                        full = res
                lat = metrics.latency(lambda i, mdl=model: mdl.predict_one(te["text"][i], classes), list(range(100)))
                params = {"k": a, "power": b} if name.startswith("kNN") else {"C": a}
                run.log_metrics(**{f"{name}.{task}": {"params": params, "test_full_history": full,
                                                      "learning_curve": curve, "latency_single": lat}})
                rows.append((task, name, params, full, curve, lat))
                print(task, name, params, round(full["macro_f1"], 3), flush=True)
    write_summary(rows, len(tr), int(novel.sum()), len(te))


def write_summary(rows, n_train, n_novel, n_test):
    lines = ["# P4.1b — Which classifier ships: per-organization learners compared", "",
             "Same public benchmark and splits as P4.1 (LLM-generated support tickets, CC BY-NC 4.0; see "
             "docs/datasets.md). Each method learns only from a sampled 'organization history' of N training tickets; "
             "hyperparameters chosen on validation with full history; test split (n=2,455) scored once per cell. "
             "Latency = one ticket end to end (embedding or vectorizing + vote/predict) against the full history, CPU, "
             "p50 over 100 tickets. Provenance: `reports/classification/p4_production_classifier.json`.", "",
             f"**Novel macro-F1** is scored on the {n_novel:,} of {n_test:,} test tickets with no training ticket at "
             f"TF-IDF cosine ≥ {NEAR_DUP} — nearest-neighbour methods can score well by finding near-copies, so this "
             "column is the fairer comparison for genuinely new tickets.", ""]
    for task in TASKS:
        lines += [f"## {task}", "",
                  f"| Method | Params | Macro F1 @ N=50 · 200 · 1000 · 5000 · {n_train:,} | Accuracy (full) | "
                  "Macro F1 full (95% CI) | Novel macro-F1 | Coverage / accuracy at conf ≥ 0.7 | p50 latency |",
                  "|---|---|---|---|---|---|---|---|"]
        for t, name, params, full, curve, lat in rows:
            if t != task:
                continue
            ci = full["macro_f1_ci95"]
            lc = " · ".join(f"{v['macro_f1']:.2f}" for v in curve.values())
            s = curve[str(n_train)]["selective"]["0.7"]
            sel = f"{s['coverage']:.2f} / {s['accuracy']:.3f}" if s["accuracy"] is not None else "0.00 / —"
            p = ", ".join(f"{k}={v:g}" for k, v in params.items())
            lines.append(f"| {name} | {p} | {lc} | {full['accuracy']:.3f} | {full['macro_f1']:.3f} "
                         f"({ci['low']:.3f}–{ci['high']:.3f}) | {full['novel']['macro_f1']:.3f} | {sel} | {lat['p50_ms']:.1f} ms |")
        lines.append("")
    (REPORTS / "classification" / "production_classifier.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

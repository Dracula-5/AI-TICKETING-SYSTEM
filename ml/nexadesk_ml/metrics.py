"""Evaluation metrics shared by all experiments (thin, tested wrappers)."""

import time
from collections.abc import Callable, Sequence

import numpy as np
from sklearn import metrics as skm


# ---------------------------------------------------------------------------
# Multiclass classification
# ---------------------------------------------------------------------------
def classification(y_true: Sequence, y_pred: Sequence, labels: Sequence) -> dict:
    report = skm.classification_report(y_true, y_pred, labels=list(labels), output_dict=True, zero_division=0)
    return {
        "accuracy": skm.accuracy_score(y_true, y_pred),
        "macro_f1": skm.f1_score(y_true, y_pred, labels=list(labels), average="macro", zero_division=0),
        "weighted_f1": skm.f1_score(y_true, y_pred, labels=list(labels), average="weighted", zero_division=0),
        "macro_precision": report["macro avg"]["precision"],
        "macro_recall": report["macro avg"]["recall"],
        "per_class": {
            str(lbl): {k: report[str(lbl)][k] for k in ("precision", "recall", "f1-score", "support")}
            for lbl in labels
            if str(lbl) in report
        },
        "confusion_matrix": skm.confusion_matrix(y_true, y_pred, labels=list(labels)).tolist(),
        "labels": [str(lbl) for lbl in labels],
    }


def top_k_accuracy(y_true: Sequence, proba: np.ndarray, classes: Sequence, k: int) -> float:
    classes = np.asarray(classes)
    top = np.argsort(-proba, axis=1)[:, :k]
    idx = {c: i for i, c in enumerate(classes)}
    truth = np.array([idx.get(y, -1) for y in y_true])
    return float(np.mean([t in row for t, row in zip(truth, top, strict=True)]))


# ---------------------------------------------------------------------------
# Binary classification (imbalanced)
# ---------------------------------------------------------------------------
def binary(y_true: np.ndarray, score: np.ndarray, threshold: float = 0.5, fpr_targets=(0.05, 0.10, 0.20)) -> dict:
    y_true = np.asarray(y_true).astype(int)
    pred = (score >= threshold).astype(int)
    fpr, tpr, _ = skm.roc_curve(y_true, score)
    recall_at_fpr = {f"recall_at_fpr_{int(t * 100)}pct": float(np.interp(t, fpr, tpr)) for t in fpr_targets}
    return {
        "positive_rate": float(y_true.mean()),
        "roc_auc": skm.roc_auc_score(y_true, score),
        "pr_auc": skm.average_precision_score(y_true, score),
        "threshold": threshold,
        "precision": skm.precision_score(y_true, pred, zero_division=0),
        "recall": skm.recall_score(y_true, pred, zero_division=0),
        "f1": skm.f1_score(y_true, pred, zero_division=0),
        "accuracy": skm.accuracy_score(y_true, pred),
        "brier": skm.brier_score_loss(y_true, score),
        **recall_at_fpr,
    }


def calibration_bins(y_true: np.ndarray, score: np.ndarray, bins: int = 10) -> list[dict]:
    y_true = np.asarray(y_true).astype(int)
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (score >= lo) & (score < hi if hi < 1 else score <= hi)
        if mask.sum():
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(mask.sum()), "mean_predicted": float(score[mask].mean()),
                        "observed_rate": float(y_true[mask].mean())})
    return out


def best_f1_threshold(y_true: np.ndarray, score: np.ndarray) -> float:
    precision, recall, thresholds = skm.precision_recall_curve(y_true, score)
    f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-12)
    return float(thresholds[int(np.argmax(f1[:-1]))]) if len(thresholds) else 0.5


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------
def regression(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "mae": skm.mean_absolute_error(y_true, y_pred),
        "rmse": float(np.sqrt(skm.mean_squared_error(y_true, y_pred))),
        "r2": skm.r2_score(y_true, y_pred),
        "median_ae": skm.median_absolute_error(y_true, y_pred),
    }


# ---------------------------------------------------------------------------
# Ranking / retrieval
# ---------------------------------------------------------------------------
def ranking(ranked_ids: list[list[str]], relevant: list[set[str]], ks=(1, 3, 5, 10, 20)) -> dict:
    out = {}
    for k in ks:
        out[f"recall_at_{k}"] = float(np.mean([len(set(r[:k]) & rel) / len(rel) for r, rel in zip(ranked_ids, relevant, strict=True)]))
        out[f"hit_rate_at_{k}"] = float(np.mean([bool(set(r[:k]) & rel) for r, rel in zip(ranked_ids, relevant, strict=True)]))
    rr = []
    for r, rel in zip(ranked_ids, relevant, strict=True):
        rank = next((i + 1 for i, d in enumerate(r) if d in rel), None)
        rr.append(1.0 / rank if rank else 0.0)
    out["mrr"] = float(np.mean(rr))
    out["mrr_at_10"] = float(np.mean([x if x >= 0.1 else 0.0 for x in rr]))
    return out


# ---------------------------------------------------------------------------
# Latency & uncertainty
# ---------------------------------------------------------------------------
def latency(predict_one: Callable[[object], object], items: Sequence, warmup: int = 5) -> dict:
    """Single-item (online) latency: what one API request pays."""
    for it in items[:warmup]:
        predict_one(it)
    samples = []
    for it in items:
        t = time.perf_counter()
        predict_one(it)
        samples.append((time.perf_counter() - t) * 1000)
    arr = np.array(samples)
    return {"n": len(arr), "p50_ms": float(np.percentile(arr, 50)), "p95_ms": float(np.percentile(arr, 95)),
            "p99_ms": float(np.percentile(arr, 99)), "mean_ms": float(arr.mean())}


def bootstrap_ci(metric: Callable[[np.ndarray, np.ndarray], float], y_true, y_pred, n: int = 1000, seed: int = 0,
                 alpha: float = 0.05) -> dict:
    """Percentile bootstrap confidence interval over test examples."""
    rng = np.random.default_rng(seed)
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    stats = []
    for _ in range(n):
        idx = rng.integers(0, len(y_true), len(y_true))
        stats.append(metric(y_true[idx], y_pred[idx]))
    lo, hi = np.percentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"low": float(lo), "high": float(hi), "n_bootstrap": n}

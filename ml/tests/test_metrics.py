"""The metric helpers every report depends on, checked against hand-computed values."""

import numpy as np
import pytest

from nexadesk_ml import metrics


def test_ranking_recall_and_mrr():
    ranked = [["a", "b", "c"], ["x", "y", "z"], ["p", "q", "r"]]
    relevant = [{"b"}, {"z", "y"}, {"nope"}]
    out = metrics.ranking(ranked, relevant, ks=(1, 3))
    assert out["recall_at_1"] == pytest.approx(0.0)
    assert out["recall_at_3"] == pytest.approx((1 + 1 + 0) / 3)
    assert out["hit_rate_at_3"] == pytest.approx(2 / 3)
    assert out["mrr"] == pytest.approx((1 / 2 + 1 / 2 + 0) / 3)


def test_top_k_accuracy():
    proba = np.array([[0.6, 0.3, 0.1], [0.2, 0.3, 0.5]])
    classes = ["a", "b", "c"]
    assert metrics.top_k_accuracy(["b", "a"], proba, classes, 1) == 0.0
    assert metrics.top_k_accuracy(["b", "a"], proba, classes, 2) == 0.5


def test_binary_metrics_on_perfect_and_constant_scores():
    y = np.array([0, 0, 1, 1])
    perfect = metrics.binary(y, np.array([0.1, 0.2, 0.8, 0.9]))
    assert perfect["roc_auc"] == 1.0 and perfect["pr_auc"] == 1.0 and perfect["f1"] == 1.0
    assert perfect["recall_at_fpr_10pct"] == 1.0
    constant = metrics.binary(y, np.array([0.5, 0.5, 0.5, 0.5]))
    assert constant["roc_auc"] == 0.5


def test_regression_metrics():
    out = metrics.regression(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 5.0]))
    assert out["mae"] == pytest.approx(2 / 3)
    assert out["median_ae"] == 0.0
    assert out["rmse"] == pytest.approx(np.sqrt(4 / 3))


def test_classification_includes_confusion_matrix_in_label_order():
    out = metrics.classification(["a", "b", "b"], ["a", "a", "b"], labels=["a", "b"])
    assert out["confusion_matrix"] == [[1, 0], [1, 1]]
    assert out["accuracy"] == pytest.approx(2 / 3)


def test_bootstrap_ci_brackets_the_point_estimate():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 500)
    p = np.where(rng.random(500) < 0.8, y, 1 - y)
    ci = metrics.bootstrap_ci(lambda a, b: float((a == b).mean()), y, p, n=300)
    point = float((y == p).mean())
    assert ci["low"] < point < ci["high"]


def test_calibration_bins_cover_all_scores():
    y = np.array([0, 1, 1, 0, 1])
    s = np.array([0.05, 0.95, 0.55, 0.45, 1.0])
    bins = metrics.calibration_bins(y, s)
    assert sum(b["n"] for b in bins) == len(y)

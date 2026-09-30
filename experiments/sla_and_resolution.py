"""
P4.4 SLA-breach prediction and P4.5 resolution-time prediction.

    python experiments/sla_and_resolution.py

Data: UCI incident log (real, anonymized ServiceNow, CC BY 4.0); time-based
70/15/15 split. Prediction point: right after the incident is opened and first
assigned — so the initial assignment group is a legitimate feature here.
Excluded as leakage: anything only known later (reassignment/reopen counts,
number of updates, resolved/closed timestamps, the final group).

Leakage-safe engineered features:
* group_load_24h — incidents opened in the same group in the previous 24 h;
* group_hist_breach_rate / group_hist_median_hours — computed from the
  TRAINING period only and joined onto val/test.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))

import lightgbm as lgb  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LinearRegression, LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

from nexadesk_ml import metrics, tracking  # noqa: E402
from nexadesk_ml.paths import PROCESSED, REPORTS  # noqa: E402

DATA = PROCESSED / "incidents.parquet"
CAT = ["open_category", "open_subcategory", "open_u_symptom", "open_location", "open_contact_type",
       "open_assignment_group", "open_knowledge", "open_u_priority_confirmation"]
NUM = ["priority_num", "impact_num", "urgency_num", "open_hour", "open_dow", "group_load_24h",
       "group_hist_breach_rate", "group_hist_median_hours", "group_hist_volume"]


def load():
    df = pd.read_parquet(DATA)
    for c in CAT:
        df[c] = df[c].fillna("missing").astype(str)
    tr = df[df["split"] == "train"]
    hist = tr.groupby("open_assignment_group").agg(
        group_hist_breach_rate=("breached_sla", "mean"),
        group_hist_median_hours=("resolution_hours", "median"),
        group_hist_volume=("incident_id", "count"),
    )
    df = df.join(hist, on="open_assignment_group")
    df["group_hist_breach_rate"] = df["group_hist_breach_rate"].fillna(tr["breached_sla"].mean())
    df["group_hist_median_hours"] = df["group_hist_median_hours"].fillna(tr["resolution_hours"].median())
    df["group_hist_volume"] = df["group_hist_volume"].fillna(0)
    return df


def lgb_frame(d, ref):
    X = d[CAT + NUM].copy()
    for c in CAT:
        X[c] = pd.Categorical(X[c], categories=sorted(ref[c].unique()))
    return X


def linear_pre():
    return ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=10), CAT),
                              ("num", StandardScaler(), NUM)])


def sla(df, run, lines):
    tr, va, te = (df[df["split"] == s] for s in ("train", "val", "test"))
    y_tr, y_va, y_te = (d["breached_sla"].astype(int).to_numpy() for d in (tr, va, te))
    run.log_params(sla_positive_rate={"train": float(y_tr.mean()), "val": float(y_va.mean()), "test": float(y_te.mean())})

    results = {}
    # Naive baseline: always predict the majority outcome — shows why accuracy misleads.
    majority = int(y_tr.mean() >= 0.5)
    results["majority_class"] = {"accuracy": float((y_te == majority).mean()), "recall": float(majority == 1),
                                 "note": "Predicts the majority class for every ticket"}

    lr = make_pipeline(linear_pre(), LogisticRegression(C=1.0, max_iter=3000, class_weight="balanced")).fit(tr, y_tr)
    s_va, s_te = lr.predict_proba(va)[:, 1], lr.predict_proba(te)[:, 1]
    thr = metrics.best_f1_threshold(y_va, s_va)
    results["logistic_regression"] = {**metrics.binary(y_te, s_te, thr), "calibration": metrics.calibration_bins(y_te, s_te)}

    pos_weight = (1 - y_tr.mean()) / y_tr.mean()
    gbm = lgb.LGBMClassifier(n_estimators=1000, learning_rate=0.03, num_leaves=31, min_child_samples=30,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, scale_pos_weight=pos_weight,
                             verbose=-1, random_state=42)
    gbm.fit(lgb_frame(tr, tr), y_tr, eval_set=[(lgb_frame(va, tr), y_va)], eval_metric="average_precision",
            callbacks=[lgb.early_stopping(50, verbose=False)])
    s_va, s_te = gbm.predict_proba(lgb_frame(va, tr))[:, 1], gbm.predict_proba(lgb_frame(te, tr))[:, 1]
    s_va_gbm, s_te_gbm = s_va, s_te
    thr = metrics.best_f1_threshold(y_va, s_va)
    X1 = lgb_frame(te, tr)
    lat = metrics.latency(lambda i: gbm.predict_proba(X1.iloc[[i]]), list(range(300)))
    results["lightgbm"] = {**metrics.binary(y_te, s_te, thr), "calibration": metrics.calibration_bins(y_te, s_te),
                           "best_iteration": int(gbm.best_iteration_ or 0), "latency_single": lat,
                           "pr_auc_ci95": metrics.bootstrap_ci(average_precision_score, y_te, s_te, n=500),
                           "feature_importance_gain": dict(sorted(zip(CAT + NUM, gbm.booster_.feature_importance("gain").round(1).tolist(), strict=True), key=lambda kv: -kv[1]))}
    # Prior shift: the breach rate fell from ~42% (train period) to ~23% (later
    # periods). Recalibrate the LightGBM scores on the most recent labelled
    # period (validation) with isotonic regression; evaluate on test.
    iso = IsotonicRegression(out_of_bounds="clip").fit(s_va_gbm, y_va)
    s_te_cal = iso.predict(s_te_gbm)
    thr_cal = metrics.best_f1_threshold(y_va, iso.predict(s_va_gbm))
    results["lightgbm_recalibrated"] = {**metrics.binary(y_te, s_te_cal, thr_cal),
                                        "calibration": metrics.calibration_bins(y_te, s_te_cal),
                                        "note": "isotonic regression fitted on the validation period"}
    results["error_analysis"] = sla_slices(te, y_te, s_te_cal, thr_cal)
    run.log_metrics(sla_breach=results)

    fig, ax = plt.subplots(figsize=(5, 5))
    for name in ("logistic_regression", "lightgbm", "lightgbm_recalibrated"):
        cal = results[name]["calibration"]
        ax.plot([c["mean_predicted"] for c in cal], [c["observed_rate"] for c in cal], marker="o", label=name.replace("_", " "))
    ax.plot([0, 1], [0, 1], color="#999", linewidth=1)
    ax.set_xlabel("Predicted breach probability")
    ax.set_ylabel("Observed breach rate")
    ax.set_title("SLA-breach calibration (test)")
    ax.legend()
    fig.tight_layout()
    path = REPORTS / "sla" / "calibration.png"
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path, dpi=120)
    run.add_artifact(path)

    lines += ["## P4.4 SLA-breach prediction", "",
              f"Positive class = SLA breached. Test breach rate {y_te.mean() * 100:.1f}% (n={len(te)}). "
              "Threshold chosen on validation (max F1). A classifier that always predicts the majority outcome "
              f"scores accuracy {results['majority_class']['accuracy']:.3f} while catching "
              f"{'every' if majority == 1 else 'no'} breach — why ROC-AUC, PR-AUC and recall at a fixed false-positive rate are reported.",
              "", "| Model | ROC-AUC | PR-AUC | Precision | Recall | F1 | Recall @ 10% FPR | Brier |", "|---|---|---|---|---|---|---|---|"]
    labels = {"logistic_regression": "Logistic regression", "lightgbm": "LightGBM",
              "lightgbm_recalibrated": "LightGBM + isotonic recalibration (val period)"}
    for name, label in labels.items():
        r = results[name]
        lines.append(f"| {label} | {r['roc_auc']:.3f} | {r['pr_auc']:.3f} | {r['precision']:.3f} | "
                     f"{r['recall']:.3f} | {r['f1']:.3f} | {r['recall_at_fpr_10pct']:.3f} | {r['brier']:.3f} |")
    lines += ["", f"Base-rate drift: the breach rate was {y_tr.mean() * 100:.1f}% in the training period and "
              f"{y_va.mean() * 100:.1f}% / {y_te.mean() * 100:.1f}% in the validation / test periods. Models trained on "
              f"the past over-predict breaches: uncalibrated Brier {results['lightgbm']['brier']:.3f} is worse than a constant "
              f"forecast at the test base rate ({y_te.mean() * (1 - y_te.mean()):.3f}). Isotonic recalibration on the most "
              f"recent labelled period brings it to {results['lightgbm_recalibrated']['brier']:.3f}; ROC-AUC is essentially "
              "unchanged (recalibration does not change the ranking beyond ties). Calibration plot: "
              "`reports/sla/calibration.png`.", ""]
    ea = results["error_analysis"]
    lines += ["### Where the recalibrated LightGBM model errs (test period)", "",
              "| Priority | n | Breach rate | ROC-AUC | Recall | False-positive rate |", "|---|---|---|---|---|---|"]
    for r in ea["by_priority"]:
        lines.append(f"| {r['priority']} | {r['n']} | {r['breach_rate']:.3f} | "
                     f"{'—' if r['roc_auc'] is None else format(r['roc_auc'], '.3f')} | {r['recall']:.3f} | {r['fpr']:.3f} |")
    lines += ["", "Assignment groups with the most missed breaches (false negatives): " + ", ".join(
        f"{g['group']} ({g['missed']} of {g['breaches']})" for g in ea["missed_by_group"]) + ".", ""]


def resolution(df, run, lines):
    d = df[df["resolution_hours"].between(0, 24 * 90)].copy()
    tr, va, te = (d[d["split"] == s] for s in ("train", "val", "test"))
    y_tr, y_va, y_te = (x["resolution_hours"].to_numpy() for x in (tr, va, te))
    results = {}

    results["global_median"] = metrics.regression(y_te, np.full_like(y_te, np.median(y_tr)))
    by_pri = tr.groupby("priority_num")["resolution_hours"].median()
    results["median_by_priority"] = metrics.regression(y_te, te["priority_num"].map(by_pri).fillna(np.median(y_tr)).to_numpy())

    lin = make_pipeline(linear_pre(), LinearRegression()).fit(tr, np.log1p(y_tr))
    results["linear_log_target"] = metrics.regression(y_te, np.expm1(lin.predict(te)).clip(0))

    gbm = lgb.LGBMRegressor(n_estimators=2000, learning_rate=0.03, num_leaves=31, min_child_samples=30, subsample=0.8,
                            subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=42)
    gbm.fit(lgb_frame(tr, tr), np.log1p(y_tr), eval_set=[(lgb_frame(va, tr), np.log1p(y_va))],
            callbacks=[lgb.early_stopping(50, verbose=False)])
    pred = np.expm1(gbm.predict(lgb_frame(te, tr))).clip(0)
    results["lightgbm_log_target"] = {**metrics.regression(y_te, pred), "best_iteration": int(gbm.best_iteration_ or 0)}
    # Median-optimal variant (MAE objective on the raw target).
    q = lgb.LGBMRegressor(objective="quantile", alpha=0.5, n_estimators=2000, learning_rate=0.03, num_leaves=31,
                          min_child_samples=30, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=42)
    q.fit(lgb_frame(tr, tr), y_tr, eval_set=[(lgb_frame(va, tr), y_va)], callbacks=[lgb.early_stopping(50, verbose=False)])
    q_pred = q.predict(lgb_frame(te, tr)).clip(0)
    results["lightgbm_median_objective"] = metrics.regression(y_te, q_pred)
    results["error_analysis"] = resolution_slices(y_te, q_pred, np.full_like(y_te, np.median(y_tr)))
    run.log_metrics(resolution_time=results)
    run.log_params(resolution_rows={"train": len(tr), "val": len(va), "test": len(te)},
                   resolution_target_summary_hours={"train_median": float(np.median(y_tr)), "test_median": float(np.median(y_te)),
                                                    "test_p90": float(np.percentile(y_te, 90))})

    lines += ["## P4.5 Resolution-time prediction", "",
              f"Target: hours from opened to resolved (incidents resolved within 90 days). Test n={len(te)}, median "
              f"{np.median(y_te):.1f} h, p90 {np.percentile(y_te, 90):.1f} h — heavy-tailed, so models are trained on "
              "log(1+hours) (or with a median objective) and scored in hours.", "",
              "| Model | MAE (h) | Median AE (h) | RMSE (h) | R² |", "|---|---|---|---|---|"]
    names = {"global_median": "Global median (baseline)", "median_by_priority": "Median by priority (rule)",
             "linear_log_target": "Linear regression (log target)", "lightgbm_log_target": "LightGBM (log target)",
             "lightgbm_median_objective": "LightGBM (median objective)"}
    for key, label in names.items():
        r = results[key]
        lines.append(f"| {label} | {r['mae']:.1f} | {r['median_ae']:.1f} | {r['rmse']:.1f} | {r['r2']:.3f} |")
    ea = results["error_analysis"]
    lines += ["", "### Where resolution-time errors come from (LightGBM median objective vs global median)", "",
              "| Actual duration | n | Median AE model (h) | Median AE baseline (h) | Share of model's total absolute error |",
              "|---|---|---|---|---|"]
    for r in ea:
        lines.append(f"| {r['bucket']} | {r['n']} | {r['model_median_ae']:.1f} | {r['baseline_median_ae']:.1f} | "
                     f"{r['share_of_total_abs_error']:.1%} |")
    lines.append("")


def sla_slices(te, y, score, thr):
    pred = score >= thr
    by_priority = []
    for pri, idx in te.reset_index(drop=True).groupby("priority_num").indices.items():
        yy, ss, pp = y[idx], score[idx], pred[idx]
        by_priority.append({
            "priority": int(pri), "n": int(len(idx)), "breach_rate": float(yy.mean()),
            "roc_auc": float(roc_auc_score(yy, ss)) if 0 < yy.sum() < len(yy) else None,
            "recall": float(pp[yy == 1].mean()) if yy.sum() else 0.0,
            "fpr": float(pp[yy == 0].mean()) if (yy == 0).any() else 0.0,
        })
    frame = pd.DataFrame({"group": te["open_assignment_group"].to_numpy(), "y": y, "pred": pred})
    miss = (frame[frame["y"] == 1].assign(missed=lambda f: ~f["pred"]).groupby("group")
            .agg(breaches=("y", "size"), missed=("missed", "sum")).sort_values("missed", ascending=False).head(5))
    return {"by_priority": by_priority, "threshold": float(thr),
            "missed_by_group": [{"group": g, "breaches": int(r.breaches), "missed": int(r.missed)} for g, r in miss.iterrows()]}


def resolution_slices(y, pred, base):
    buckets = [("< 1 h", 0, 1), ("1–8 h", 1, 8), ("8–72 h", 8, 72), ("3–30 days", 72, 720), ("> 30 days", 720, np.inf)]
    total = np.abs(pred - y).sum()
    out = []
    for name, lo, hi in buckets:
        m = (y >= lo) & (y < hi)
        if m.any():
            out.append({"bucket": name, "n": int(m.sum()), "model_median_ae": float(np.median(np.abs(pred[m] - y[m]))),
                        "baseline_median_ae": float(np.median(np.abs(base[m] - y[m]))),
                        "share_of_total_abs_error": float(np.abs(pred[m] - y[m]).sum() / total)})
    return out


def main():
    df = load()
    lines = ["# P4.4 / P4.5 — SLA breach and resolution time (UCI ServiceNow incident log, real data)", "",
             "Time-based split (train on the past, test on the most recent 15%). Provenance: "
             "`reports/sla/p4_sla_and_resolution.json`.", ""]
    with tracking.run("sla", "p4_sla_and_resolution", [DATA]) as run:
        run.log_params(categorical=CAT, numeric=NUM, split="time-based 70/15/15")
        sla(df, run, lines)
        resolution(df, run, lines)
    (REPORTS / "sla" / "summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

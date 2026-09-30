"""
P4.2 — Routing: predict the team (assignment group) that resolves an incident,
from what is known when it is opened.

    python experiments/routing.py

Data: UCI "Incident management process enriched event log" (real, anonymized
ServiceNow data, CC BY 4.0), aggregated to one row per incident, time-based
70/15/15 split (train on the past, test on the future).

Target: final_assignment_group (the group holding the incident when it closed).
Not used as a feature: the initial assignment group — that is the routing
decision being predicted. Its accuracy is reported instead as the measured
*human dispatcher* baseline (open group == final group).

Compared: category→most-frequent-group table (how NexaDesk's rules engine
routes), logistic regression, LightGBM. Selective prediction: when confidence
is below a threshold the ticket goes to human triage — reported as coverage vs
accuracy.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))

import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.preprocessing import OneHotEncoder  # noqa: E402

from nexadesk_ml import metrics, tracking  # noqa: E402
from nexadesk_ml.paths import PROCESSED, REPORTS  # noqa: E402

DATA = PROCESSED / "incidents.parquet"
CAT_FEATURES = ["open_category", "open_subcategory", "open_u_symptom", "open_location", "open_contact_type",
                "open_impact", "open_urgency", "open_priority", "open_knowledge", "open_opened_by"]
NUM_FEATURES = ["open_hour", "open_dow"]
MIN_GROUP_SUPPORT = 20


def load():
    df = pd.read_parquet(DATA)
    df = df.dropna(subset=["final_assignment_group"]).copy()
    # Groups too rare to learn are folded into "Other" (counted as the model's
    # responsibility to route to a human dispatcher).
    counts = df[df["split"] == "train"]["final_assignment_group"].value_counts()
    keep = set(counts[counts >= MIN_GROUP_SUPPORT].index)
    df["target"] = df["final_assignment_group"].where(df["final_assignment_group"].isin(keep), "Other")
    for c in CAT_FEATURES:
        df[c] = df[c].fillna("missing").astype(str)
    return df


def coverage_curve(y, proba, classes, pred, human_correct):
    """Auto-route only tickets whose top probability clears a threshold. The
    human dispatcher's accuracy on the *same* subset is the fair comparison:
    confident tickets may simply be easier for everyone."""
    conf = proba.max(axis=1)
    out = {}
    for thr in (0.3, 0.5, 0.7, 0.9):
        keep = conf >= thr
        out[f"conf_{thr}"] = {
            "coverage": float(keep.mean()),
            "accuracy_on_covered": float((pred[keep] == y[keep]).mean()) if keep.any() else None,
            "human_accuracy_on_same_subset": float(human_correct[keep].mean()) if keep.any() else None,
            "routed_to_human_triage": float(1 - keep.mean()),
        }
    return out


def routing_errors(y, pred, human_correct):
    wrong = pred != y
    pairs = Counter(zip(y[wrong], pred[wrong], strict=True)).most_common(8)
    groups = []
    for g in np.unique(y):
        m = y == g
        if m.sum() >= 30:
            groups.append({"group": str(g), "n": int(m.sum()), "recall": float((pred[m] == g).mean())})
    return {"n": int(len(y)), "errors": int(wrong.sum()),
            "errors_where_human_also_wrong": int((wrong & ~human_correct).sum()),
            "top_confusions": [{"true": str(a), "pred": str(b), "count": int(c)} for (a, b), c in pairs],
            "weakest_groups": sorted(groups, key=lambda g: g["recall"])[:5]}


def main():
    df = load()
    tr, va, te = (df[df["split"] == s] for s in ("train", "val", "test"))
    classes = np.array(sorted(tr["target"].unique()))
    y_te = te["target"].to_numpy()
    rows = []

    with tracking.run("routing", "p4_routing_uci", [DATA]) as run:
        run.log_params(features=CAT_FEATURES + NUM_FEATURES, n_classes=len(classes), min_group_support=MIN_GROUP_SUPPORT,
                       split_sizes={"train": len(tr), "val": len(va), "test": len(te)}, split="time-based")

        # Measured human baseline: the dispatcher's first group vs the resolving group.
        human = (te["open_assignment_group"].fillna("?") == te["final_assignment_group"]).to_numpy()
        reassigned = (te["reassignment_count"] > 0).to_numpy()
        run.log_metrics(human_dispatcher={
            "first_assignment_correct": float(human.mean()),
            "wrong_routing_rate": float(1 - human.mean()),
            "incidents_with_any_reassignment": float(reassigned.mean()),
            "note": "Real ServiceNow data: share of test incidents whose initial assignment group was the group that resolved it.",
        })
        rows.append(("Human dispatcher (first assignment, measured)", float(human.mean()), None, None))

        # Rule table: most frequent resolving group per category (like NexaDesk's category->team routing).
        table = tr.groupby("open_category")["target"].agg(lambda s: s.value_counts().index[0])
        fallback = tr["target"].value_counts().index[0]
        pred_rule = te["open_category"].map(table).fillna(fallback).to_numpy()
        r = metrics.classification(y_te, pred_rule, classes)
        run.log_metrics(category_table={"top1_accuracy": r["accuracy"], "macro_f1": r["macro_f1"], "wrong_routing_rate": 1 - r["accuracy"]})
        rows.append(("Category → group table (rules)", r["accuracy"], None, None))

        enc = OneHotEncoder(handle_unknown="ignore", min_frequency=5)
        X_tr = enc.fit_transform(tr[CAT_FEATURES])
        X_va, X_te = enc.transform(va[CAT_FEATURES]), enc.transform(te[CAT_FEATURES])
        best = None
        for C in (0.1, 0.3, 1.0, 3.0):
            m = LogisticRegression(C=C, max_iter=3000).fit(X_tr, tr["target"])
            acc = (m.predict(X_va) == va["target"]).mean()
            if best is None or acc > best[0]:
                best = (acc, C, m)
        _, C, lr = best
        proba = lr.predict_proba(X_te)
        pred = lr.classes_[proba.argmax(axis=1)]
        lat = metrics.latency(lambda i: lr.predict_proba(X_te[i]), list(range(300)))
        res = {"C": C, "top1_accuracy": float((pred == y_te).mean()), "top3_accuracy": metrics.top_k_accuracy(y_te, proba, lr.classes_, 3),
               "wrong_routing_rate": float((pred != y_te).mean()), "macro_f1": metrics.classification(y_te, pred, classes)["macro_f1"],
               "selective": coverage_curve(y_te, proba, lr.classes_, pred, human), "latency_single": lat}
        res["error_analysis"] = routing_errors(y_te, pred, human)
        run.log_metrics(logreg=res)
        selective_lr, errors_lr = res["selective"], res["error_analysis"]
        rows.append(("One-hot + Logistic regression", res["top1_accuracy"], res["top3_accuracy"], lat["p50_ms"]))

        def lgb_frame(d):
            X = d[CAT_FEATURES + NUM_FEATURES].copy()
            for c in CAT_FEATURES:
                X[c] = pd.Categorical(X[c], categories=sorted(tr[c].unique()))
            return X

        label_index = {c: i for i, c in enumerate(classes)}
        gbm = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.05, num_leaves=63, min_child_samples=20,
                                 subsample=0.8, subsample_freq=1, colsample_bytree=0.8, max_cat_to_onehot=8,
                                 verbose=-1, random_state=42)
        gbm.fit(lgb_frame(tr), tr["target"].map(label_index), eval_set=[(lgb_frame(va), va["target"].map(label_index))],
                callbacks=[lgb.early_stopping(30, verbose=False)])
        Xte = lgb_frame(te)
        proba = gbm.predict_proba(Xte)
        pred = classes[proba.argmax(axis=1)]
        lat = metrics.latency(lambda i: gbm.predict_proba(Xte.iloc[[i]]), list(range(300)))
        res = {"best_iteration": int(gbm.best_iteration_ or 0), "top1_accuracy": float((pred == y_te).mean()),
               "top3_accuracy": metrics.top_k_accuracy(y_te, proba, classes, 3), "wrong_routing_rate": float((pred != y_te).mean()),
               "macro_f1": metrics.classification(y_te, pred, classes)["macro_f1"],
               "selective": coverage_curve(y_te, proba, classes, pred, human), "latency_single": lat,
               "top1_ci95": metrics.bootstrap_ci(lambda a, b: float((a == b).mean()), y_te, pred)}
        run.log_metrics(lightgbm=res)
        rows.append(("LightGBM (categorical)", res["top1_accuracy"], res["top3_accuracy"], lat["p50_ms"]))

    lines = [
        "# P4.2 Routing — results (UCI ServiceNow incident log, real data)",
        "",
        f"Target: the assignment group that resolved the incident ({len(classes)} classes incl. 'Other' for groups with "
        f"<{MIN_GROUP_SUPPORT} training incidents). Time-based split; test = the most recent 15% of incidents "
        f"(n={len(te)}). Provenance: `reports/routing/p4_routing_uci.json`.",
        "",
        "| Router | Top-1 accuracy | Top-3 accuracy | p50 latency |",
        "|---|---|---|---|",
    ]
    for name, top1, top3, p50 in rows:
        lines.append(f"| {name} | {top1:.3f} | {'' if top3 is None else f'{top3:.3f}'} | {'' if p50 is None else f'{p50:.2f} ms'} |")
    lines += ["", "## Selective routing (logistic regression)", "",
              "Auto-route only when the model's top probability clears a threshold; everything else goes to human "
              "triage. The human column is the dispatcher's first-assignment accuracy on the *same* tickets.", "",
              "| Confidence ≥ | Auto-routed share | Model accuracy on them | Human accuracy on the same tickets |",
              "|---|---|---|---|"]
    for key, v in selective_lr.items():
        lines.append(f"| {key.split('_')[1]} | {v['coverage']:.3f} | {v['accuracy_on_covered']:.3f} | "
                     f"{v['human_accuracy_on_same_subset']:.3f} |")
    lines += ["", "## Where the logistic-regression router errs (test)", "",
              f"{errors_lr['errors']} wrong routes of {errors_lr['n']}; the human dispatcher was also wrong on "
              f"{errors_lr['errors_where_human_also_wrong']} of them. Most frequent confusions (true → predicted):", "",
              "| True group | Predicted group | Count |", "|---|---|---|"]
    for c in errors_lr["top_confusions"]:
        lines.append(f"| {c['true']} | {c['pred']} | {c['count']} |")
    lines += ["", "Lowest-recall groups with ≥ 30 test incidents: " + ", ".join(
        f"{g['group']} ({g['recall']:.2f} of {g['n']})" for g in errors_lr["weakest_groups"]) + ".", ""]
    (REPORTS / "routing" / "summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

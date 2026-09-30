"""
P4.6 — Error analysis across the baseline experiments.

    python experiments/error_analysis.py

Reads the JSON results written by the P4 experiments (no retraining) and
writes reports/error_analysis.md: the weakest classes and most frequent
confusions of the best text classifier, how much the nearest-neighbour methods
depend on near-duplicate tickets, where routing / SLA / resolution-time models
fail, and the duplicate-threshold trade-off. Every figure is copied from a
results file named next to it.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml"))

from nexadesk_ml.paths import REPORTS  # noqa: E402


def load(rel):
    path = REPORTS / rel
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def top_confusions(cm, labels, n=5):
    pairs = []
    for i, row in enumerate(cm):
        for j, v in enumerate(row):
            if i != j and v:
                pairs.append((v, labels[i], labels[j]))
    return sorted(pairs, reverse=True)[:n]


def classification_section(lines):
    d = load("classification/p4_text_classification.json")
    if not d:
        return
    m = d["metrics"]
    lines += ["## Ticket classification (P4.1, TF-IDF + LinearSVC — best model)", "",
              "Source: `reports/classification/p4_text_classification.json`.", ""]
    for task in ("queue", "type", "priority"):
        r = m.get(f"{task}.tfidf_linearsvc")
        if not r:
            continue
        test = r.get("test", r)
        per = test["per_class"]
        weakest = sorted(per.items(), key=lambda kv: kv[1]["f1-score"])[:3]
        lines.append(f"**{task}** — macro-F1 {test['macro_f1']:.3f}. Weakest classes: " + ", ".join(
            f"{k} (F1 {v['f1-score']:.2f}, n={int(v['support'])})" for k, v in weakest) + ".")
        conf = top_confusions(test["confusion_matrix"], test["labels"])
        lines.append("Most frequent confusions (true → predicted): " + "; ".join(
            f"{a} → {b} ({v})" for v, a, b in conf) + ".")
        lines.append("")
    lc = m.get("leakage_check")
    if lc:
        share = lc["share_test_with_near_duplicate_in_train_cos_ge_0.8"]
        lines += [f"Near-duplicate exposure: {share * 100:.1f}% of test tickets have a training ticket at TF-IDF "
                  f"cosine ≥ 0.8 (median max cosine {lc['test_max_cosine_to_train_p50']:.2f}). LinearSVC macro-F1 on the "
                  "novel subset is reported next to each model in `reports/classification/summary.md`.", ""]


def production_section(lines):
    d = load("classification/p4_production_classifier.json")
    if not d:
        return
    lines += ["## Per-organization learners (P4.1b): full test set vs genuinely new tickets", "",
              "Source: `reports/classification/p4_production_classifier.json`. 'Novel' = test tickets with no training "
              f"ticket at TF-IDF cosine ≥ 0.8 ({d['params'].get('novel_test_tickets', '?')} tickets).", "",
              "| Task | Method | Macro-F1 (all test) | Macro-F1 (novel) | Drop |", "|---|---|---|---|---|"]
    for key, v in d["metrics"].items():
        method, task = key.rsplit(".", 1)
        full = v["test_full_history"]
        nov = full.get("novel", {}).get("macro_f1")
        if nov is None:
            continue
        lines.append(f"| {task} | {method} | {full['macro_f1']:.3f} | {nov:.3f} | {full['macro_f1'] - nov:+.3f} |")
    lines.append("")


def routing_section(lines):
    d = load("routing/p4_routing_uci.json")
    ea = d and d["metrics"].get("logreg", {}).get("error_analysis")
    if not ea:
        return
    lines += ["## Routing (P4.2, UCI incident log, logistic regression)", "",
              "Source: `reports/routing/p4_routing_uci.json`.", "",
              f"{ea['errors']} of {ea['n']} test incidents routed to the wrong group; the human dispatcher's first "
              f"assignment was also wrong on {ea['errors_where_human_also_wrong']} of those — many errors are cases "
              "that are hard for people too.", "",
              "Most frequent confusions: " + "; ".join(f"{c['true']} → {c['pred']} ({c['count']})"
                                                       for c in ea["top_confusions"][:5]) + ".",
              "Lowest-recall groups (≥ 30 incidents): " + ", ".join(
                  f"{g['group']} ({g['recall']:.2f}, n={g['n']})" for g in ea["weakest_groups"]) + ".", ""]


def sla_section(lines):
    d = load("sla/p4_sla_and_resolution.json")
    if not d:
        return
    ea = d["metrics"]["sla_breach"].get("error_analysis")
    if ea:
        lines += ["## SLA breach (P4.4, recalibrated LightGBM)", "", "Source: `reports/sla/p4_sla_and_resolution.json`.",
                  "", "| Priority | n | Breach rate | ROC-AUC | Recall | FPR |", "|---|---|---|---|---|---|"]
        for r in ea["by_priority"]:
            auc = "—" if r["roc_auc"] is None else f"{r['roc_auc']:.3f}"
            lines.append(f"| {r['priority']} | {r['n']} | {r['breach_rate']:.3f} | {auc} | {r['recall']:.3f} | "
                         f"{r['fpr']:.3f} |")
        lines += ["", "Groups with the most missed breaches: " + ", ".join(
            f"{g['group']} ({g['missed']}/{g['breaches']})" for g in ea["missed_by_group"]) + ".", ""]
    rt = d["metrics"]["resolution_time"].get("error_analysis")
    if rt:
        lines += ["## Resolution time (P4.5, LightGBM median objective)", "",
                  "| Actual duration | n | Model median AE (h) | Baseline median AE (h) | Share of total abs. error |",
                  "|---|---|---|---|---|"]
        for r in rt:
            lines.append(f"| {r['bucket']} | {r['n']} | {r['model_median_ae']:.1f} | {r['baseline_median_ae']:.1f} | "
                         f"{r['share_of_total_abs_error']:.1%} |")
        lines.append("")


def duplicates_section(lines):
    d = load("duplicates/p4_duplicate_threshold.json")
    if not d:
        return
    m = d["metrics"]
    t = m["chosen_threshold"]
    pub, syn = m["public"]["test"][str(t)], m["synthetic"][str(t)]
    lines += ["## Duplicates (P4.3 / P4.3b)", "",
              "Source: `reports/duplicates/p4_duplicate_threshold.json`.", "",
              f"At the production threshold {t} (MiniLM cosine), real CQADupStack duplicates are flagged with "
              f"precision {pub['precision']:.2f} but recall only {pub['recall']:.2f}: most real duplicates are "
              "phrased too differently to clear a threshold that keeps false flags acceptable. Planted synthetic "
              f"resubmissions are caught almost perfectly (precision {syn['precision']:.2f}, recall "
              f"{syn['recall']:.2f}) — the synthetic check overstates real-world performance and is not used for "
              "claims.", ""]


def main():
    lines = ["# P4.6 — Error analysis", "",
             "Generated by `experiments/error_analysis.py` from the P4 result files; no model is retrained here.", ""]
    for section in (classification_section, production_section, routing_section, sla_section, duplicates_section):
        section(lines)
    (REPORTS / "error_analysis.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {REPORTS / 'error_analysis.md'} ({len(lines)} lines)")


if __name__ == "__main__":
    main()

# P4.4 / P4.5 — SLA breach and resolution time (UCI ServiceNow incident log, real data)

Time-based split (train on the past, test on the most recent 15%). Provenance: `reports/sla/p4_sla_and_resolution.json`.

## P4.4 SLA-breach prediction

Positive class = SLA breached. Test breach rate 23.4% (n=3738). Threshold chosen on validation (max F1). A classifier that always predicts the majority outcome scores accuracy 0.766 while catching no breach — why ROC-AUC, PR-AUC and recall at a fixed false-positive rate are reported.

| Model | ROC-AUC | PR-AUC | Precision | Recall | F1 | Recall @ 10% FPR | Brier |
|---|---|---|---|---|---|---|---|
| Logistic regression | 0.769 | 0.508 | 0.438 | 0.623 | 0.515 | 0.380 | 0.184 |
| LightGBM | 0.762 | 0.523 | 0.413 | 0.646 | 0.504 | 0.392 | 0.190 |
| LightGBM + isotonic recalibration (val period) | 0.760 | 0.494 | 0.413 | 0.646 | 0.504 | 0.378 | 0.151 |

Base-rate drift: the breach rate was 42.3% in the training period and 23.1% / 23.4% in the validation / test periods. Models trained on the past over-predict breaches: uncalibrated Brier 0.190 is worse than a constant forecast at the test base rate (0.179). Isotonic recalibration on the most recent labelled period brings it to 0.151; ROC-AUC is essentially unchanged (recalibration does not change the ranking beyond ties). Calibration plot: `reports/sla/calibration.png`.

### Where the recalibrated LightGBM model errs (test period)

| Priority | n | Breach rate | ROC-AUC | Recall | False-positive rate |
|---|---|---|---|---|---|
| 1 | 30 | 0.800 | 0.521 | 1.000 | 1.000 |
| 2 | 44 | 0.955 | 0.601 | 1.000 | 1.000 |
| 3 | 3559 | 0.227 | 0.737 | 0.620 | 0.289 |
| 4 | 105 | 0.029 | 0.569 | 0.000 | 0.020 |

Assignment groups with the most missed breaches (false negatives): Group 70 (127 of 193), Group 65 (32 of 48), Group 20 (21 of 87), Group 24 (15 of 18), Group 66 (15 of 34).

## P4.5 Resolution-time prediction

Target: hours from opened to resolved (incidents resolved within 90 days). Test n=3577, median 3.0 h, p90 291.3 h — heavy-tailed, so models are trained on log(1+hours) (or with a median objective) and scored in hours.

| Model | MAE (h) | Median AE (h) | RMSE (h) | R² |
|---|---|---|---|---|
| Global median (baseline) | 98.9 | 26.3 | 243.8 | -0.087 |
| Median by priority (rule) | 98.9 | 25.9 | 243.7 | -0.086 |
| Linear regression (log target) | 92.5 | 18.2 | 231.3 | 0.022 |
| LightGBM (log target) | 91.5 | 21.9 | 228.1 | 0.049 |
| LightGBM (median objective) | 95.1 | 30.3 | 226.6 | 0.061 |

### Where resolution-time errors come from (LightGBM median objective vs global median)

| Actual duration | n | Median AE model (h) | Median AE baseline (h) | Share of model's total absolute error |
|---|---|---|---|---|
| < 1 h | 1471 | 13.1 | 26.3 | 10.2% |
| 1–8 h | 540 | 32.8 | 23.9 | 7.6% |
| 8–72 h | 664 | 28.2 | 9.6 | 8.7% |
| 3–30 days | 804 | 128.0 | 163.7 | 42.1% |
| > 30 days | 98 | 965.0 | 1056.8 | 31.3% |

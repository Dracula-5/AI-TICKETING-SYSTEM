# Benchmark status and reproducibility

This is a consolidated index of measured experiments, not a claim that every requested benchmark
category has been completed. Public benchmark results, synthetic production-path replays and live
user outcomes are separate evidence classes. No live-user results are available.

## Reproduction and provenance

Dataset sources, licenses, hashes and split rules: [`docs/datasets.md`](../docs/datasets.md).
Commands and environment setup: [`experiments/README.md`](../experiments/README.md). Each JSON
result records provenance and configuration. Tests and reports should be regenerated in the
documented environment before using numbers in a resume or external presentation.

| Area | Evidence available | Result/report | Limit |
|---|---|---|---|
| A. ML quality | Public support text, ServiceNow incident log, CQADupStack | [`execution_plan.md`](../docs/execution_plan.md) P4; `reports/{classification,routing,duplicates,sla}/` | Different datasets represent text and operational outcomes; not customer production. |
| B. Retrieval quality | CQADupStack Unix, 533 test queries | `reports/rag/summary.md`, `p6_retrieval_cqadupstack.json` | Duplicate retrieval proxy, not labelled organization KB answer quality. No 100-question answer/faithfulness set yet. |
| C. API performance | Local load test of the production compose stack (100k synthetic tickets) | [`load/README.md`](load/README.md) | Laptop with the load generator on the same machine; not a VM result. |
| D. Database performance | 10k / 100k / 1M tickets, 12 endpoints, EXPLAIN plans | [`scale/README.md`](scale/README.md): number search 5.1 s → 27 ms at 1M; dashboard 2.2 s uncached at 1M | In-process calls on a laptop; one synthetic organization. |
| E. Load testing | 5 Locust runs at 50–500 users with before/after changes | [`load/README.md`](load/README.md): 100 users ~30 req/s p95 150 ms 0 errors; saturation ~65–70 req/s | Same-machine generator; per-IP limits reported separately; WebSockets not load-tested. |
| F. AI latency | Synthetic production-path PostgreSQL replay | `reports/pipeline/summary.md` | Local synthetic data and CPU; not service SLO or user latency. |
| G. AI cost | LLM call ledger and parameterized cost model | `docs/cost.md` | No provider configured, no paid deployment, no measured per-query external cost. |
| H. Business workflow | Instrumentation and pilot reporting exist | `docs/pilot_plan.md`, `app/services/pilot.py` | No real pilot participants or business outcome data. |

## Selected measured results

* Public text classification: TF-IDF + LinearSVC macro-F1 0.676 (queue), 0.892 (type), 0.689
  (priority); see the P4 progress entry and `reports/classification/summary.md`.
* Public incident routing: logistic regression top-1 0.655 and top-3 0.857 on a time split;
  historical first assignment top-1 was 0.673 (`reports/routing/summary.md`).
* Public duplicate retrieval: MiniLM Recall@10 0.532 on CQADupStack; conservative duplicate
  flagging precision 0.47 and recall 0.18 (`reports/duplicates/`).
* Public SLA prediction: logistic regression ROC-AUC 0.769; resolution-time LightGBM MAE 95.1 h
  vs global median 98.9 h (`reports/sla/summary.md`).
* Public retrieval benchmark: dense MiniLM Recall@10 0.532, MRR@10 0.392, nDCG@10 0.407;
  equal-weight hybrid RRF nDCG@10 0.372. CPU reranking p50 1,154 ms for 20 candidates
  (`reports/rag/summary.md`).
* Synthetic pipeline replay: 3 synthetic organizations, 2,400 replayed tickets; agent run p50
  107–159 ms (first replay) and 154–314 ms (second replay on a busier machine)
  (`reports/pipeline/summary.md`). Agent ablation: `reports/pipeline/agent_ablation.md`. These
  values are specific to a local replay and must not be presented as API performance or real usage.
* Retrieval fusion: lexical weight chosen on validation = 0 → dense-first retrieval
  (`reports/rag/fusion_weight.md`).
* Local load test: see [`load/README.md`](load/README.md) — including a connection-pool deadlock
  found under load and fixed.

## Failure analysis

See [`error_analysis.md`](error_analysis.md): category overlap, low-support routing groups,
priority confusion, SLA base-rate drift, long-duration resolution errors and low real-duplicate
recall are all documented. Duplicate performance on planted synthetic resubmissions is
explicitly excluded from real-world claims.

## Uncompleted experiment fields

Load and scale figures come from one Windows laptop running Docker Desktop and must be re-measured
on the deployment VM before capacity is promised. Business KPIs remain unpopulated until real
organizations generate eligible data. Generated answer correctness, faithfulness and citation
correctness need a labelled question set and human evaluation.

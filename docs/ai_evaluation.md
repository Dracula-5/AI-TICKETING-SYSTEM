# AI evaluation, monitoring and model promotion (P13)

How NexaDesk decides whether an AI component is good enough, notices when it stops being good
enough, and changes models without guessing.

## 1. Three layers of evidence — never mixed

| Layer | Data | Answers | Where |
|---|---|---|---|
| Offline benchmarks | Public datasets (real where available) | Which *method* is best, with confidence intervals | `experiments/*.py` → `reports/{classification,routing,duplicates,sla,rag}/` |
| Pipeline replay | Synthetic organizations replayed through the production code on PostgreSQL + pgvector | Does the *shipped pipeline* behave as the method promised (coverage, accuracy, latency, index recall)? | `experiments/pipeline_eval.py` → `reports/pipeline/` |
| Live telemetry | Real organizations' decisions | Do *people* accept it here, and is the input drifting? | `/analytics/ai-performance`, `/analytics/ai-monitoring`, `/analytics/pilot`, Prometheus |

A number from one layer is never presented as a number from another. Synthetic replays measure the
pipeline, not users; public benchmarks measure methods, not NexaDesk customers.

## 2. What is monitored continuously

Per organization, daily (`app/ai/monitoring.py`, stored in `ai_monitoring`):

| Signal | Definition | Alert when |
|---|---|---|
| Category drift | PSI of the category mix, last 7 days vs the 28 days before | > 0.25 (warn > 0.10) |
| Embedding drift | cosine distance between mean embeddings of the two windows | reported (no fixed threshold yet — needs real baselines) |
| Novelty rate | share of new tickets with no resolved neighbour above the similarity floor | > 50% |
| Agreement | acceptance rate of decided recommendations, recent vs baseline | drop > 15 points |

Windows with fewer than 20 tickets (or decisions) report "insufficient data". Operationally
(Prometheus): agent run time, step outcomes (`invalid`, `failed_verification` spikes mean the
model proposes illegal or non-sticking changes), human decisions, LLM failures and tokens.

## 3. Promotion gate — how a model or engine change ships

Any change to the embedding model, `app/ai/triage.py` (engine version), the agent or the KB
retrieval must:

1. **Offline:** re-run the relevant experiment(s) and show the new method is not worse on the
   test split (bootstrap CI where available) — including on the *novel* subset for classification.
2. **Pipeline:** pass `experiments/regression_gate.py` — a fixed 300-ticket replay of one synthetic
   organization; fails if category accuracy / macro-F1, priority accuracy or selective accuracy at
   confidence ≥ 0.7 drop by more than their tolerance vs `reports/pipeline/gate_baseline.json`.
   Runs in CI (`.github/workflows/ai-eval.yml`) on AI code changes, weekly and on demand.
3. **Baseline update:** only in the same pull request that justifies the change, with
   `--update-baseline`, and the reports regenerated.
4. **Rollout:** new model → `ai.reindex_tenant` for each organization (embeddings are keyed by
   model name, so old and new vectors never mix); watch `ai_monitoring` agreement for two weeks.
5. **Rollback:** redeploy the previous image tag (model files are baked into the image) and
   reindex.

## 4. Known gaps (measured, not hidden)

* Classification: kNN over TF-IDF scored higher than the shipped kNN over MiniLM on the public
  benchmark's novel tickets (queue macro-F1 0.719 vs 0.615). Candidate for the next promotion —
  it has to pass this gate first.
* Duplicates: at the production threshold, real duplicates are found with recall 0.18 (precision
  0.47). The flag is a hint, not a detector.
* No real-user acceptance data exists yet; the live metrics are wired but empty until a pilot.
* Generated text (summaries, drafts, KB answers) has no quality benchmark: no LLM provider is
  configured. The citation/support check is automated; an LLM-judged or human-rated evaluation
  set is the first task once a provider is enabled.

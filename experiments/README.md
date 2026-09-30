# Experiments

Every model-quality number in this repository comes from a script in this folder, run on the
pinned datasets described in [`docs/datasets.md`](../docs/datasets.md). Each run writes a JSON
record (git commit, dataset SHA-256s, parameters, metrics, environment) to `reports/<task>/`
and a human-readable `summary.md` next to it; runs are also logged to a local MLflow store
(`./mlruns`, not committed).

## Reproduce

```bash
python -m venv .venv-ml && . .venv-ml/bin/activate          # Windows: .venv-ml\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r ml/requirements.txt
export PYTHONPATH=ml                                          # Windows: set PYTHONPATH=ml

python -m nexadesk_ml.datasets all        # download (SHA-256 verified) + prepare splits
python -m nexadesk_ml.synthetic           # synthetic multi-org ticket history
pytest ml/tests                           # metric helpers + data invariants

python experiments/classification.py         # P4.1  queue / type / priority from text
python experiments/production_classifier.py  # P4.1b per-organization learners, learning curves, novel tickets
python experiments/routing.py                # P4.2  team routing (real ServiceNow data)
python experiments/duplicates.py             # P4.3  duplicate detection (CQADupStack + synthetic)
python experiments/duplicate_threshold.py    # P4.3b production duplicate-flag threshold
python experiments/sla_and_resolution.py     # P4.4/5 SLA breach + resolution time (real data)
python experiments/error_analysis.py         # P4.6  error analysis from the result files
python experiments/rag_retrieval.py          # P6    KB retrieval: BM25 vs dense vs hybrid vs rerank
```

Production-pipeline evaluation (backend virtualenv + an empty PostgreSQL 16/pgvector database,
which it wipes):

```bash
python -m nexadesk_ml.synthetic export-csv   # synthetic orgs in the history-importer format
EVAL_DATABASE_URL=postgresql+psycopg://user:pw@localhost:5432/nexadesk_eval   backend/.venv/bin/python experiments/pipeline_eval.py      # P5/P7 end-to-end replay
EVAL_DATABASE_URL=... backend/.venv/bin/python experiments/regression_gate.py   # P13 promotion gate
```

CPU only. Embeddings are cached under `data/cache/` keyed by model and input hash.

## Rules

* Model selection uses the **validation** split; the **test** split is scored once per run.
* Time-ordered data (the incident log) uses a **time-based** split — train on the past.
* Features are limited to what exists at prediction time; leakage exclusions are listed in each
  script's docstring.
* Every task reports a **baseline** (majority class, rule table, TF-IDF, median) next to the
  improved model, plus latency measured per single item on CPU.

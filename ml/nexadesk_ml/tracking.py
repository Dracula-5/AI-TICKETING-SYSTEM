"""
Experiment tracking.

Every experiment run records: task, run name, git commit (+ dirty flag),
SHA-256 of every input dataset file, parameters, metrics, artifacts, timing and
the package environment. Two sinks:

* reports/<task>/<run>.json — committed; the source of truth for every number
  quoted anywhere in the project.
* MLflow (local file store ./mlruns, git-ignored) — for browsing and comparing
  runs: `mlflow ui --backend-store-uri ./mlruns` (needs the full `mlflow`
  package). Best effort: a tracking failure never fails a run.
"""

import hashlib
import json
import os
import platform
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from nexadesk_ml.paths import MLRUNS, REPORTS, ROOT

_PACKAGES = ["numpy", "pandas", "scikit-learn", "lightgbm", "torch", "sentence-transformers", "transformers"]


def _git() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()

    return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain", "--", "ml", "experiments"))}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _environment() -> dict:
    versions = {}
    for p in _PACKAGES:
        try:
            versions[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            continue
    return {"python": platform.python_version(), "platform": platform.platform(), "cpu": platform.processor(), "packages": versions}


class Run:
    def __init__(self, task: str, name: str, datasets: list[Path]):
        self.task = task
        self.name = name
        self.datasets = {str(p.relative_to(ROOT)).replace("\\", "/"): file_sha256(p) for p in datasets}
        self.params: dict[str, Any] = {}
        self.metrics: dict[str, Any] = {}
        self.artifacts: list[str] = []
        self.notes: list[str] = []

    def log_params(self, **params):
        self.params.update(params)

    def log_metrics(self, **metrics):
        self.metrics.update(metrics)

    def add_artifact(self, path: Path):
        self.artifacts.append(str(path.relative_to(ROOT)).replace("\\", "/"))

    def note(self, text: str):
        self.notes.append(text)

    @property
    def report_dir(self) -> Path:
        d = REPORTS / self.task
        d.mkdir(parents=True, exist_ok=True)
        return d


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    if isinstance(value, float):
        return round(value, 6)
    return value


@contextmanager
def run(task: str, name: str, datasets: list[Path]):
    r = Run(task, name, datasets)
    started = time.time()
    yield r
    record = {
        "task": task,
        "run": name,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_seconds": round(time.time() - started, 2),
        "git": _git(),
        "datasets_sha256": r.datasets,
        "params": r.params,
        "metrics": r.metrics,
        "artifacts": r.artifacts,
        "notes": r.notes,
        "environment": _environment(),
    }
    out = r.report_dir / f"{name}.json"
    out.write_text(json.dumps(_jsonable(record), indent=2))
    _log_mlflow(record)


def _log_mlflow(record: dict) -> None:
    try:
        import mlflow
    except ImportError:
        return
    try:
        _log_mlflow_run(mlflow, record)
    except Exception as exc:  # noqa: BLE001 -- the JSON report is the source of truth
        print(f"warning: MLflow logging skipped: {exc}")


def _log_mlflow_run(mlflow, record: dict) -> None:
    # mlflow-skinny has no SQL store; its file store needs an explicit opt-in.
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    mlflow.set_tracking_uri(MLRUNS.as_uri())
    mlflow.set_experiment(record["task"])
    with mlflow.start_run(run_name=record["run"]):
        mlflow.set_tags({"git_commit": record["git"]["commit"], "git_dirty": str(record["git"]["dirty"])})
        mlflow.log_params({k: str(v)[:250] for k, v in _flatten(record["params"]).items()})
        mlflow.log_params({f"data.{k}": v[:16] for k, v in record["datasets_sha256"].items()})
        mlflow.log_metrics({k: float(v) for k, v in _flatten(record["metrics"]).items() if isinstance(v, (int, float))})


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out

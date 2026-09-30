from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
SYNTHETIC = DATA / "synthetic"
REPORTS = ROOT / "reports"
MODELS = ROOT / "ml" / "artifacts"
MLRUNS = ROOT / "mlruns"

for _p in (RAW, PROCESSED, SYNTHETIC, REPORTS, MODELS):
    _p.mkdir(parents=True, exist_ok=True)

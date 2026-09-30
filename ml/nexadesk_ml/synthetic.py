"""
Synthetic multi-organization ticket history (SYNTHETIC DATA).

    python -m nexadesk_ml.synthetic            # writes data/synthetic/*.parquet

What is real and what is invented — also stated in docs/datasets.md:

* Ticket text, queue, type and priority come from the public support-ticket
  dataset (itself LLM-generated), **train split only**, so synthetic tickets
  never contain benchmark test texts.
* Resolution times are bootstrap-sampled from the *real* resolution-time
  distribution of the UCI ServiceNow incident log for the matching priority
  (train split only).
* Arrival times, organizations, requesters, first-response times and planted
  duplicates are generated from the explicit parameters in CONFIG. They are
  assumptions, not measurements.

Every row carries data_origin="synthetic". Use: load/scale testing (P10–P11),
product demos, and in-domain sanity checks — never as evidence of real usage.
"""

import json
import random
import re
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from nexadesk_ml.paths import PROCESSED, SYNTHETIC


@dataclass
class OrgSpec:
    name: str
    tickets: int
    requesters: int


@dataclass
class Config:
    seed: int = 20260930
    start: str = "2026-03-01"
    days: int = 180
    orgs: list[OrgSpec] = field(
        default_factory=lambda: [
            OrgSpec("Helix Health (Synthetic)", 5500, 900),
            OrgSpec("Brightline Retail (Synthetic)", 4000, 650),
            OrgSpec("Orbital Engineering (Synthetic)", 2500, 300),
        ]
    )
    # Relative arrival weight by hour of day (local business hours peak) and weekday.
    hour_weights: list[float] = field(default_factory=lambda: [
        0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.5, 1.2, 2.5, 3.5, 3.6, 3.2,
        2.6, 3.0, 3.3, 3.1, 2.6, 1.8, 1.0, 0.6, 0.5, 0.4, 0.3, 0.2])
    weekday_weights: list[float] = field(default_factory=lambda: [1.15, 1.1, 1.05, 1.0, 0.9, 0.25, 0.2])
    # Share of 'high' Incidents in the outage queue promoted to 'critical'.
    critical_from_outage_incidents: float = 1.0
    # First response: log-normal, median minutes by priority (assumption).
    first_response_median_min: dict = field(default_factory=lambda: {"critical": 12, "high": 45, "medium": 150, "low": 300})
    first_response_sigma: float = 0.9
    # NexaDesk default SLA targets (app/services/organizations.py DEFAULT_SLA_MINUTES).
    sla_minutes: dict = field(default_factory=lambda: {
        "critical": (15, 240), "high": (60, 480), "medium": (240, 1440), "low": (480, 4320)})
    # Planted duplicates: share of tickets that are resubmissions of an earlier one.
    duplicate_rate: float = 0.04
    duplicate_window_hours: int = 72
    reopen_rate: float = 0.05


# UCI priority label -> NexaDesk priority (for resolution-time sampling).
UCI_PRIORITY = {"critical": "1 - Critical", "high": "2 - High", "medium": "3 - Moderate", "low": "4 - Low"}


def _perturb(text: str, rng: random.Random) -> str:
    """Resubmission-style edits: reorder sentences, drop one, add a nudge, typos."""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) > 2 and rng.random() < 0.5:
        sentences.pop(rng.randrange(1, len(sentences)))
    if len(sentences) > 2 and rng.random() < 0.5:
        i = rng.randrange(1, len(sentences))
        sentences.insert(0, sentences.pop(i))
    out = " ".join(sentences)
    if rng.random() < 0.6:
        out = rng.choice(["Following up on this: ", "Still having this problem. ", "Resubmitting — ", "Any update? "]) + out
    if rng.random() < 0.5 and len(out) > 20:  # a couple of typos
        chars = list(out)
        for _ in range(2):
            j = rng.randrange(len(chars) - 1)
            chars[j], chars[j + 1] = chars[j + 1], chars[j]
        out = "".join(chars)
    return out


def generate(cfg: Config | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = cfg or Config()
    rng = np.random.default_rng(cfg.seed)
    prng = random.Random(cfg.seed)

    texts = pd.read_parquet(PROCESSED / "tickets_en.parquet")
    texts = texts[texts["split"] == "train"].reset_index(drop=True)
    incidents = pd.read_parquet(PROCESSED / "incidents.parquet")
    incidents = incidents[(incidents["split"] == "train") & incidents["resolution_hours"].between(0, 24 * 60)]
    res_pool = {p: incidents.loc[incidents["open_priority"] == u, "resolution_hours"].to_numpy() for p, u in UCI_PRIORITY.items()}

    hour_p = np.array(cfg.hour_weights) / sum(cfg.hour_weights)
    start = pd.Timestamp(cfg.start, tz="UTC")
    day_w = np.array([cfg.weekday_weights[(start + pd.Timedelta(days=d)).dayofweek] for d in range(cfg.days)])
    day_p = day_w / day_w.sum()

    rows = []
    for org in cfg.orgs:
        picks = rng.integers(0, len(texts), org.tickets)
        days = rng.choice(cfg.days, org.tickets, p=day_p)
        hours = rng.choice(24, org.tickets, p=hour_p)
        minutes = rng.integers(0, 60, org.tickets)
        created = [start + pd.Timedelta(days=int(d), hours=int(h), minutes=int(m)) for d, h, m in zip(days, hours, minutes, strict=True)]
        for i, (pick, ts) in enumerate(zip(picks, created, strict=True)):
            src = texts.iloc[int(pick)]
            priority = src["priority"]
            if priority == "high" and src["queue"] == "Service Outages and Maintenance" and src["type"] == "Incident" \
                    and rng.random() < cfg.critical_from_outage_incidents:
                priority = "critical"
            rows.append({
                "org": org.name, "created_at": ts, "requester": f"requester-{int(rng.integers(0, org.requesters))}",
                "subject": src["subject"], "body": src["body"], "queue": src["queue"], "type": src["type"],
                "priority": priority, "source_ticket_id": src["ticket_id"], "duplicate_of": None,
            })

    df = pd.DataFrame(rows).sort_values(["org", "created_at"]).reset_index(drop=True)

    # Planted duplicates: rewrite a share of tickets as resubmissions of an
    # earlier ticket in the same org within the window.
    dup_pairs = []
    for org, group in df.groupby("org"):
        idx = group.index.to_numpy()
        times = group["created_at"].to_numpy()
        n_dup = int(len(idx) * cfg.duplicate_rate)
        chosen = rng.choice(np.arange(1, len(idx)), n_dup, replace=False)
        for c in sorted(chosen):
            window_start = times[c] - np.timedelta64(cfg.duplicate_window_hours, "h")
            candidates = [k for k in range(c) if times[k] >= window_start and df.at[idx[k], "duplicate_of"] is None]
            if not candidates:
                continue
            orig = idx[prng.choice(candidates)]
            dup = idx[c]
            df.loc[dup, ["subject", "queue", "type", "priority", "source_ticket_id"]] = df.loc[
                orig, ["subject", "queue", "type", "priority", "source_ticket_id"]].to_numpy()
            df.at[dup, "body"] = _perturb(df.at[orig, "body"], prng)
            if prng.random() < 0.5:
                df.at[dup, "subject"] = prng.choice(["Re: ", "Follow-up: ", "Again: "]) + str(df.at[orig, "subject"])
            df.at[dup, "duplicate_of"] = int(orig)
            dup_pairs.append((int(orig), int(dup)))

    # Lifecycle outcomes.
    fr_median = df["priority"].map(cfg.first_response_median_min).astype(float)
    df["first_response_minutes"] = np.exp(np.log(fr_median) + rng.normal(0, cfg.first_response_sigma, len(df)))
    df["resolution_hours"] = [float(rng.choice(res_pool[p])) for p in df["priority"]]
    df["resolution_hours"] = np.maximum(df["resolution_hours"], df["first_response_minutes"] / 60 + 0.05)
    fr_target = df["priority"].map({k: v[0] for k, v in cfg.sla_minutes.items()})
    res_target = df["priority"].map({k: v[1] for k, v in cfg.sla_minutes.items()})
    df["first_response_breached"] = df["first_response_minutes"] > fr_target
    df["resolution_breached"] = df["resolution_hours"] * 60 > res_target
    df["reopened"] = rng.random(len(df)) < cfg.reopen_rate
    df["resolved_at"] = df["created_at"] + pd.to_timedelta(df["resolution_hours"], unit="h")
    df["data_origin"] = "synthetic"
    df.insert(0, "synthetic_id", np.arange(len(df)))

    # Duplicate-pair benchmark: planted positives + hard negatives (same org,
    # same queue, within the window, not a duplicate).
    pairs = [{"a": a, "b": b, "label": 1} for a, b in dup_pairs]
    by_key = df.groupby(["org", "queue"]).indices
    for a, b in dup_pairs:
        key = (df.at[b, "org"], df.at[b, "queue"])
        pool = [k for k in by_key[key] if k not in (a, b) and abs((df.at[k, "created_at"] - df.at[b, "created_at"]).total_seconds())
                < cfg.duplicate_window_hours * 3600 and df.at[k, "duplicate_of"] != a and df.at[k, "source_ticket_id"] != df.at[b, "source_ticket_id"]]
        for k in prng.sample(pool, min(3, len(pool))):
            pairs.append({"a": int(k), "b": b, "label": 0})
    pairs_df = pd.DataFrame(pairs)

    SYNTHETIC.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SYNTHETIC / "tickets.parquet", index=False)
    pairs_df.to_parquet(SYNTHETIC / "duplicate_pairs.parquet", index=False)
    (SYNTHETIC / "config.json").write_text(json.dumps(asdict(cfg), indent=2, default=str))
    return df, pairs_df


def export_import_csv(df: pd.DataFrame | None = None) -> list:
    """Write each synthetic organization as a CSV in the format of NexaDesk's
    history importer (backend/app/scripts/import_history.py). Queue doubles as
    category and team — one team per queue, as in many helpdesks. Extra columns
    (synthetic_id, duplicate_of, type) are ignored by the importer and used by
    experiments/pipeline_eval.py as ground truth."""
    df = pd.read_parquet(SYNTHETIC / "tickets.parquet") if df is None else df
    out_dir = SYNTHETIC / "import"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for org, g in df.sort_values("created_at").groupby("org"):
        slug = org.split(" (")[0].lower().replace(" ", "-")
        out = pd.DataFrame({
            "synthetic_id": g["synthetic_id"],
            # Some source tickets have no subject; like a mail gateway, fall back to the body's opening.
            "title": g["subject"].fillna("").str.strip().where(lambda t: t != "", g["body"].str.slice(0, 80)).str.slice(0, 200),
            "description": g["body"],
            "created_at": g["created_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "resolved_at": g["resolved_at"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "category": g["queue"],
            "team": g["queue"],
            "priority": g["priority"],
            "type": g["type"],
            "requester_email": g["requester"] + f"@{slug}.synthetic.invalid",
            "duplicate_of": g["duplicate_of"].astype("Int64"),
        })
        path = out_dir / f"{slug}.csv"
        out.to_csv(path, index=False)
        paths.append(path)
    return paths


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["export-csv"]:
        for p in export_import_csv():
            print(p)
        raise SystemExit(0)
    tickets, pairs = generate()
    print(f"synthetic tickets: {len(tickets)} across {tickets['org'].nunique()} orgs; "
          f"planted duplicate pairs: {int(pairs['label'].sum())}; negative pairs: {int((pairs['label'] == 0).sum())}")

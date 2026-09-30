"""
Public datasets: download, verify, prepare.

    python -m nexadesk_ml.datasets fetch      # download raw files, verify SHA-256
    python -m nexadesk_ml.datasets prepare    # build data/processed/*.parquet + split files

Every raw file is pinned by SHA-256 (MANIFEST). A changed upstream file fails
verification instead of silently changing every downstream metric. Details,
licenses and provenance: docs/datasets.md.
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.request
import zipfile

import numpy as np
import pandas as pd

from nexadesk_ml.paths import PROCESSED, RAW

MANIFEST = {
    "uci_incident_event_log.zip": {
        "url": "https://archive.ics.uci.edu/static/public/498/incident+management+process+enriched+event+log.zip",
        "sha256": "6294e29a311647306bfdfc85783f7df66517c197b9cd49aa5ee36ba9c525d1d6",
    },
    "support_tickets_multilang_5_2_50.csv": {
        "url": "https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets/resolve/main/"
        "aa_dataset-tickets-multi-lang-5-2-50-version.csv",
        "sha256": "f187c090e59581c2bbf3aa1377c8db4dd647464ecf2ae51bf8966e42e0ed6bc0",
    },
    "cqadupstack_unix_corpus.jsonl": {
        "url": "https://huggingface.co/datasets/mteb/cqadupstack-unix/resolve/main/corpus.jsonl",
        "sha256": "fd1c0922dc036962440cfc9d440574ca0e22bfcbc5f6059072e7339fdb8d569e",
    },
    "cqadupstack_unix_queries.jsonl": {
        "url": "https://huggingface.co/datasets/mteb/cqadupstack-unix/resolve/main/queries.jsonl",
        "sha256": "2ed3a6d73a03c06213e5f05f74126d7187528e9d26917d8562d312226947aea9",
    },
    "cqadupstack_unix_qrels_test.tsv": {
        "url": "https://huggingface.co/datasets/mteb/cqadupstack-unix/resolve/main/qrels/test.tsv",
        "sha256": "a7bd24ce081b0bb892602e9b0067017dc66fd03e7593563ad095cb3cd05e92ed",
    },
}

SEED = 42


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch() -> None:
    for name, meta in MANIFEST.items():
        path = RAW / name
        if not path.exists():
            print(f"downloading {name}")
            urllib.request.urlretrieve(meta["url"], path)  # noqa: S310 -- pinned https URLs
        digest = sha256_file(path)
        if digest != meta["sha256"]:
            sys.exit(f"checksum mismatch for {name}: {digest} != {meta['sha256']}")
        print(f"ok  {name}")
    with zipfile.ZipFile(RAW / "uci_incident_event_log.zip") as z:
        z.extract("incident_event_log.csv", RAW)


# ---------------------------------------------------------------------------
# 1. UCI incident management event log  ->  one row per incident
# ---------------------------------------------------------------------------
UCI_TIME_COLS = ["opened_at", "sys_created_at", "sys_updated_at", "resolved_at", "closed_at"]


def _uci_ts(col: pd.Series) -> pd.Series:
    return pd.to_datetime(col.replace("?", np.nan), format="%d/%m/%Y %H:%M", errors="coerce")


def prepare_incidents() -> pd.DataFrame:
    """Aggregate the event log to incidents.

    Features are restricted to what is known when the incident is opened
    (first event), plus leakage-safe context computed only from earlier
    incidents. Final-state columns (reassignment/reopen counts, sys_mod_count,
    resolved/closed timestamps) are kept only as targets or for analysis.
    """
    ev = pd.read_csv(RAW / "incident_event_log.csv", na_values=["?"], keep_default_na=True, low_memory=False)
    for c in UCI_TIME_COLS:
        ev[c] = _uci_ts(ev[c].astype("string"))
    ev = ev.sort_values(["number", "sys_updated_at"])

    first = ev.groupby("number").first()
    last = ev.groupby("number").last()
    inc = pd.DataFrame(index=first.index)
    inc["opened_at"] = first["opened_at"]
    for col in ["contact_type", "location", "category", "subcategory", "u_symptom", "impact", "urgency",
                "priority", "assignment_group", "knowledge", "u_priority_confirmation", "notify", "caller_id",
                "opened_by"]:
        inc[f"open_{col}"] = first[col]
    # Targets / outcomes (final state).
    inc["made_sla"] = last["made_sla"].astype(bool)
    inc["breached_sla"] = ~inc["made_sla"]
    inc["resolved_at"] = last["resolved_at"]
    inc["closed_at"] = last["closed_at"]
    inc["final_assignment_group"] = last["assignment_group"]
    inc["final_state"] = last["incident_state"]
    inc["reassignment_count"] = last["reassignment_count"]
    inc["reopen_count"] = last["reopen_count"]
    inc["resolution_hours"] = (inc["resolved_at"] - inc["opened_at"]).dt.total_seconds() / 3600

    inc = inc.dropna(subset=["opened_at"]).sort_values("opened_at")
    inc["priority_num"] = inc["open_priority"].str.extract(r"^(\d)").astype(float)
    inc["impact_num"] = inc["open_impact"].str.extract(r"^(\d)").astype(float)
    inc["urgency_num"] = inc["open_urgency"].str.extract(r"^(\d)").astype(float)
    inc["open_hour"] = inc["opened_at"].dt.hour
    inc["open_dow"] = inc["opened_at"].dt.dayofweek

    # Leakage-safe load feature: incidents opened in the same assignment group
    # during the preceding 24 hours (strictly earlier timestamps).
    inc["group_load_24h"] = 0
    for _, idx in inc.groupby("open_assignment_group").groups.items():
        times = inc.loc[idx, "opened_at"].sort_values()
        vals = times.values.astype("datetime64[s]").astype(np.int64)
        left = np.searchsorted(vals, vals - 24 * 3600, side="left")
        inc.loc[times.index, "group_load_24h"] = np.arange(len(vals)) - left

    # Time-based split: train on the past, evaluate on the future.
    n = len(inc)
    split = np.array(["train"] * n, dtype=object)
    split[int(n * 0.70) : int(n * 0.85)] = "val"
    split[int(n * 0.85) :] = "test"
    inc["split"] = split
    inc = inc.reset_index().rename(columns={"number": "incident_id"})
    inc.to_parquet(PROCESSED / "incidents.parquet", index=False)
    return inc


# ---------------------------------------------------------------------------
# 2. Support ticket texts (synthetic, published)  ->  English tickets, dedup, split
# ---------------------------------------------------------------------------
QUEUE_TO_CATEGORY = {
    # Public queue label -> NexaDesk category used in the product. Kept 1:1 so
    # benchmark numbers are on the dataset's own labels.
    "Technical Support": "Technical Support",
    "Product Support": "Product Support",
    "Customer Service": "Customer Service",
    "IT Support": "IT Support",
    "Billing and Payments": "Billing and Payments",
    "Returns and Exchanges": "Returns and Exchanges",
    "Service Outages and Maintenance": "Service Outages and Maintenance",
    "Sales and Pre-Sales": "Sales and Pre-Sales",
    "Human Resources": "Human Resources",
    "General Inquiry": "General Inquiry",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\\n", " ")).strip().lower()


def prepare_tickets() -> pd.DataFrame:
    df = pd.read_csv(RAW / "support_tickets_multilang_5_2_50.csv", encoding="utf-8")
    df = df[df["language"] == "en"].copy()
    df["subject"] = df["subject"].fillna("")
    df["body"] = df["body"].fillna("").str.replace("\\n", "\n", regex=False)
    df["answer"] = df["answer"].fillna("").str.replace("\\n", "\n", regex=False)
    df["text"] = (df["subject"].str.strip() + "\n" + df["body"].str.strip()).str.strip()
    df = df[df["text"].str.len() > 10]

    # Exact / whitespace-level duplicates would leak across splits (the same
    # ticket in train and test). Keep one row per normalized text.
    df["_key"] = df["text"].map(_norm)
    before = len(df)
    df = df.drop_duplicates("_key").drop(columns="_key")
    dropped = before - len(df)

    tags = [c for c in df.columns if c.startswith("tag_")]
    df["tags"] = df[tags].apply(lambda r: [t for t in r if isinstance(t, str) and t], axis=1)
    df = df.drop(columns=tags + ["version", "language"])
    df = df.reset_index(drop=True)
    df.insert(0, "ticket_id", [f"T{i:05d}" for i in range(len(df))])

    # Stratified 70/15/15 by queue (no timestamps in this dataset).
    rng = np.random.default_rng(SEED)
    split = pd.Series("train", index=df.index, dtype=object)
    for _, idx in df.groupby("queue").groups.items():
        idx = rng.permutation(np.array(idx))
        n = len(idx)
        split[idx[int(n * 0.70) : int(n * 0.85)]] = "val"
        split[idx[int(n * 0.85) :]] = "test"
    df["split"] = split
    df.to_parquet(PROCESSED / "tickets_en.parquet", index=False)
    (PROCESSED / "tickets_en.dedup.json").write_text(json.dumps({"rows_before": before, "exact_duplicates_dropped": dropped}))
    return df


# ---------------------------------------------------------------------------
# 3. CQADupStack (unix)  ->  queries, corpus, qrels
# ---------------------------------------------------------------------------
def prepare_duplicates() -> dict:
    corpus = pd.read_json(RAW / "cqadupstack_unix_corpus.jsonl", lines=True, dtype={"_id": str})
    queries = pd.read_json(RAW / "cqadupstack_unix_queries.jsonl", lines=True, dtype={"_id": str})
    qrels = pd.read_csv(RAW / "cqadupstack_unix_qrels_test.tsv", sep="\t", dtype={"query-id": str, "corpus-id": str})
    corpus = corpus.rename(columns={"_id": "doc_id"})[["doc_id", "title", "text"]]
    queries = queries.rename(columns={"_id": "query_id"})[["query_id", "text"]]
    qrels = qrels.rename(columns={"query-id": "query_id", "corpus-id": "doc_id"})[["query_id", "doc_id", "score"]]
    queries = queries[queries["query_id"].isin(qrels["query_id"])]
    corpus.to_parquet(PROCESSED / "dup_unix_corpus.parquet", index=False)
    queries.to_parquet(PROCESSED / "dup_unix_queries.parquet", index=False)
    qrels.to_parquet(PROCESSED / "dup_unix_qrels.parquet", index=False)
    return {"corpus": len(corpus), "queries": len(queries), "qrels": len(qrels)}


def prepare() -> None:
    inc = prepare_incidents()
    print(f"incidents: {len(inc)} rows, splits {inc['split'].value_counts().to_dict()}")
    tk = prepare_tickets()
    print(f"tickets_en: {len(tk)} rows, splits {tk['split'].value_counts().to_dict()}")
    print(f"duplicates: {prepare_duplicates()}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["fetch", "prepare", "all"])
    args = parser.parse_args()
    if args.command in ("fetch", "all"):
        fetch()
    if args.command in ("prepare", "all"):
        prepare()


if __name__ == "__main__":
    main()

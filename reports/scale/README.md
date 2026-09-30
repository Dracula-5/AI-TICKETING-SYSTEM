# P11 — Database volume: 10k → 100k → 1M tickets in one organization

`experiments/db_scale.py` grows one SYNTHETIC organization (`app/scripts/seed_volume.py`: realistic
status/priority/category mix over a year, one history row per ticket, comments on 30%) and calls the
real API endpoints in-process 20 times each at every size (FastAPI → SQLAlchemy → PostgreSQL 16 in
Docker on the same laptop; no HTTP proxy, no cache for the dashboard). The slowest SQL of each
endpoint is kept with its `EXPLAIN (ANALYZE, BUFFERS)` plan in the JSON files.

* `db_scale_baseline.json` — schema at migration 0008, 10k / 100k / 1M.
* `db_scale_optimized.json` — the same 1M database after migration 0009 (trigram indexes) and the
  ticket-number lookup change.

p50 / p95 in ms:

| Endpoint | 10k | 100k | 1M | 1M after changes |
|---|---|---|---|---|
| queue (open, unassigned) | 46 / 69 | 53 / 58 | 196 / 265 | 186 / 208 |
| my work (open, mine) | 47 / 61 | 48 / 61 | 169 / 221 | 139 / 155 |
| requester's tickets | 41 / 49 | 44 / 48 | 41 / 57 | 43 / 57 |
| all tickets, newest | 45 / 57 | 39 / 57 | 87 / 93 | 78 / 101 |
| open by priority | 39 / 45 | 77 / 90 | 364 / 412 | 369 / 433 |
| SLA at risk | 32 / 56 | 52 / 69 | 59 / 85 | 57 / 78 |
| SLA breached | 34 / 52 | 58 / 75 | 164 / 186 | 173 / 203 |
| search "printer" (common word, 7% of tickets) | 48 / 52 | 133 / 178 | 486 / 511 | 570 / 625 |
| search "#123" (ticket number) | 49 / 71 | 281 / 355 | **5,123 / 5,537** | **27 / 33** |
| dashboard overview (uncached) | 109 / 161 | 340 / 414 | 2,173 / 2,333 | 2,193 / 2,286 |
| ticket detail | 50 / 63 | 45 / 67 | 31 / 43 | 37 / 52 |
| ticket history | 32 / 42 | 36 / 51 | 28 / 49 | 24 / 33 |

Storage: 10k tickets 17 MB database, 100k 72 MB, 1M 596 MB (tickets 395 MB, history 146 MB, comments
44 MB); the two trigram indexes add 118 MB at 1M.

## Findings

1. **Ticket-number search collapsed at 1M (5.1 s).** Plan: backward scan of the created-at index
   filtering for a rare match to fill `LIMIT 25`. Change: `#123` is an exact lookup on the unique
   `(tenant, number)` index → **27 ms**.
2. **Trigram indexes help selective terms, not common ones.** At 100k the search query itself went
   75 → 20 ms (load-test database, same term); at 1M "printer" matches 71k tickets, so the bitmap
   heap scan dominates and the endpoint stays ~0.5–0.6 s. Kept: they cost 118 MB at 1M and
   bound the worst case; full-text ranking with a result cap is the next step if search at this
   size matters.
3. **Dashboard aggregates grow linearly (2.2 s uncached at 1M).** In the app they are cached for
   30 s per organization (`routers/analytics.py`), so a person sees this at most once per 30 s;
   pre-aggregated counters are the next step for organizations of this size.
4. **"Open by priority" sorts every open ticket (0.37 s at 1M).** Acceptable; an index on the
   priority rank would remove the sort if it becomes a problem.
5. Point lookups (detail, history, a requester's own tickets) are flat from 10k to 1M.

One organization with 1M tickets is far beyond the pilot scale; these numbers bound the design
rather than describe expected use.

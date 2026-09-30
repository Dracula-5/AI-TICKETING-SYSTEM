# Cost (P17)

What it costs to run NexaDesk, split into what was **measured** in this repository and what comes
from **third-party price lists** (dated, to be re-checked before buying). No operating cost has
been incurred yet — nothing is deployed on paid infrastructure.

## 1. Resource use — measured

| Quantity | Value | Source |
|---|---|---|
| Backend image | 839 MB | `docker images`, 2026-10-01 (includes the 87 MB embedding model and ONNX Runtime) |
| Web image | 83.6 MB | same |
| Containers' memory under load (250–500 users) | API 2 processes 550–600 MiB · worker 230 MiB · PostgreSQL 300–370 MiB · Caddy 80–100 MiB · Redis 7 MiB · web 10 MiB (≈ 1.2 GiB); + Prometheus 35 MiB, Grafana 135 MiB | `reports/load/README.md` |
| Database size per ticket | see `reports/scale/` (10k / 100k / 1M tickets) | `experiments/db_scale.py` |
| Embedding storage per ticket (vector(384) + HNSW index) | ≈ 3.6 kB | `pg_total_relation_size('ticket_embeddings')` ÷ 2,227 vectors, 2026-10-01 |
| One triage-agent run (embed + search + votes + validation + record), p50 | 107–159 ms (first replay), 154–314 ms (second replay, machine shared with other work) | `reports/pipeline/`; synthetic replay, local Windows + Docker PostgreSQL |
| Text generation | 0 calls, 0 tokens | no provider configured; every call would be in `llm_calls` |

## 2. Infrastructure price references (third party, excl. VAT)

From the *Cloud Pricing Comparison, 2026-08* (kimmo.suominen.com/stuff/cpc-2026-08.txt), 2 vCPU / 4 GB
class, monthly: Hetzner CX23 €5.99 (40 GB disk) · Netcup VPS 500 G12 €4.97 · AWS t4g.medium
€13.69 (3-year commitment) · DigitalOcean Basic 2 vCPU €20.88 · Akamai Linode 4 GB €20.88.
Hetzner raised several European cloud prices on 15 June 2026 — prices move; check the provider's
page on the day you buy.

## 3. Monthly cost model

```
monthly = VM + backup storage + (optional) LLM usage + (optional) email provider + domain/12

LLM usage = Σ_features calls × (input_tokens × price_in + output_tokens × price_out) / 1e6
```

* **VM:** the sizing in §4 decides between a 4 GB and an 8 GB machine.
* **LLM usage** is exactly what the `llm_calls` ledger records once prices are configured
  (`LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK`); per-organization monthly token budgets
  cap it. Summaries are capped at 300 output tokens, drafts and KB answers at 400.
* **No per-ticket model cost** for triage, duplicates, SLA risk or search: they run on the VM's
  CPU with an open model baked into the image.

## 4. Sizing

Measured on a laptop, not a VM (`reports/load/README.md`): the application uses about 1.2 GiB of
memory under load (1.4 GiB with the observability profile) and served ~30 req/s at p95 150 ms
(100 concurrent users of the test profile) and ~66 req/s error-free at 250 users before
saturating. For a public demo or a small pilot team, a **4 GB / 2 vCPU** VM (e.g. the
€5.99/month class in §2) leaves headroom for PostgreSQL's cache; 2 GB would be tight once the
embedding model is loaded in each API process. Re-run `loadtest/run_load.py` on the chosen VM
before inviting a larger pilot.

## 5. Cost controls built in

Per-organization LLM token budget (refuses requests beyond it); no LLM call when retrieval finds
nothing relevant; rate limits on generation endpoints; embeddings computed once per ticket and
reused for triage, duplicates and "similar tickets"; cross-encoder reranking off by default (it
cost ~1.2 s CPU per query and did not improve retrieval on the P6 benchmark).

# Interview guide

Use these answers as prompts for discussion, not claims of customer impact. All model numbers
refer to the reproducible reports linked below; none are production-user results.

## Business and consulting

**What problem does this solve?** It gives IT/operations teams an auditable intake-to-resolution
workflow and brings triage, SLA visibility, knowledge and agent assistance into one tenant-scoped
system.

**Who is the customer, and why use AI?** The intended customer is an internal service desk. AI is
useful for ranking likely categories, similar prior tickets and relevant knowledge, but rules and
human decisions remain available because the evidence is imperfect.

**What is the measured value?** No business value has been measured with real users. The business
case defines a pilot and KPIs; public benchmark performance is not translated into savings.

## Architecture and operations

**Why a modular monolith?** Ticket updates need atomic status, history, audit and notification
records. One deployable is simpler to operate for the current scope; AI workers and read-heavy
analytics are future extraction candidates if measurements show a separate scaling need.

**Why PostgreSQL and pgvector?** PostgreSQL is the system of record and supports relational
transactions, full-text search and vector search. Tenant predicates can be applied in the same
retrieval query, avoiding a separate vector-store security boundary.

**Why FastAPI and a worker?** FastAPI provides typed HTTP APIs and OpenAPI. A separate worker
handles retryable or scheduled work without tying it to API request lifetime.

**What happens if Redis or the LLM is unavailable?** Cache/rate-limit integrations are designed
to fail open; deterministic rules and non-generative paths remain. Provider calls are optional,
budgeted and logged. Verify the exact deployment configuration before making an availability
claim.

**How would you scale to millions of tickets?** It was measured at 1M tickets in one organization
(`reports/scale/README.md`): point lookups stay flat, a ticket-number search degraded to 5 s and
was fixed (27 ms) by making `#123` an exact index lookup, and the uncached dashboard reached 2.2 s
(cached 30 s). The load test found a connection-pool deadlock and fixed it (`reports/load/`). Next
steps would follow those numbers: pre-aggregated dashboard counters, capped full-text ranking for
common search terms, then archival/partitioning, read replicas for analytics and separate
inference workers — measured on the real VM first.

## ML and GenAI

**Why macro-F1?** Classes are imbalanced, so macro-F1 gives each class a voice. The reports also
include per-class errors and weighted/accuracy metrics where relevant.

**What caused errors?** Ticket categories overlap semantically, rare routing groups have little
training data, priority has substantial medium/high confusion, SLA labels shift with time, and
resolution-time errors concentrate in long-open tickets. See `reports/error_analysis.md`.

**Why RAG, hybrid search and reranking?** Retrieval grounds answers in tenant documents. The
CQADupStack experiment found dense MiniLM retrieval stronger than the tested lexical and equal
weight fusion configurations. Reranking improved some ranking measures but cost about 1.15 s
median on CPU and did not justify enabling it by default. This is a retrieval benchmark, not an
answer-faithfulness result.

**How are hallucinations and prompt injection handled?** The answer path requires retrieved
evidence and citations, treats document text as untrusted data, and can return no answer. The
guardrails are tested, but no human-rated hallucination benchmark has been run yet.

## System design

**How is tenant isolation enforced?** Authenticated user records determine organization scope;
queries constrain tenant IDs and foreign resource IDs return not-found. Tests exercise the
tenant boundary. KB retrieval also carries tenant scope into search.

**How are retries and duplicate jobs handled?** Durable job rows use deduplication keys, leases,
backoff and dead-letter state. Operations should remain idempotent and be verified before retry.

**What should be built next?** Complete the owner-controlled deployment, run externally reachable
staging checks, recruit a consenting pilot, and measure baseline-vs-pilot workflow outcomes.
Only then decide whether automation should be enabled for particular recommendation types.

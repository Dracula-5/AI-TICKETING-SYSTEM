# Business case

## Problem and current-state process

Internal IT and operations requests arrive across forms, email and chat. Staff manually
categorize, route and prioritize work; requesters have limited status visibility; managers find
SLA risk and backlog through manual reporting. The costs to an individual organization are not
quantified here because no customer baseline has been collected.

## Proposed future state

NexaDesk provides one auditable service record from intake through closure. Deterministic rules
and measured recommendation models assist classification and routing; a tenant-scoped knowledge
base retrieves evidence; SLA and duplicate signals support agents; human approval gates protected
actions. Analytics are calculated from the organization's own data and marked by data origin.

## Solution and architecture

The implementation is a FastAPI modular monolith, React/TypeScript SPA, PostgreSQL with pgvector,
and optional Redis, delivered with Docker Compose. A database-backed worker handles durable jobs.
This keeps ticket, status history and audit updates transactional while retaining extraction
points for independently scaling AI work if measurements justify it. Details and ADRs are in
[`system_design.md`](system_design.md).

## Evidence and expected value

Offline experiments show that automated routing is not better overall than the historical human
dispatcher on the selected public incident benchmark (65.5% vs 67.3% top-1). At confidence at
least 0.9 it covers 16% of that benchmark at 93.7% accuracy, comparable to human dispatch on the
same slice. These results justify cautious, reviewable recommendations; they do not prove time or
cost savings. The retrieval benchmark and synthetic pipeline replay are documented separately.

Expected value hypotheses are faster triage, fewer avoidable reassignments, earlier SLA attention,
fewer repeat questions and improved operational visibility. The pilot plan defines comparisons
and acceptance criteria. No savings, CSAT, real-user adoption, or production improvement is
claimed today.

## KPIs and measurement

Measure per organization: time to correct assignment, first-response and resolution time,
reassignment rate, SLA breach rate, recommendation accept/edit/reject, automation reverts, CSAT,
KB helpfulness, and active invited users. Use imported prior-period history where available and
report periods and sample counts. The value report accepts explicit labor-time and cost
assumptions and labels its output as modeled work handled, not measured savings.

## Risks and assumptions

The public datasets do not represent a particular customer's taxonomy; some text data is
synthetic or non-commercial; cold-start tenants have limited ticket history; duplicate detection
has low recall at the conservative production threshold; and SLA base rates shift over time.
Text generation is disabled until configured and approved. Deployment, email delivery and
external-user operation depend on owner-managed services and secrets.

## Roadmap

See [`transformation_roadmap.md`](transformation_roadmap.md) for implemented phases, external
dependencies, and the recommended pilot sequence.

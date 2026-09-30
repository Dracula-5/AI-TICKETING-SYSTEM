# Transformation roadmap

This roadmap separates code already present from work that needs an external deployment, real
participants, or further measurement. Stage evidence and reproduction commands are maintained in
[`execution_plan.md`](execution_plan.md), [`experiments/README.md`](../experiments/README.md),
and the linked reports.

| Phase | State | Deliverable / exit evidence |
|---|---|---|
| 1. Digital intake and service workflow | Implemented (P1) | Tenant-scoped organizations, ticket state machine, SLA, collaboration, audit and operations dashboard. |
| 2. AI triage and routing | Implemented (P4–P5) | Reproducible public-data baselines and a synthetic-organization production-path replay. Results are not user outcomes. |
| 3. Knowledge retrieval | Implemented (P6) | Tenant-scoped document ingestion and cited retrieval; retrieval benchmark on CQADupStack. Generated answer quality is not yet benchmarked. |
| 4. Agent assistance | Implemented with deterministic playbook (P5/P7) | Typed tools, authorization, verification, evidence and logged recommendations; generative provider remains opt-in. |
| 5. Human oversight | Implemented (P8) | Approval queue, recommendation decisions, feedback capture and audit trail. Pilot adoption metrics are empty until users participate. |
| 6. Predictive analytics | Offline baselines measured (P4) | SLA risk and resolution-time experiments; model limitations are documented. Operational value is unproven. |
| 7. Enterprise deployment | Prepared, not live (P2) | Compose/Caddy, migrations, health checks, backup and rollback. Requires owner-provided VM, DNS and deployment secrets. |
| 8. Pilot and measured business impact | Not started (P9/P16) | Recruit a consenting organization, collect a baseline, run recommend-only then optional automation, and publish tenant-scoped measured outcomes. |
| 9. Load, scale and cost validation | Measured locally (P10–P11/P17) | `reports/load/README.md`, `reports/scale/`, `docs/cost.md`: laptop results with fixes and before/after deltas. Re-run on the chosen VM. |

## Recommended next sequence

1. Complete an owner-controlled staging deployment and validate HTTPS, backup restore, and
   registration from an external network.
2. Run the existing acceptance suite against that deployment and address any environment-specific
   failures before inviting pilot users.
3. Start a small consented pilot in recommend-only mode; keep demo, synthetic and real data
   separate in every report.
4. Re-run the load and storage experiments on the selected VM (the laptop results are in
   `reports/load/` and `reports/scale/`) and confirm capacity before a larger pilot.
5. Benchmark generated responses with a labelled question set and human review before enabling
   text generation for a pilot organization.

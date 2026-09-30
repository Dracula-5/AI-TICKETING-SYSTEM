# Real-user pilot plan (P9)

**Status: ready to run, not started.** No real organization has used NexaDesk yet. Everything
below is the plan and the tooling; no pilot result exists until a pilot has been run and its
report generated from the database. Until then the deployment is described as a *public demo
deployment*, and every number in this repository comes from public benchmarks, synthetic
replays or automated tests — never from users.

## 1. Question the pilot answers

Does a small IT or operations support team resolve internal requests at least as fast, with
at least as good requester satisfaction, when using NexaDesk's recommendations — and how
often do agents accept, correct or reject those recommendations?

## 2. Participants

| Role | Target | How they join |
|---|---|---|
| Pilot organization | 1–3 teams (5–30 people) with a real internal support queue | Owner recruits; organization created by its admin (not a demo org) |
| Agents / managers | 2–8 per organization | Invitations from the org admin |
| Requesters | Colleagues who raise requests | Self-service portal restricted to the company's email domain |

Excluded: demo organizations (`is_demo`), synthetic organizations (`data_origin` ≠ `real`),
and the NexaDesk developers' own test tickets.

## 3. Duration and phases

1. **Week 0 — setup (≤ 1 day):** create the organization; import up to 12 months of resolved
   tickets from the previous tool (`python -m app.scripts.import_history --origin real`) so
   recommendations have history; upload existing runbooks/FAQs to the knowledge base.
2. **Weeks 1–2 — recommend-only:** all AI output is proposed; nothing applies automatically.
3. **Weeks 3–4 — optional automation:** only if week 1–2 acceptance for a kind is high (see
   §5), the org admin may enable auto-apply for that kind at a confidence threshold chosen
   from the P7/P8 replay analysis.

## 4. Consent and data handling

* Participants are told, before they start, that this is a pilot, what is measured, and how AI
  is used — the in-app notice at `/ai-notice` is the plain-language version.
* Recommendations and search run on the deployment's own server. Text generation (summaries,
  reply drafts, KB answers) stays **off** unless the organization explicitly agrees to send
  ticket text to the configured provider; if enabled, every call is logged in `llm_calls`.
* Data stays in the organization's tenant; it is deleted on request at the end of the pilot
  (database backup rotation per `docs/runbook.md`).
* No individual performance is reported; metrics are per organization.

## 5. Metrics — defined before any data exists

All computed by `app/services/pilot.py` (`GET /analytics/pilot`,
`python -m app.scripts.pilot_report --org <slug>`). Rates over fewer than 5 observations are
reported as "not enough data".

| Metric | Definition | Pilot target (hypothesis, not a result) |
|---|---|---|
| AI acceptance rate | accepted ÷ (accepted + edited + rejected) recommendations | ≥ 60% for category/team before auto-apply is considered |
| Automation false-positive rate | auto-applied changes a person later reverted ÷ auto-applied | ≤ 5% for any kind left on auto-apply |
| Median first response | created → first staff reply | not worse than the team's previous tool (baseline from imported history) |
| Median resolution time | created → resolved | not worse than baseline |
| CSAT | mean 1–5 rating on resolved tickets; share of 4–5 | share of 4–5 ≥ 80% |
| KB helpfulness | "helpful" ÷ rated searches/answers | reported; no target (first measurement) |
| Adoption | people who signed in during the window ÷ invited | reported |

Baseline for time metrics: the same statistics over the organization's imported history
(`channel = "import"`), reported side by side and labelled as a different tool/period.

## 6. Feedback channels

* CSAT prompt on every resolved ticket (requester).
* "Helpful / not helpful" on KB answers and summaries; accept / edit / reject on every
  recommendation (agents).
* "Send feedback" in the account menu (everyone) — reviewed weekly.

## 7. Weekly review

Generate the pilot report, read all product feedback, list the top three problems, decide
fixes. Keep the reports (they are the pilot's evidence) under `reports/pilot/<org>/`.

## 8. Exit criteria

* **Continue / widen:** targets in §5 met for two consecutive weeks.
* **Change course:** acceptance < 40% for a kind → stop showing that kind to this org and
  investigate its errors; automation false-positive rate > 5% → switch that kind back to
  recommend-only immediately.
* **Stop:** any cross-tenant data exposure or data loss (P0 incident, `docs/runbook.md`).

## 9. What is needed from the owner

A real deployment (P2 go-live: VM, DNS, deploy secrets), a pilot organization willing to
participate, and a decision on whether text generation may be enabled for it.

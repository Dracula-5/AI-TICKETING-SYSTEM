# Business value — hypotheses, evidence so far, and how to measure it (P16)

**No business result is claimed.** NexaDesk has not been used by a real organization yet, so there
is no measured saving, deflection rate or satisfaction change. This document states where value
is expected, what the evidence collected so far does and does not support, and exactly how each
value would be measured in a pilot.

## 1. The problem being paid for

Internal service desks (IT, facilities, HR operations) lose time in three places: getting a
request to the right person (triage and routing), answering repeat questions, and missing
service-level targets on work that sat unnoticed. The P3 incident log shows the scale of the first
one in a real ServiceNow deployment: on the most recent 3,738 incidents the dispatcher's first
assignment was the resolving group for **67.3%**, and **37.1%** were reassigned at least once
(`reports/routing/p4_routing_uci.json`).

## 2. Value hypotheses and the evidence behind each

| # | Hypothesis | Product mechanism | Evidence so far (source) | What it does *not* show |
|---|---|---|---|---|
| H1 | Less time spent triaging and routing | AI recommendations with confidence; optional auto-apply above a threshold; approval queue | Routing model at confidence ≥ 0.9 handles 16% of real incidents at 93.7% accuracy — the same as the dispatcher on those incidents (92.8%) (`reports/routing/`) | Any time saving; it shows automation *at parity* on a slice, not better routing |
| H2 | Fewer misrouted tickets | Same | Overall the model is *not* better than the dispatcher (65.5% vs 67.3% top-1) | — this hypothesis is **not supported** by current evidence |
| H3 | Fewer repeat tickets (self-service) | Article suggestions while writing a ticket; KB answers with citations | Retrieval finds a true duplicate in the top 10 for 53% of real forum questions (`reports/rag/`) | Whether requesters read articles instead of filing; needs real usage |
| H4 | Fewer SLA breaches | SLA-risk estimate, escalation proposals, SLA monitor | Breach model ROC-AUC 0.76–0.77 on real incidents after recalibration (`reports/sla/`) | Whether earlier warnings change outcomes — only a pilot can show that |
| H5 | Faster, more consistent replies | Reply drafts (template + KB article; LLM when enabled) | None — text generation has not been evaluated (no provider configured) | Everything |
| H6 | Visibility for managers | Live dashboards, AI performance, drift checks | Feature exists and is tested | Business impact |

## 3. How value is measured in a pilot

All from the database, per organization (`docs/pilot_plan.md`):

| Hypothesis | Metric | Comparison |
|---|---|---|
| H1 | median minutes from ticket creation to correct team; agent accept/edit/reject rates | imported pre-pilot history (previous tool) vs pilot period; recommend-only weeks vs auto-apply weeks |
| H2 | share of tickets reassigned after first routing | same |
| H3 | share of requesters who opened a suggested article and did not file within 24 h; "helpful" ratings | pilot organizations with vs without published articles |
| H4 | resolution-SLA breach rate | pre-pilot vs pilot, per priority |
| H5 | minutes from first open to first reply; drafts sent unchanged/edited/discarded | agents with vs without drafts |

## 4. Turning measured activity into money — without inventing it

`python -m app.scripts.value_report --org <slug> --triage-minutes M --reply-minutes R --hourly-cost C`
multiplies the organization's **measured** counts (recommendations accepted or edited, automatic
changes not reverted, drafts sent) by **your** assumptions (minutes each replaces, loaded hourly
cost) and prints every input next to the result. Its output is "work handled with AI assistance",
explicitly not a measured saving, and it refuses to hide that demo or synthetic data is not real.

## 5. What would change the conclusion

* H1/H2: if agents accept ≥ 60% of routing recommendations and reassignment falls versus the
  imported baseline, routing value is real; if acceptance stays < 40%, routing recommendations
  should be switched off for that organization (the pilot's exit criteria).
* H3: deflection needs a knowledge base worth reading — the pilot organization's own articles.
* H4: a lower breach rate with unchanged staffing would be the strongest single result.

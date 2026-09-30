# Security — threat model, controls and evidence (P14)

Scope: the NexaDesk AI web app, API, worker, PostgreSQL, Redis and the single-VM deployment in
`deploy/`. Each threat names its control and the automated test that proves the control; a
threat without a test is listed under residual risks.

## Assets

| Asset | Why it matters |
|---|---|
| Ticket content, comments, attachments | Confidential business and personal data of each organization |
| Knowledge-base documents (internal) | Runbooks may reveal infrastructure details |
| Accounts, sessions, invitation/reset tokens | Account takeover → everything above |
| Organization configuration, AI policy | Changing routing/automation silently misroutes work |
| AI recommendations and decision records | The evidence behind automation and its metrics |
| Secrets (`SECRET_KEY`, DB password, `METRICS_TOKEN`, `LLM_API_KEY`) | Forged tokens, data access, provider spend |

## Trust boundaries

```
Internet ──TLS──► Caddy ──► web (static SPA)
                        └─► backend /api/*  ──► PostgreSQL, Redis (internal network only)
worker ──► PostgreSQL, Redis, SMTP, (optional) LLM provider over HTTPS
Prometheus ──bearer──► backend /metrics, worker :9101   (internal network only)
```

Untrusted: everything a requester or agent types or uploads, every document uploaded to the
knowledge base, and every LLM response.

## Threats, controls, tests

| ID | Threat | Control | Evidence |
|---|---|---|---|
| T1 | SQL injection via search/filter/KB query | ORM + bound parameters everywhere; the only f-string SQL uses fixed fragments (reviewed by Bandit, `nosec` with reason) | `test_threats.py::TestT1Injection` |
| T2 | Stored XSS in tickets/comments/KB/AI text | API returns JSON only with `nosniff` and `default-src 'none'`; the SPA renders text through React escaping — no `dangerouslySetInnerHTML` (CI check); strict CSP on the SPA (nginx) | `TestT2StoredXss`, `frontend/src/security.test.ts` |
| T3 | Malicious uploads (HTML/SVG, polyglots, path traversal, oversize) | Extension allowlist + magic-byte check + UTF-8 check for text; sanitized filenames; downloads are `attachment` with `nosniff`; KB parser rejects non-text documents and runs in the worker | `TestT3Uploads`, `test_comments_attachments.py`, `test_kb.py::TestParsing` |
| T4 | Cross-tenant access (IDOR) incl. vector/KB search | Every query filters by the caller's `tenant_id`; retrieval SQL includes the tenant filter; foreign ids return 404 | `test_tenant_isolation.py`, `TestT4TenantIsolation`, `test_ai.py::TestIsolation`, `test_kb.py::test_search_is_tenant_isolated` |
| T5 | Privilege escalation (role/tenant in requests, self-promotion) | Central permission map; role and tenant come from the database, never from the token or body | `test_rbac.py`, `test_security.py::TestAuditFindings`, `TestT7Tokens::test_role_claim_is_not_trusted` |
| T6 | Mass assignment | Pydantic input schemas list the writable fields; status only changes through the state machine | `TestT6MassAssignment` |
| T7 | Token forgery/replay | HS256 with a ≥ 32-char secret (boot refuses weak/dev keys outside development); 15-min access tokens; rotating httpOnly refresh cookie with reuse detection; `alg=none`, expired, wrong-type tokens rejected | `TestT7Tokens`, `test_auth.py`, `test_security.py::TestProductionConfig` |
| T8 | Credential stuffing / brute force | bcrypt (12 rounds in deployed environments); per-IP rate limits on login, registration, reset (Redis-backed) | `test_security.py` rate-limit test |
| T9 | Prompt injection through tickets or KB documents | Content delimited as data with our delimiters neutralized; system prompts forbid following instructions in data; generated text is never sent or applied without a person; reply drafts never see internal notes; KB answers must cite sources and pass the support check | `test_ai_generative.py`, `test_kb.py::test_document_text_cannot_escape_its_source_block`, `test_uncited_text_is_not_returned_as_an_answer` |
| T10 | AI acting beyond its authority | Agent tools are typed, validated per organization, policy-gated by risk; high-risk actions always need a person; automatic changes are verified and rolled back on mismatch; approvals run with the approver's own permissions | `test_agent.py` |
| T11 | Data sent to third parties without consent | Text generation off unless `LLM_PROVIDER` **and** `LLM_API_KEY` are set; a provider key in the environment is ignored; every call is in the `llm_calls` ledger; per-org token budget | `test_ai_generative.py::test_key_in_environment_alone_does_not_enable_generation` |
| T12 | Operational endpoints exposed (legacy A5 leaked tenant data at `/metrics`) | New `/metrics` has only operational counters, is not routed by Caddy, and requires `METRICS_TOKEN` (boot refuses to start without it when deployed) | `test_security.py::test_a5_metrics_carry_no_tenant_data_and_need_a_token`, `test_metrics_endpoint.py` |
| T13 | Secrets in git | Secrets only in the VM's `.env` (generated by `bootstrap-vm.sh`, mode 600); gitleaks scans history in CI | CI `secret-scan` job, `.gitleaksignore` (reviewed entries only) |
| T14 | Vulnerable dependencies | Fully pinned Python deps; `pip-audit` and `npm audit` in CI; Bandit static analysis | CI `dependency-audit`, `static-analysis` jobs |
| T15 | Clickjacking, MIME confusion, downgrade | `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `nosniff`, HSTS (Caddy + API) | `test_security.py` headers test |
| T16 | Abuse of expensive endpoints (LLM, KB answers, analysis) | Per-user rate limits (20/min), monthly token budget per organization, no model call without relevant evidence | `test_ai_generative.py::test_monthly_budget_is_enforced`, `test_kb.py::test_nothing_relevant_means_no_model_call` |

## Secrets

* Generated on the VM by `deploy/bootstrap-vm.sh`: `SECRET_KEY`, `POSTGRES_PASSWORD`,
  `METRICS_TOKEN`, `GRAFANA_ADMIN_PASSWORD`. `LLM_API_KEY` is entered by the owner if and when
  text generation is enabled.
* **Known exposure:** the pre-rewrite code (commit `d850616`, August 2026, public history) contained
  a hard-coded default JWT key. The current code never reads it and refuses to start in
  staging/production with a weak or default key. That key must be treated as public: any
  deployment that ever ran the legacy code must rotate `SECRET_KEY`. Purging it from public history
  (a force-push that rewrites every commit) is the owner's decision; it is recorded in
  `.gitleaksignore` so CI can still fail on any *new* finding.

## Static analysis and scans (2026-09-30)

| Check | Result |
|---|---|
| Bandit 1.9.4, `app/`, severity ≥ medium | 0 findings after review (3 false positives annotated `nosec` with reasons); 9 low-severity notes |
| gitleaks 8.28 over full git history | 3 findings: 2 test-fixture passwords, 1 legacy key (above) — all reviewed |
| `pip-audit` / `npm audit --omit=dev` | run in CI on every push |

## Residual risks

* No web application firewall or bot protection beyond per-IP rate limits (single VM).
* Rate limiting is per IP; users behind one NAT share a budget.
* Attachments are not malware-scanned (allowlist + magic bytes only).
* Prompt-injection defenses reduce but cannot eliminate manipulation of *generated text*; this is
  why generated text is never applied or sent without a person.
* No independent penetration test has been performed.

# Architecture diagrams

These diagrams describe the checked-in modular-monolith design and deployment configuration.
The production topology is prepared but is not yet running at a public URL.

## Ticket lifecycle

```mermaid
stateDiagram-v2
    [*] --> submitted
    submitted --> triaged
    triaged --> assigned
    assigned --> acknowledged
    acknowledged --> in_progress
    in_progress --> waiting_for_customer
    waiting_for_customer --> in_progress
    in_progress --> escalated
    escalated --> in_progress
    in_progress --> resolved
    resolved --> closed
    resolved --> reopened
    closed --> reopened
    reopened --> triaged
```

Each accepted transition writes status history and an audit record with actor/source and reason.
The service state machine and role permissions remain authoritative.

## AI recommendation pipeline

```mermaid
flowchart LR
    T[New ticket] --> R[Deterministic rules]
    T --> E[Text embedding]
    E --> V[Same-tenant resolved-ticket search]
    V --> C[Category / priority votes]
    V --> D[Duplicate candidates]
    T --> S[SLA and resolution features]
    R --> X[Evidence and confidence]
    C --> X
    D --> X
    S --> X
    X --> P[Policy and confidence gate]
    P -->|low confidence / protected action| H[Human review]
    P -->|recommendation| A[Agent decision]
    H --> A
    A --> L[Persist prediction, decision and audit]
```

## Knowledge retrieval and answer flow

```mermaid
flowchart LR
    F[PDF / DOCX / MD / HTML / text] --> P[Parse and clean]
    P --> K[Chunk with heading metadata]
    K --> I[Embed and index with tenant id]
    Q[Question + caller scope] --> S[Dense search + lexical fallback]
    I --> S
    S --> G{Evidence above floor?}
    G -->|No| N[No answer / relevant passages]
    G -->|Yes| L[Optional provider with source blocks]
    L --> C[Citation and support validation]
    C --> O[Answer with citations and confidence]
```

## Bounded agent workflow

```mermaid
sequenceDiagram
    participant U as User / ticket event
    participant P as Deterministic playbook
    participant T as Typed authorized tools
    participant G as Guard / verifier
    participant H as Human approver
    participant D as Database and audit
    U->>P: Request analysis
    P->>T: Read-only evidence calls
    T->>D: Tenant-scoped reads
    D-->>T: Ticket, SLA and KB evidence
    T-->>P: Typed results
    P->>G: Proposed action + evidence
    G->>D: Validate role, tenant, state and policy
    alt High impact or low confidence
        G->>H: Queue recommendation for review
        H->>D: Approve, modify or reject
    else Allowed recommendation
        G->>D: Apply permitted action / persist recommendation
    end
    D-->>U: Audited outcome
```

## Deployment topology

```mermaid
flowchart TB
    B[Browser] -->|HTTPS| C[Caddy reverse proxy]
    C -->|static assets| W[nginx frontend]
    C -->|REST + WebSocket| A[FastAPI API processes]
    A --> PG[(PostgreSQL + pgvector)]
    A -. optional fail-open .-> R[(Redis)]
    J[Worker process] --> PG
    J -. pub/sub .-> R
    A --> O[stdout JSON / Prometheus]
    J --> O
    O --> M[Prometheus + Grafana profile]
```

## Observability flow

```mermaid
flowchart LR
    API[API request middleware] --> LOG[Structured logs + request id]
    API --> MET[Route-template counters and latency]
    WORKER[Background worker] --> JOB[Job outcomes and backlog]
    AI[AI / KB / human decisions] --> DB[(Telemetry tables)]
    DB --> SCRAPE[Metrics scrape gauges]
    MET --> PROM[Prometheus]
    JOB --> PROM
    SCRAPE --> PROM
    PROM --> GRAF[Grafana dashboards]
    PROM --> ALERT[Alert rules]
    API -. optional scrubbed errors .-> SENTRY[Sentry-compatible DSN]
    WORKER -. optional scrubbed errors .-> SENTRY
```

## CI/CD flow

```mermaid
flowchart LR
    PUSH[Push / pull request] --> SECRET[Secret scan]
    PUSH --> LINT[Lint, type and static security checks]
    PUSH --> TEST[SQLite tests + coverage]
    PUSH --> PG[PostgreSQL tests + migrations]
    PUSH --> WEB[Frontend lint, type, unit tests, build]
    LINT --> E2E[Playwright acceptance]
    TEST --> E2E
    WEB --> E2E
    PG --> IMG[Container build and compose smoke]
    WEB --> IMG
    E2E --> IMG
    IMG --> RELEASE[Commit-SHA image]
    RELEASE --> APPROVAL[Protected deploy environment]
    APPROVAL --> DEPLOY[Backup, migrate, deploy, smoke]
    DEPLOY -->|failure| ROLLBACK[Restore previous image]
```

The deployment step only runs after owner-managed host credentials and protected environment
approval are configured. PostgreSQL, container, and public network verification must be performed
against the actual deployment target.

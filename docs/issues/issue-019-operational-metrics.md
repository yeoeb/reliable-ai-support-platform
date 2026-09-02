# Engineering Issue #019 — Operational Metrics / Monitoring Foundation

<!-- codex-dispatch-supervisor-approved-through: CP1 -->
<!-- codex-dispatch-write-allow: ["requirements/base.txt","app/core/metrics.py","app/api/routes/metrics.py","app/api/middleware/request_logging.py","app/main.py","app/services/rag.py","app/services/agent.py","tests/test_metrics.py","tests/test_request_metrics.py","tests/test_ai_metrics.py","tests/test_metrics_api.py","docs/issues/issue-019-operational-metrics.md"] -->

## GitHub Tracking

- GitHub Issue: #85
- Engineering Issue ID: #019
- Branch: `feature/issue-019-operational-metrics`

## Goal

Add a bounded Prometheus-compatible Operational Metrics foundation.

Metrics must remain:

- aggregate;
- low-cardinality;
- non-sensitive;
- best-effort;
- additive to Logs/Audit;
- independent from Product DB / OpenAI / Tool / Approval execution at scrape time.

## Required Reading

Before CP2 edits:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- GitHub Issue #85
- this execution note
- `app/core/logging.py`
- `app/api/middleware/request_logging.py`
- `app/core/request_context.py`
- `app/main.py`
- `app/core/config.py`
- `app/services/rag.py`
- `app/services/agent.py`
- `app/services/tool_execution.py`
- `app/services/approval.py`
- `tests/test_request_logging.py`
- `tests/test_rag_service.py`
- `tests/test_agent_service.py` when present
- `requirements/base.txt`
- `.github/workflows/backend-tests.yml` read-only

## CP0 — Observability / Metric Surface Inventory

Status: **completed by Supervisor**

Findings:

1. Structured JSON application logging already exists.
2. Request Logging middleware already owns:
   - server-generated Request ID;
   - request start time;
   - resolved route template;
   - response status;
   - exception path;
   - duration.
3. Request lifecycle logging excludes raw Body, Query, Authorization/Cookie, and unmatched raw paths.
4. Durable Audit Events are separate from runtime Logs.
5. RAG already exposes bounded operation status plus input/output token counts.
6. Agent results already expose:
   - completed / approval_required state;
   - aggregate input/output tokens.
7. Tool/Approval already have durable Audit/structured logs; they do not need per-ID metrics in V1.
8. No metrics package, CollectorRegistry, scrape endpoint, Counter, or Histogram currently exists.
9. No current Prometheus/OpenTelemetry dependency exists.
10. Backend Verification installs `requirements/dev.txt`, which includes `base.txt`; a new runtime metrics dependency will be exercised automatically.
11. Existing GitHub workflow path filters already include `app/**`, `tests/**`, and `requirements/**`; no workflow edit is required.
12. `compose.yaml` currently runs only PostgreSQL; #019 does not deploy a Prometheus server.

No contradiction was found.

## CP1 — Low-Cardinality Prometheus Metrics Architecture

Status: **completed and Supervisor-approved**

### Dependency

Add:

```text
prometheus-client>=0.20,<1.0
```

to `requirements/base.txt`.

Do not add Grafana / Prometheus server / OpenTelemetry packages in #019.

### Metrics Registry

Create:

`app/core/metrics.py`

Use a dedicated custom `CollectorRegistry`.

Do not use the library's global default registry.

Provide an `ApplicationMetrics` class so tests can instantiate isolated registries.

Provide a process-wide singleton:

`application_metrics`

### Metric 1 — HTTP Requests

Name:

`reliable_ai_http_requests_total`

Labels:

- `method`
- `route`
- `status_class`

Allowed method normalization:

- GET
- POST
- PUT
- PATCH
- DELETE
- OPTIONS
- HEAD
- TRACE
- everything else → `OTHER`

Route:

- server-owned template only;
- unmatched → `<unmatched>`;
- never raw request path;
- skip the `/metrics` route entirely.

Status:

- 1xx
- 2xx
- 3xx
- 4xx
- 5xx
- unknown

### Metric 2 — HTTP Duration

Name:

`reliable_ai_http_request_duration_seconds`

Labels:

- `method`
- `route`

Suggested explicit buckets:

```text
0.005
0.01
0.025
0.05
0.1
0.25
0.5
1.0
2.5
5.0
10.0
```

No status label.

### Metric 3 — AI Operation Outcomes

Name:

`reliable_ai_operations_total`

Labels:

- `operation`
- `outcome`

V1 allowed pairs:

```text
rag_answer / grounded
rag_answer / insufficient_evidence
rag_answer / provider_failure

agent_run / completed
agent_run / approval_required
```

Reject/ignore invalid internal label pairs without creating a new series.

Do not allow arbitrary caller/user/provider strings to become labels.

### Metric 4 — Aggregate LLM Tokens

Name:

`reliable_ai_llm_tokens_total`

Labels:

- `operation`
- `direction`

Allowed:

```text
rag_answer / input
rag_answer / output
agent_run / input
agent_run / output
```

Token amount must be a non-negative integer.

Do not label by model/provider/user/tool/request/document.

### Metrics Best-Effort Boundary

Metrics must never become a Product availability dependency.

Public recording methods should be best-effort.

If Prometheus recording unexpectedly fails:

- preserve Product request/result/exception;
- emit at most a bounded warning log;
- warning fields may include only fixed metric category, never request content;
- do not recursively include raw exception messages from untrusted input.

Tests must prove instrumentation failure cannot turn a normal 200 into a 500.

### HTTP Instrumentation

Reuse `RequestLoggingMiddleware`.

Do not introduce a second request timing middleware.

Extend its constructor with an injectable metrics object for focused tests, defaulting to `application_metrics`.

On success:

1. compute existing duration;
2. log existing lifecycle event unchanged;
3. best-effort record metric unless route is `/metrics`.

On exception:

1. compute existing duration;
2. log existing failure event unchanged;
3. best-effort record HTTP metric with status class derived from actual status when known, otherwise `unknown`;
4. re-raise original exception.

The metrics call must not change Request ID behavior.

### Scrape Endpoint

Create:

`app/api/routes/metrics.py`

Endpoint:

`GET /metrics`

Properties:

- `include_in_schema=False`;
- no authentication dependency;
- no DB dependency;
- no OpenAI dependency;
- no Tool/Approval dependency;
- uses `generate_latest(application_metrics.registry)`;
- correct Prometheus exposition Content-Type.

Register the router in `app/main.py`.

Security note belongs in docs/tests:

The endpoint is intentionally JWT-free for scraper compatibility and must be network-restricted by deployment infrastructure in production.

Only low-cardinality aggregate metrics may be exposed.

### Default Registry Boundary

Because a custom registry is used, `/metrics` should not include automatically registered default process/python metrics such as:

- `python_gc_*`
- `process_*`

unless a future Issue explicitly reviews/permits them.

### RAG Instrumentation

Reuse existing `RagService._record_outcome`.

Best-effort record:

```text
operation = rag_answer
outcome = status
```

Allowed status values already map to:

- grounded
- insufficient_evidence

Provider failure path records:

- provider_failure

Token totals:

- grounded / generated insufficient-evidence Provider result:
  - add Provider input tokens;
  - add Provider output tokens.
- zero-retrieval path:
  - operation outcome only;
  - zero tokens do not need to increment counters.
- provider failure:
  - no token increment unless valid token usage is available before failure; V1 does not infer missing usage.

Do not label metrics with:

- question
- answer
- citation
- source/chunk/document
- model
- Request ID
- actor user ID.

### Agent Instrumentation

Record one `agent_run` metric per successful `AgentRunResult`.

Outcomes:

- `completed`
- `approval_required`

For both:

- add aggregate input tokens;
- add aggregate output tokens.

A completed Tool run still records only `agent_run/completed`, not the Tool name.

Direct answer and Tool-finalized answer intentionally share the same outcome metric in V1.

HTTP status metrics cover Agent route failures; #019 does not add high-cardinality exception labels.

A small private helper that constructs/records `AgentRunResult` is acceptable if it reduces duplication without changing API semantics.

### Label Privacy Invariant

Metric labels must never contain:

- Request ID
- user ID
- approval ID
- document ID
- chunk ID
- raw path
- query/body
- Prompt/question/answer
- citation content
- Tool arguments
- exception message
- model/provider response
- access token/API key/secret.

### Focused Tests

#### `tests/test_metrics.py`

Prove:

- isolated custom registry;
- reviewed metric families only;
- no `python_gc_` / `process_`;
- method/status normalization;
- invalid AI labels do not create series;
- token validation;
- exposition bytes are deterministic enough for contract assertions.

#### `tests/test_request_metrics.py`

Use an isolated `ApplicationMetrics` instance.

Prove:

- two concrete item IDs use one route-template series;
- raw IDs absent;
- query/auth/body/cookie absent;
- unmatched route is `<unmatched>`;
- status class grouping;
- unknown method → OTHER;
- `/metrics` is excluded from Product HTTP metric recording;
- metrics-record failure does not alter successful response;
- existing Request ID still works.

#### `tests/test_ai_metrics.py`

Monkeypatch service-level metrics singleton with isolated/mock recorder.

Prove:

- RAG grounded outcome + token totals;
- RAG zero evidence outcome, Provider not called, no token increment;
- RAG provider failure outcome;
- Agent completed outcome + token totals;
- Agent approval_required outcome + token totals;
- no sensitive content passed to metric recording API.

#### `tests/test_metrics_api.py`

Prove:

- GET /metrics = 200;
- Prometheus Content-Type;
- hidden from OpenAPI;
- no Product auth required;
- no known configured/synthetic secret appears;
- no default process/python families.

### Existing Test Preservation

The following behavior must remain unchanged:

- RequestLogging middleware tests
- RAG tests
- Agent tests
- Audit behavior
- AI Security Regression
- Offline Eval
- database recovery/Alembic.

### CP2 Ordered Slices

1. add prometheus-client dependency
2. ApplicationMetrics custom registry
3. HTTP metric recording in existing middleware
4. /metrics route + main wiring
5. RAG outcome/token instrumentation
6. Agent outcome/token instrumentation
7. focused metrics tests

Do not run full repository regression in CP2.

CP3 owns full regression.

### Initial Write Scope

Only the machine-readable Allowlist at the top is authoritative.

No migration, model, repository, DB schema, Docker Compose, or GitHub workflow change is authorized.

## Out of Scope

- Prometheus server deployment
- Grafana
- Alertmanager
- OpenTelemetry / distributed tracing
- external log aggregation
- alert/SLO configuration
- auth proxy/network policy implementation
- process/default registry metrics
- per-user/request/document/Approval metrics
- Tool-name labels
- model-name labels
- arbitrary exception labels
- database polling gauges
- business dashboards
- workflow edits.

## Checkpoints

- [x] CP0 — Observability / metric-surface inventory
- [x] CP1 — Low-cardinality Prometheus metrics architecture
- [ ] CP2 — Bounded implementation
- [ ] CP3 — Verification / cardinality & failure regression
- [ ] CP4 — Observability / security review
- [ ] CP5 — Knowledge / documentation
- [ ] CP6 — exact-Head delivery

## Current State

CP0 and CP1 are complete.

Remote Supervisor approval: **CP1**.

Next authorized action: **CP2** on `feature/issue-019-operational-metrics`.

Full repository regression remains CP3.


## Supervisor Fallback Execution

The remote CP2 gate remained authorized but no Local Watcher/Codex checkpoint was published after repeated remote checks.

A bounded Supervisor fallback is being used on the Feature Branch.

Control boundaries preserved:

- writes remain inside the existing #019 machine Allowlist;
- no migration / DB model / Docker Compose / GitHub workflow change;
- no fake `checkpoint(issue-019): CP2` commit;
- CP3 full GitHub-hosted regression remains mandatory;
- CP4 cardinality/security review remains mandatory;
- CP6 exact-Head delivery remains mandatory.

Fallback CP2 implements:

- `prometheus-client>=0.20,<1.0`;
- dedicated custom `CollectorRegistry`;
- bounded HTTP Counter + latency Histogram;
- fixed AI operation outcomes;
- aggregate LLM input/output token counters;
- low-cardinality normalization;
- best-effort metrics recording;
- instrumentation inside the existing RequestLoggingMiddleware;
- public `GET /metrics` hidden from OpenAPI;
- `/metrics` self-scrape exclusion;
- RAG outcome/token instrumentation;
- Agent outcome/token instrumentation;
- focused Registry / HTTP / AI / Endpoint tests.

No full regression is represented as executed by the Supervisor fallback environment.

Remote approval remains CP1 until CP2 review is complete.

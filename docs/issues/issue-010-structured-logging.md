# Engineering Issue #010 — Structured Logging / Request Correlation

<!-- codex-dispatch-supervisor-approved-through: CP1 -->
<!-- codex-dispatch-write-allow: [".env.example","app/core/logging.py","app/core/request_context.py","app/api/middleware/__init__.py","app/api/middleware/request_logging.py","app/main.py","app/core/config.py","app/services/user.py","app/services/rbac.py","app/services/audit.py","app/api/dependencies/auth.py","app/api/dependencies/authorization.py","tests/test_logging.py","tests/test_request_logging.py","tests/test_config.py","docs/issues/issue-010-structured-logging.md"] -->

## GitHub Tracking

- GitHub Issue: #44
- Engineering Issue ID: #010
- Branch: `feature/issue-010-structured-logging`

## Goal

Establish machine-readable runtime Application Logging and server-generated HTTP Request Correlation without changing the durable Audit Trail delivered in Engineering #009.

## Why Now

Authentication, RBAC, Audit Logging, and reproducible Backend CI are complete.

Before RAG and Tool Calling add additional runtime components, the Backend needs a stable Observability contract so one HTTP request can be traced across Application Logs without relying on free-form strings.

## Dependencies

Completed:

- #007 Authentication
- #008 RBAC
- #009 Durable Security Audit Trail
- Backend PostgreSQL Verification CI
- Supervisor / Dispatcher / Watcher Control Plane
- fail-closed remote Issue Branch Resolver

## Required Reading

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- GitHub Issue #44
- `app/main.py`
- `app/core/config.py`
- `app/services/user.py`
- `app/services/rbac.py`
- `app/services/audit.py`
- `app/api/dependencies/auth.py`
- `app/api/dependencies/authorization.py`
- `app/api/routes/health.py`
- `tests/test_config.py`
- relevant Auth/RBAC/Audit tests

## CP0 — Context Bootstrap

Status: **completed by Supervisor**

Findings:

1. Application logging already uses Python stdlib `logging` in User, RBAC, Audit, Authentication, and Authorization paths.
2. Existing events encode structure inside message strings such as `event=... key=value`.
3. There is no central JSON formatter or `app` logger configuration.
4. There is no HTTP Request ID or ContextVar correlation.
5. There is no request lifecycle log middleware.
6. `audit_events` is already the durable security/accountability trail and must remain separate from runtime Application Logs.
7. Current settings do not expose a Log Level.
8. No OpenTelemetry / Prometheus / ELK dependency is required to meet the V1 contract.
9. Request logging must not capture raw path/query/header/body data because those surfaces may contain secrets or PII.
10. A pure ASGI middleware is preferred over a request helper that depends on mutable chat/session state.

No Product contradiction was found.

## CP1 — Architecture / Scope Validation

Status: **completed and approved by Supervisor**

### Runtime Logging Architecture

Approved flow:

```text
HTTP request
    ↓
RequestLoggingMiddleware
    ↓
server UUID request_id
    ↓
ContextVar
    ↓
FastAPI / Service / Repository work
    ↓
app.* LogRecord
    ↓
JsonFormatter
    ↓
one-line JSON on stdout
```

### Base JSON Contract

Every record emitted through the configured `app` logger hierarchy must contain:

- `timestamp` — UTC ISO-8601
- `level`
- `logger`
- `message`
- `event` — null when the caller did not provide one
- `request_id` — current ContextVar value or null

JSON serialization must preserve booleans/numbers when practical and safely stringify values such as UUIDs.

### Structured Event Fields

Existing logger calls in Scope should stop embedding key/value data into `message`.

Example target shape:

```python
logger.info(
    "RBAC role assigned",
    extra={
        "event": "rbac.role.assigned",
        "user_id": str(user.id),
        "role": role.name,
        "changed": created,
    },
)
```

Stable semantic event names should be preserved.

### Sensitive Structured Fields

The formatter must redact known sensitive structured keys, case-insensitively, including variants of:

- password / password_hash
- token / access_token
- authorization
- cookie
- secret / jwt_secret
- api_key
- database_url / connection_string

Redaction applies to structured fields.

It does **not** make arbitrary free-form `message` content safe; callers remain prohibited from logging secrets in messages.

### Request Context

Use `ContextVar[str | None]`.

Required behavior:

1. Middleware generates a UUID for each HTTP request.
2. Set ContextVar and retain the returned token.
3. Application logs during the request resolve the same Request ID.
4. Add `X-Request-ID` to the HTTP response.
5. Reset the ContextVar in `finally`.
6. Never trust or reuse client-supplied `X-Request-ID` in V1.

### Middleware Design

Prefer a pure ASGI middleware so Request ID setup/reset surrounds the full application call.

It may wrap `send` to:

- capture response status;
- append `X-Request-ID` on `http.response.start`.

After request handling, emit:

- event: `http.request.completed`
- `http_method`
- `route`
- `status_code`
- `duration_ms`

Route field must prefer the resolved route template (for example `/users/{user_id}`) and must use a stable placeholder such as `<unmatched>` when no route exists.

Do **not** fall back to raw `scope["path"]`.

If an unhandled exception escapes:

- emit `http.request.failed`;
- include exception **type** only;
- do not include arbitrary exception text;
- re-raise the original exception.

### Logging Configuration

Add a central configuration function using Python stdlib `logging`.

Requirements:

- configure `logging.getLogger("app")`;
- stdout `StreamHandler`;
- JSON formatter;
- configured Log Level;
- `propagate = False` for the application hierarchy root;
- repeated configuration must not duplicate owned handlers.

Do not globally destroy unrelated/root handlers.

### Settings

Add:

```text
LOG_LEVEL=INFO
```

Default must remain INFO when the environment variable is absent.

Invalid values must fail explicitly or normalize through one documented rule; do not silently enable DEBUG.

### Audit Boundary

Do not:

- change `AuditEvent` schema;
- change Audit transaction rules;
- persist Application Logs to `audit_events`;
- remove existing Audit calls because a runtime Log now exists.

Application Log and Audit Event may represent related incidents but serve different purposes.

## Scope

- central JSON Application Logging configuration
- Request ContextVar
- HTTP correlation/lifecycle middleware
- FastAPI wiring
- `LOG_LEVEL` setting and env example
- conversion of existing in-scope application log calls to structured fields
- focused Unit/API tests
- Issue execution evidence

## Dispatcher Publish Allowlist

Machine-controlled CP2/CP3 publication is limited to the exact remote `codex-dispatch-write-allow` marker.

Notably, `docs/PROJECT_STATE.md` and `README.md` are **not** machine-writable through the Dispatcher because project-wide state synchronization remains Supervisor-controlled.

## Out of Scope

- OpenTelemetry
- distributed tracing
- Prometheus/metrics
- ELK/Loki/Datadog
- log shipping/retention
- Application Log database table
- Audit schema/transaction changes
- client-controlled Request ID
- Client IP / User-Agent
- raw Request Body
- raw Query String
- Authorization/Cookie header capture
- changing Uvicorn access-log internals
- deployment-specific collectors

## Acceptance Criteria

Use GitHub Issue #44 as the authoritative checklist.

## Known Risks

### Context Leakage

A missing ContextVar reset could attach one request's ID to a later request.

### Sensitive Data

Blind serialization of Request/Headers/Query/Body or arbitrary LogRecord fields could leak secrets.

### Cardinality

Logging raw paths such as `/users/<uuid>` creates high-cardinality/PII-prone fields; route templates are required.

### Duplicate Logging

Repeated logging initialization could stack handlers and duplicate every event.

### Audit Confusion

Runtime logging must not weaken or replace durable Audit Events.

### Exception Leakage

Logging `str(exc)` may expose query/credential/request data; use exception type only in the request failure event.

## Checkpoints

- [x] CP0 — Context bootstrap / contradiction detection
- [x] CP1 — Architecture + Scope validation
- [ ] CP2 — Bounded implementation
- [ ] CP3 — Targeted + full verification
- [ ] CP4 — Security / observability review
- [ ] CP5 — Knowledge + documentation sync
- [ ] CP6 — PR delivery evidence

## CP2 Ordered Slices

Codex may implement these in one CP2 turn, preserving the order:

1. **Context foundation**
   - `app/core/request_context.py`
   - set/get/reset helpers or equivalent bounded API

2. **JSON logging foundation**
   - `app/core/logging.py`
   - stable base fields
   - structured extra fields
   - sensitive-key redaction
   - idempotent `app` logger configuration

3. **Settings**
   - `LOG_LEVEL`
   - `.env.example`
   - config tests

4. **HTTP correlation middleware**
   - server-generated UUID
   - response header
   - completion/failure event
   - route-template safety
   - ContextVar reset

5. **Application wiring**
   - configure logging
   - add middleware

6. **Existing event migration**
   - User Service
   - RBAC Service
   - Audit Service
   - Auth dependency
   - Authorization dependency

7. **Focused tests**
   - JSON structure
   - redaction
   - idempotent handlers
   - request ID lifecycle/isolation
   - route-template behavior
   - sensitive HTTP input exclusion
   - existing Audit/RBAC/Auth regressions remain intact

Do not modify Product files outside the remote write Allowlist.

## CP3 Verification Contract

At minimum:

```powershell
python -m pytest -q tests/test_logging.py tests/test_request_logging.py tests/test_config.py
python -m pytest -q tests/test_auth.py tests/test_auth_dependency.py tests/test_authorization_dependency.py tests/test_admin_rbac.py tests/test_rbac_service.py tests/test_audit_integrations.py
python -m pytest -q
```

GitHub-hosted Backend Verification remains authoritative if the local Python environment is unavailable.

## Knowledge Candidates

Do not create new Notion entries during CP2.

Potential CP5 candidates, deduplicated first:

- Structured Logging vs Audit Logging
- Request Correlation / Correlation ID
- Python ContextVar for request-scoped context
- Log redaction boundary
- route template vs raw path cardinality

## Current State

CP0 and CP1 are complete.

Supervisor remote approval is **CP1**, which authorizes CP2.

The next Executor action is bounded CP2 implementation through the Dispatcher/Watcher.

Do not begin CP3 until the Supervisor reviews the CP2 diff.

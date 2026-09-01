# Engineering Issue #009 — Durable Security Audit Trail

<!-- codex-dispatch-supervisor-approved-through: CP1 -->

## GitHub Tracking

- GitHub Issue: #16
- Engineering Issue ID: #009
- Branch: `feature/issue-009-audit-logging`

## Goal

Add a durable, structured Audit Trail for Authentication, Authorization denial, and RBAC privilege-change events without changing existing `401/403` semantics or exposing sensitive data.

## Why Now

Authentication and RBAC are already implemented.

Current Security Events are transient Python Application Logs. Before RAG and Tool Calling are introduced, the platform needs a persistent Security Event Trail that later AI/tool actions can reuse.

## Dependencies

Completed:

- #007 Authentication
- #008 RBAC
- Agent workflow bootstrap
- Local Codex Dispatcher

## Required Reading

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/codex-dispatcher.md`
- GitHub Issue #16
- `app/api/routes/auth.py`
- `app/api/routes/admin.py`
- `app/api/dependencies/auth.py`
- `app/api/dependencies/authorization.py`
- `app/services/auth.py`
- `app/services/rbac.py`
- `app/repositories/rbac.py`
- `app/db/base.py`
- `app/models/__init__.py`
- `migrations/env.py`
- relevant Authentication / Authorization / RBAC tests

## CP0 — Context Bootstrap

Status: **completed by Supervisor**

Findings:

1. Existing transient Security Logs already include:
   - `auth.token.invalid`
   - `authorization.denied`
   - `rbac.role.assigned`
   - `rbac.role.removed`
   - RBAC persistence-failure logs

2. There is no durable `audit_events` table, ORM Model, Repository, or Audit Service.

3. `RBACService` currently owns the Commit/Rollback boundary for Role assignment/removal. This is the correct place to make privilege mutation + Audit insert atomic.

4. `require_permission()` already has the current User ID and Permission name, so it is the correct Authorization-denied integration point.

5. `get_current_user()` already has the DB Session and token validation boundary, so invalid/inactive Authentication events can be recorded there without exposing the token.

6. `login()` owns Login success/failure HTTP behavior and can record generic Authentication Audit Events without storing submitted Password or Email.

7. No Audit read/search HTTP API currently exists. It remains Out of Scope.

8. SQLAlchemy Declarative reserves the Model attribute name `metadata`. The DB column may be named `metadata`, but the Python attribute must use another name such as `event_metadata`.

9. User UUID fields in Audit records should not use cascading foreign-key deletion that could erase history.

10. OWASP guidance supports recording Authentication successes/failures, Authorization failures, and privilege-administration events while excluding Tokens, Passwords, Secrets, and other sensitive data.

No contradiction was found between `AGENTS.md`, `PROJECT_STATE.md`, merged Authentication/RBAC code, and Issue #16.

## CP1 — Architecture / Plan Validation

Status: **completed and approved by Supervisor**

The following plan is the approved CP2 contract:

### Data Model

`audit_events`:

- `id: UUID`
- `actor_user_id: UUID | None`
- `action: str`
- `target_type: str`
- `target_id: str | None`
- `outcome: str`
- `occurred_at: datetime(timezone=True)`
- DB column `metadata: JSONB`, Python attribute `event_metadata`

Suggested indexes:

- `occurred_at`
- `actor_user_id`
- `action`

No Update/Delete Repository methods.

### Event Vocabulary

Suggested stable Actions:

- `auth.login`
- `auth.token.invalid`
- `auth.user.invalid`
- `authorization.permission.denied`
- `rbac.role.assign`
- `rbac.role.remove`

Suggested Outcomes:

- `success`
- `failure`
- `denied`

### Service / Repository Boundary

Approved shape:

```text
AuditRepository.create(...)
    ↓
session.add(AuditEvent)
session.flush()
    ↓
NO commit inside Repository
```

`AuditService` exposes two semantics:

1. **Transaction-participating insert**
   - adds/flushed Audit Event
   - does not commit
   - caller owns the surrounding transaction
   - used by RBAC privilege mutation

2. **Best-effort record**
   - adds/flushed Audit Event
   - commits its own request-scoped Audit write
   - on SQLAlchemy persistence failure: rollback + Application Log
   - does not re-raise into the original `401/403` path
   - used by Login/Auth/Authorization failure paths

Do not hide Commit inside `AuditRepository`.

### RBAC Transaction Policy

For Role assignment/removal:

```text
validate target User / Role
        ↓
mutate UserRole
        ↓
insert AuditEvent
        ↓
single session.commit()
```

If Audit insert/persistence fails:

```text
session.rollback()
→ no unaudited privilege mutation
```

The route must pass the acting administrator's User ID into the RBAC Service.

### Best-effort Authentication / Authorization Policy

For events whose primary result is a `401/403`:

```text
primary security decision
        ↓
attempt Audit insert + commit
        ↓
Audit failure?
    ├─ rollback failed Audit transaction
    ├─ Application Log audit persistence failure
    └─ preserve original 401/403
```

Do not let Audit persistence failure replace the intended security response with an unrelated `500`.

### Integration Points

Approved integration:

- `app/api/routes/auth.py::login`
  - successful Login → `auth.login / success`, actor = authenticated User ID
  - invalid credentials → `auth.login / failure`, actor = null, generic reason only
- `app/api/dependencies/auth.py::get_current_user`
  - invalid/expired Token → `auth.token.invalid / failure`, actor = null
  - decoded Token pointing to missing/inactive User → `auth.user.invalid`, stable User UUID may be used
  - missing Authorization header is not required to be audited in #009
- `app/api/dependencies/authorization.py::require_permission`
  - denied Permission → `authorization.permission.denied / denied`
- `app/api/routes/admin.py`
  - pass acting Administrator User ID into `RBACService`
- `app/services/rbac.py`
  - UserRole mutation + Audit Event + one Commit

### Model / Migration Details

- No Foreign Key from `audit_events.actor_user_id` to `users.id` in #009; preserve historical identifier even if User lifecycle changes later.
- `target_id` remains String so later Tool / Document / Ticket targets can reuse the same table.
- PostgreSQL `JSONB` is acceptable because this Project already targets PostgreSQL.
- Python ORM attribute: `event_metadata`; DB column: `metadata`.
- Import `AuditEvent` from `app/models/__init__.py`; `migrations/env.py` should only change if Alembic metadata discovery actually requires it.
- Repository exposes Create only.

### CP2 Ordered Implementation Slices

Codex may implement these in one CP2 Turn, but must preserve this order:

1. **Persistence foundation**
   - `AuditEvent` ORM Model
   - Model export
   - Alembic migration
   - Model / migration tests

2. **Audit boundary**
   - `AuditRepository.create`
   - `AuditService` transaction-participating + best-effort semantics
   - focused Unit Tests

3. **RBAC atomic integration**
   - actor User ID passed from Admin routes
   - Role assignment/removal + Audit in one Transaction
   - rollback behavior tests

4. **Authentication / Authorization best-effort integration**
   - Login success/failure
   - invalid Token / invalid User
   - Permission denied
   - preserve existing 401/403 semantics
   - sensitive-data negative tests

5. **Documentation state**
   - update this Execution Note only with actual CP2 evidence/current state
   - do not mark CP3/CP4 complete

If any slice requires a Production file outside Allowed Write Set, stop and report the Scope expansion instead of silently editing it.

### Sensitive Data Policy

Audit calls/records must never contain:

- submitted Password
- Password Hash
- Access Token
- Authorization Header
- JWT Secret
- Database Password / URL
- API Key
- arbitrary Request Body
- submitted Login Email on failed Login in #009

Failed Login metadata should use a generic reason such as `invalid_credentials`.

## Scope

- Audit ORM Model
- Audit Repository
- Audit recording Service/boundary
- Alembic migration
- Authentication integration
- Authorization-denied integration
- RBAC privilege-mutation integration
- focused Tests
- relevant Project documentation sync

## Allowed Write Set

- `app/models/audit_event.py`
- `app/models/__init__.py`
- `app/repositories/audit.py`
- `app/services/audit.py`
- `app/services/rbac.py`
- `app/api/routes/auth.py`
- `app/api/routes/admin.py`
- `app/api/dependencies/auth.py`
- `app/api/dependencies/authorization.py`
- `migrations/env.py` only if required for metadata discovery
- one new `migrations/versions/*audit*.py`
- focused `tests/test_audit_*.py`
- existing Auth/RBAC tests only where integration expectations must change
- this file
- `docs/PROJECT_STATE.md`
- `README.md` only if completion status requires synchronization

Additional Production files require Scope expansion.

## Out of Scope

- Audit read/search HTTP API
- Update/Delete Audit API
- DB immutable Trigger
- cryptographic Tamper Evidence
- retention policy
- SIEM export
- IP / User-Agent collection
- Request ID / Correlation ID middleware
- RAG
- Embeddings
- Tool Calling
- Human Approval
- RBAC policy redesign
- JWT authorization redesign

## Acceptance Criteria

Use GitHub Issue #16 as the authoritative Acceptance Criteria.

## Checkpoints

- [x] CP0 — Context bootstrap / contradiction detection
- [x] CP1 — Architecture + implementation plan validation
- [ ] CP2 — Bounded implementation
- [ ] CP3 — Targeted + regression verification
- [ ] CP4 — Diff / security / transaction review
- [ ] CP5 — Knowledge + documentation synchronization
- [ ] CP6 — PR delivery evidence

## Commands / Evidence

### CP0

Repository state inspected from current `develop`.

No Product Code modified.

### CP1

Supervisor performed the Architecture / Scope / Transaction review against the current GitHub Branch and approved CP1 without requiring a separate Local Codex planning Turn.

This is intentionally allowed: Supervisor approval is the progression authority, while Local Codex State is only execution/session metadata.

### CP2 — First Product Code Dispatcher command

After synchronizing the local Branch:

```powershell
git fetch origin
git switch feature/issue-009-audit-logging
git pull --ff-only origin feature/issue-009-audit-logging

python scripts/codex_dispatch.py --issue 009 --checkpoint CP2 --dry-run
python scripts/codex_dispatch.py --issue 009 --checkpoint CP2
```

The remote Supervisor Marker is now approved through CP1, so CP2 is authorized.

CP2 uses `workspace-write` and must stop before CP3.

## Knowledge Candidates

Existing Notion Knowledge already covers the Audit Logging fundamentals.

Potential additions after implementation (CP5 only):

- Transactional Audit Event vs Best-effort Security Event
- SQLAlchemy reserved `metadata` attribute
- Actor vs Target identity
- Append-only Application Boundary
- Durable Audit Trail vs Application Log

## Current State

CP0 and CP1 are complete.

Supervisor approval marker: **CP1**.

Next authorized action: Dispatcher CP2 on `feature/issue-009-audit-logging`.

Do not begin CP3 until the Supervisor reviews CP2 evidence and advances the remote approval marker.

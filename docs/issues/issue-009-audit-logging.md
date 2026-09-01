# Engineering Issue #009 — Durable Security Audit Trail

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

Status: **next**

Supervisor proposal for Codex to validate, not blindly accept:

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
- [ ] CP1 — Architecture + implementation plan validation
- [ ] CP2 — Bounded implementation
- [ ] CP3 — Targeted + regression verification
- [ ] CP4 — Diff / security / transaction review
- [ ] CP5 — Knowledge + documentation synchronization
- [ ] CP6 — PR delivery evidence

## Commands / Evidence

### CP0

Repository state inspected from current `develop`.

No Product Code modified.

### CP1 — First real Dispatcher command

From the local Repository after fetching the new Branch:

```powershell
git fetch origin
git switch feature/issue-009-audit-logging
git pull --ff-only origin feature/issue-009-audit-logging

python scripts/codex_dispatch.py --issue 009 --checkpoint CP1 --dry-run
python scripts/codex_dispatch.py --issue 009 --checkpoint CP1
```

CP1 is `read-only` and must stop after returning the validated plan.

## Knowledge Candidates

Existing Notion Knowledge already covers the Audit Logging fundamentals.

Potential additions after implementation (CP5 only):

- Transactional Audit Event vs Best-effort Security Event
- SQLAlchemy reserved `metadata` attribute
- Actor vs Target identity
- Append-only Application Boundary
- Durable Audit Trail vs Application Log

## Current State

CP0 is complete.

Next action: run Dispatcher CP1 on `feature/issue-009-audit-logging`.

Do **not** begin CP2 until the Supervisor reviews the CP1 result.

# Engineering Issue #009 — Durable Security Audit Trail

<!-- codex-dispatch-supervisor-approved-through: CP6 -->
<!-- codex-dispatch-write-allow: ["app/models/audit_event.py","app/models/__init__.py","app/repositories/audit.py","app/services/audit.py","app/services/rbac.py","app/api/routes/auth.py","app/api/routes/admin.py","app/api/dependencies/auth.py","app/api/dependencies/authorization.py","migrations/versions/*audit*.py","tests/test_audit_*.py","tests/test_auth.py","tests/test_auth_dependency.py","tests/test_authorization_dependency.py","tests/test_admin_rbac.py","tests/test_rbac_service.py","tests/test_rbac_security.py","tests/test_migrations.py","docs/issues/issue-009-audit-logging.md"] -->

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

### Dispatcher Publish Allowlist

The machine-readable `codex-dispatch-write-allow` marker above is intentionally narrower than the conceptual Allowed Write Set.

Notably, `migrations/env.py`, `docs/PROJECT_STATE.md`, and `README.md` are **not** authorized for automatic CP2 publication. If Codex proves one is necessary, it must stop and report the blocker so the Supervisor can explicitly expand the remote Allowlist.

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
- [x] CP2 — Bounded implementation (Supervisor-reviewed)
- [x] CP3 — Targeted + regression verification
- [x] CP4 — Diff / security / transaction review
- [x] CP5 — Knowledge + documentation synchronization
- [x] CP6 — PR delivery evidence

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

### CP2 Implementation Evidence

Implemented the approved bounded slices:

- `AuditEvent` persistence model, export, migration, and focused tests.
- Audit repository/service with transaction-participating and best-effort semantics.
- Atomic RBAC role-mutation audit insertion with acting-administrator identity.
- Best-effort login, invalid-token/user, and permission-denial audit recording.

Focused test command attempted:

```powershell
pytest -q tests/test_audit_model.py tests/test_audit_repository.py tests/test_audit_service.py tests/test_audit_integrations.py tests/test_auth.py tests/test_auth_dependency.py tests/test_authorization_dependency.py tests/test_admin_rbac.py tests/test_rbac_service.py tests/test_migrations.py
```

The command did not reach test collection because the configured virtual-environment launcher reports that its Python 3.11 base executable is missing. This is a local environment blocker; CP3 has not started.

## Supervisor CP2 Review

Status: **approved to enter CP3 with required verification fixes**

### Architecture findings

PASS:

- `AuditEvent` uses Python attribute `event_metadata` mapped to DB column `metadata`, avoiding SQLAlchemy Declarative `metadata` collision.
- `actor_user_id` is a durable UUID value without a cascading Foreign Key, preserving Audit history.
- `AuditRepository.create()` performs add + flush only; it does not own Commit.
- RBAC role mutation and Audit insertion share one SQLAlchemy transaction and one Commit.
- Audit persistence failure during RBAC mutation rolls back and translates to `PersistenceUnavailableError`.
- Login failure does not persist submitted Email or Password.
- Login success records the authenticated User ID.
- Authorization denial records User + Permission without Tokens/Headers.
- Migration chain is linear: `372ee... → 1042... → 9f3c...`.

### CP3 must resolve / prove

1. **Regression test fix**
   - Existing `test_require_permission_rejects_user_without_permission` passes `session=object()` and does not mock the new Audit path.
   - Update the test so the expected 403 is testing Authorization behavior rather than failing on an invalid fake Session.

2. **Real best-effort failure tests**
   - Current tests named `invalid_token_audit_failure_preserves_401` and `permission_denial_audit_failure_preserves_403` replace `record_best_effort` with a no-op.
   - That does not simulate persistence failure.
   - Replace/add tests that exercise the real `AuditService.record_best_effort()` while `flush` or `commit` raises a SQLAlchemy persistence exception, then prove the original 401/403 still wins and Rollback occurs.

3. **Audit event coverage assertions**
   - Add explicit assertions for Login success Audit payload.
   - Add explicit assertions for RBAC assign/remove Audit payload including:
     - actor User ID
     - target User ID
     - role
     - outcome
     - `changed=true/false`

4. **Migration / schema verification**
   - Run the existing Alembic single-head tests.
   - If PostgreSQL/Docker is available, run real `upgrade → downgrade -1 → upgrade` and record evidence.
   - Verify `audit_events.metadata` is JSONB and non-null and Model/Migration remain aligned.

5. **Sensitive-data negative verification**
   - Assert Audit payloads never contain submitted Password, failed-login Email, Access Token, Authorization Header, Password Hash, JWT Secret, or arbitrary Request body.

### CP3 command policy

Do **not** use the broken `pytest.exe` launcher first.

Use the Python interpreter that successfully launches the Watcher/Codex process:

```powershell
python -m pytest -q tests/test_audit_model.py tests/test_audit_repository.py tests/test_audit_service.py tests/test_audit_integrations.py tests/test_auth.py tests/test_auth_dependency.py tests/test_authorization_dependency.py tests/test_admin_rbac.py tests/test_rbac_service.py tests/test_migrations.py
```

Then:

```powershell
python -m pytest -q
```

If `python -m pytest` cannot import pytest, report the exact interpreter path and dependency error. Do not silently install or mutate unrelated environment configuration unless required by the Issue contract.

For PostgreSQL migration evidence when the local Docker stack is available:

```powershell
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

CP3 may fix only in-scope Product/Test files already covered by the Remote Write Allowlist.

Do not mark CP4 complete.

### CP3 Verification Evidence

In-scope test coverage was updated to:

- mock the Audit path in the existing Authorization-denial regression test;
- exercise the real best-effort Audit service with a SQLAlchemy flush failure while preserving the original `401` and `403` responses and rolling back;
- assert Login success and RBAC assign/remove Audit payloads, including actor, target, role, outcome, and `changed` state;
- assert JSONB/non-null model metadata and sensitive-data exclusion from failed-login Audit payloads.

Required commands attempted:

```powershell
python -m pytest -q tests/test_audit_model.py tests/test_audit_repository.py tests/test_audit_service.py tests/test_audit_integrations.py tests/test_auth.py tests/test_auth_dependency.py tests/test_authorization_dependency.py tests/test_admin_rbac.py tests/test_rbac_service.py tests/test_migrations.py
python -m pytest -q
```

Both commands failed before test collection because the only available interpreter is `.venv\\Scripts\\python.exe`, whose `pyvenv.cfg` points to the missing base executable `C:\\Users\\88693\\AppData\\Local\\Microsoft\\WindowsApps\\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\\python.exe`. Docker is not available, so the optional PostgreSQL migration cycle could not be run. `git diff --check` passed.

## CP3 CI Evidence — First GitHub-hosted Run

Draft PR #38 verified the exact Issue Branch Head `56e83d51fcddb2d943fc4948dbafa6d0a96401cf`.

### PASS

- Dispatcher / Watcher Control Plane: PASS
- PostgreSQL 16 service: healthy
- Alembic `upgrade head`: PASS
- Docker Compose database recovery: PASS
- 160 backend tests passed before the regression gate stopped

### FAIL — bounded test-isolation regression

Exactly two tests failed:

- `tests/test_rbac_security.py::test_jwt_admin_claim_cannot_bypass_database_authorization`
- `tests/test_rbac_security.py::test_jwt_rbac_manage_claim_cannot_access_admin_api`

Both tests deliberately override `get_db` with `object()` because their purpose is to prove JWT role/permission claims cannot bypass database-backed authorization.

The new denial Audit path now calls `AuditService(session).record_best_effort(...)`, so those fake Sessions fail with:

```text
AttributeError: 'object' object has no attribute 'add'
```

This does **not** justify weakening `AuditService` or swallowing arbitrary programming errors.

### Required CP3 fix

Keep the RBAC security tests focused on their original trust-boundary assertion.

Preferred fix:

- mock/stub `AuditService.record_best_effort` in those two tests, or provide a Session fake that satisfies the Audit contract without performing persistence.
- do not change production Authorization semantics solely to accommodate `session=object()`.
- preserve explicit verification that denied JWT claims still return 403 and DB-backed `has_permission` is authoritative.

The remote Write Allowlist is expanded to include `tests/test_rbac_security.py`.

After the fix, rerun the Draft PR Backend Verification and complete the remaining CP3 requirements, including real best-effort persistence-failure tests and sensitive-data assertions.

## Supervisor Intervention — CP3 test isolation

The authorized `CP3 rework-1` was not consumed by a running Local Watcher.

To avoid blocking the Issue on local process availability, the Supervisor disarmed the unused rework marker and applied only the two CI-proven test-isolation fixes directly.

Boundary:

- Production Audit code is unchanged.
- Authorization / RBAC semantics are unchanged.
- Only `tests/test_rbac_security.py` may change in this intervention.
- The fix must mock the Audit side effect while preserving the tests' original assertion that JWT role/permission claims cannot bypass database-backed authorization.
- Draft PR #38 GitHub-hosted Backend Verification remains the acceptance gate.

## Final CP3 / CP4 Evidence

Final verification after the bounded RBAC security-test isolation fix and additional Security Evidence tests:

```text
Dispatcher / Control Plane: 73 passed
Backend regression: 178 passed
Database recovery: 1 passed
Alembic upgrade → downgrade -1 → re-upgrade: PASS
```

CP4 findings:

- No Production file outside Issue Scope.
- `AuditRepository` exposes Create only.
- Audit DB column `metadata` maps through Python `event_metadata`.
- Actor Administrator identity and target User identity are distinct.
- RBAC Role mutation + Audit insertion use one transaction / one Commit.
- Audit persistence failure prevents unaudited privilege mutation.
- Best-effort SQLAlchemy Audit failure rolls back its failed write and preserves intended 401 / 403.
- Failed Login Audit excludes submitted Email/Password.
- Invalid-token Audit explicitly excludes the raw Access Token / Authorization material.
- JWT role/permission claims still cannot bypass database-backed RBAC.
- Migration chain remains single-head and round-trip tested.

No merge-blocking finding remains.

## Knowledge Candidates

Existing Notion Knowledge already covers the Audit Logging fundamentals.

Potential additions after implementation (CP5 only):

- Transactional Audit Event vs Best-effort Security Event
- SQLAlchemy reserved `metadata` attribute
- Actor vs Target identity
- Append-only Application Boundary
- Durable Audit Trail vs Application Log

## Current State

Engineering Issue #009 is complete and verified.

Final delivery evidence:

- Product PR: #38
- Final reviewed Product/Test Head before delivery docs: `bad2b65f3f8fe49aa8ead32c2a3120359be1643e`
- Dispatcher / Control Plane: **73 passed**
- Backend regression: **178 passed**
- Docker Compose database recovery: **1 passed**
- PostgreSQL 16 + Alembic upgrade/downgrade/re-upgrade: PASS
- CP4 Security / Transaction review: PASS
- CP5 Notion knowledge synchronization: complete
- README / Project State synchronization: complete

Supervisor approval marker: **CP6**.

No known merge-blocking finding remains. PR #38 is ready for delivery into `develop`.

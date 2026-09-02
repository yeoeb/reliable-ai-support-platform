# Engineering Issue #016 — Durable Human Approval for Higher-Risk Tool Actions

<!-- codex-dispatch-supervisor-approved-through: CP6 -->
<!-- codex-dispatch-write-allow: ["app/models/approval_request.py","app/models/__init__.py","app/repositories/approval.py","app/services/approval.py","app/services/rbac.py","app/services/agent.py","app/services/tool_execution.py","app/tools/registry.py","app/tools/system.py","app/tools/rbac.py","app/schemas/approval.py","app/schemas/agent.py","app/api/routes/approvals.py","app/api/routes/agent.py","app/core/errors.py","app/main.py","migrations/versions/*approval*.py","tests/test_approval_*.py","tests/test_agent_*.py","tests/test_tool_*.py","tests/test_rbac_service.py","tests/test_migrations.py","docs/issues/issue-016-human-approval.md"] -->

## GitHub Tracking

- GitHub Issue: #73
- Engineering Issue ID: #016
- Branch: `feature/issue-016-human-approval`

## Goal

Add a durable Human Approval boundary for one fixed higher-risk Tool action:

`grant_support_agent_role(user_id)`

The model may propose the action but cannot execute or approve it.

## Required Reading

Before CP2 edits:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- GitHub Issue #73
- this execution note
- `app/tools/registry.py`
- `app/tools/system.py`
- `app/services/tool_execution.py`
- `app/services/agent.py`
- `app/services/rbac.py`
- `app/repositories/rbac.py`
- `app/services/audit.py`
- `app/api/routes/agent.py`
- `app/api/routes/admin.py`
- `app/api/dependencies/authorization.py`
- `app/models/audit_event.py`
- `app/models/__init__.py`
- `migrations/versions/d94c6e7f8a03_add_system_read_tool_permission.py`
- focused Tool/RBAC/Audit/Migration tests

## CP0 — Context Bootstrap

Status: **completed by Supervisor**

Findings:

1. #015 Controlled Tool Calling is merged to `develop`.
2. Current Registry supports `read_only` only and owns Tool name/schema/permission/executor.
3. `ToolExecutionService` re-checks current DB permission immediately before read-only execution.
4. `AgentService` filters Tool schemas from current effective permissions and executes at most one Tool.
5. Existing `RBACService.assign_role()` performs mutation + durable RBAC Audit + internal commit.
6. Existing Admin role-assignment API requires `rbac:manage`.
7. Admin is the only baseline role with `rbac:manage`.
8. Reusing unrestricted `assign_role(role_name)` as a model Tool would be unsafe because the model could choose `admin`.
9. A fixed Tool `grant_support_agent_role(user_id)` exercises a real privilege mutation without exposing arbitrary role selection.
10. Human Approval must survive request boundaries; an in-memory flag/model turn is insufficient.
11. Approval execution needs a row lock and one transaction to prevent duplicate execution and crash-window inconsistency.
12. Existing `RBACService.assign_role()` therefore needs a transaction-participating inner operation while preserving current direct Admin API behavior.

No contradiction was found.

## CP1 — Durable Approval Architecture

Status: **completed and approved by Supervisor**

### Core Security Invariant

```text
model proposes
≠
human approves
≠
server authorizes
```

All three layers remain separate.

### V1 Higher-Risk Tool

Name:

`grant_support_agent_role`

Arguments:

```text
user_id: UUID
```

Server-owned constants:

- role: `support_agent`
- required permission: `rbac:manage`
- risk: `approval_required`

The Provider schema has no `role_name` field.

### Tool Registry Evolution

Extend risk:

- `read_only`
- `approval_required`

Use explicit executor ownership:

```text
read_only
  → executor required
  → approval_executor absent

approval_required
  → executor absent
  → approval_executor required
```

Registry construction fails closed for invalid combinations.

Suggested approval executor signature:

```text
(session, actor_user_id, validated_arguments)
    → bounded result dict
```

The callable remains server-owned.

### Normal ToolExecutionService

`ToolExecutionService` must continue to execute **read_only only**.

If passed an `approval_required` Tool, fail closed before executor invocation.

### Fixed RBAC Approval Tool

Create `app/tools/rbac.py`.

`GrantSupportAgentRoleArguments`:

- `user_id: UUID`
- extra fields forbidden

Approval executor:

- calls a transaction-participating RBACService role assignment
- fixed role `support_agent`
- no commit
- returns:
  - `{"status":"assigned"}`
  - or `{"status":"already_assigned"}`

### RBAC Transaction Refactor

Add an explicit method such as:

`RBACService.assign_role_in_transaction(...)->bool`

It owns:

- target User lookup
- Role lookup
- role assignment
- durable `rbac.role.assign` Audit

It does **not** commit/rollback.

Existing public `assign_role()` becomes a wrapper:

```text
assign_role_in_transaction
→ commit
→ existing success log
```

and preserves existing rollback/error behavior for the direct Admin route.

This avoids adding a vague `commit=False` switch and keeps transaction ownership explicit.

### Durable Approval Model

Create `ApprovalRequest`.

Fields:

- `id: UUID`
- `requested_by_user_id: UUID`
- `tool_name: str`
- Python attribute `tool_arguments`, DB JSONB column `arguments`
- `status: str`
- `created_at: timezone-aware datetime`
- `expires_at: timezone-aware datetime`
- `decided_by_user_id: UUID | None`
- `decided_at: datetime | None`
- `executed_at: datetime | None`

Statuses:

- `pending`
- `rejected`
- `executed`
- `expired`

No generic Update/Delete API.

No durable `approved` intermediate status: approve + action execution are atomic.

### Exact Action Binding

Before persistence:

```text
Registry lookup
→ risk must be approval_required
→ Pydantic validate model arguments
→ model_dump(mode="json")
→ persist tool_name + canonical validated arguments
```

The DB row is the exact pending action.

No endpoint can edit `tool_name` or `tool_arguments`.

### TTL

Use a bounded V1 constant:

`APPROVAL_TTL_MINUTES = 15`

Do not expand configuration scope in #016 unless tests expose a concrete need.

Service computes `expires_at` using timezone-aware UTC.

### Approval Repository

Create `ApprovalRepository`:

- `create(...)`: add + flush, no commit
- `get_by_id(...)`
- `get_for_update(...)`: `SELECT ... FOR UPDATE`

No repository-level commit.

### Approval Request Creation

When Agent receives an `approval_required` Tool proposal:

1. exact Registry lookup;
2. validate arguments;
3. re-check requester's current action permission;
4. persist Approval row;
5. persist durable `approval.requested` Audit in same transaction;
6. commit;
7. do **not** execute the Tool;
8. do **not** call Provider finalization;
9. return deterministic server response:
   - `status="approval_required"`
   - `approval_id`
   - `answer="Human approval required."`

If Approval persistence/Audit commit fails, roll back and return generic persistence error.

### Agent Response Evolution

Extend `AgentRunResponse`:

- `status: completed | approval_required`
- `approval_id: UUID | None`

Existing read-only/direct-answer paths return:

- `status="completed"`
- `approval_id=None`

Approval-required path does not claim action success.

### Approval Permission

Migration adds:

`approval:decide`

Grant only to admin.

Existing action still requires `rbac:manage`.

### Human Approval API

Add:

```text
GET  /approvals/{approval_id}
POST /approvals/{approval_id}/approve
POST /approvals/{approval_id}/reject
```

Route dependency requires `approval:decide`.

Service additionally re-checks permissions during decision.

Inspection response exposes only safe exact action state:

- ID
- effective status
- Tool name
- validated Tool arguments
- requester ID
- timestamps
- decider ID if decided

No model prompt/provider response.

### Approval Decision Locking

Approve/reject:

```text
SELECT Approval ... FOR UPDATE
→ current-state checks
→ decision
```

Reject missing/already decided/expired states.

Concurrent approval attempts must serialize on the row lock.

### Approval-Time Authorization

Approve transaction:

1. lock Approval;
2. verify pending;
3. check expiry;
4. Registry resolves exact persisted Tool;
5. require `approval_required`;
6. Pydantic revalidate persisted arguments;
7. re-check approver's current `approval:decide`;
8. re-check original requester's current Tool permission (`rbac:manage`);
9. execute server-owned approval executor;
10. set status `executed`;
11. set decided/executed timestamps + approver ID;
12. persist `approval.executed` Audit;
13. one commit.

The approval executor's RBAC mutation also emits `rbac.role.assign` through the transaction-participating RBAC operation.

If the final transaction fails, Approval status and RBAC mutation roll back together.

### Expiry

If decision occurs after `expires_at`:

- do not execute;
- mark `expired`;
- persist `approval.expired` Audit;
- commit expiration;
- return controlled conflict.

GET may report effective `expired` for an elapsed pending row without using an execution path.

### Reject

Reject flow:

- row lock;
- pending/not-expired check;
- current approver `approval:decide`;
- mark rejected;
- durable `approval.rejected` Audit;
- commit;
- no Tool execution.

### Self-Approval

V1 allows the same admin to be requester and human approver.

Reason: Human Approval is demonstrated as an explicit user interaction and durable authorization boundary.

Mandatory four-eyes separation is future hardening and must not be claimed by #016.

### Audit / Log Boundary

Durable:

- `approval.requested`
- `approval.executed`
- `approval.rejected`
- `approval.expired`
- existing `rbac.role.assign`

Safe metadata:

- approval ID
- Tool name
- risk level
- target user ID
- bounded result status

Exclude:

- raw user/model request
- raw Provider response
- secrets/token
- arbitrary unvalidated args
- arbitrary output

### Supervisor Fallback Execution

The authorized CP2 gate was not consumed by a running Local Watcher/Codex Executor.

The Supervisor is performing a bounded fallback implementation on the Feature Branch.

This does not bypass:
- the machine Write Allowlist;
- CP3 exact-head verification;
- CP4 concurrency / authorization / transaction review;
- CP5 Knowledge Capture;
- CP6 Delivery Gate.

Branch history must not be represented as a Codex-generated checkpoint unless the Dispatcher actually produced it.

## CP2 Ordered Slices

CP2 is deliberately bounded.

1. **Model + migration**
   - ApprovalRequest model/export
   - approval_requests table
   - `approval:decide` admin-only permission
   - focused model/migration tests

2. **Repository + approval state machine**
   - create/get/get_for_update
   - expiry
   - request/reject/approve transaction logic
   - focused service/repository tests

3. **RBAC transaction refactor**
   - explicit no-commit role assignment
   - preserve old public Admin behavior/tests

4. **Registry / higher-risk Tool**
   - approval_required risk
   - executor combination invariants
   - `grant_support_agent_role(user_id)`
   - ToolExecutionService refuses approval-required Tool

5. **Agent integration**
   - high-risk proposal creates Approval
   - no execution/finalization
   - deterministic approval_required response
   - existing read-only path preserved

6. **Approval API**
   - inspect/approve/reject
   - generic 403/404/409/503
   - focused API tests

7. **Focused tests only**

**Do not run full repository regression in CP2.**
Full regression remains CP3 / Final CI.

If an implementation needs a file outside the machine Allowlist, stop and report Scope expansion instead of editing it.

## CP3 / CP4 Verification Evidence

Final reviewed Product/Test Head before CP5 documentation:

`6e80cd63a71cc392a1699f18f36a253035971dd2`

GitHub-hosted exact-head evidence:

```text
Backend regression: 424 passed
Database recovery:   1 passed
Control Plane:      87 passed
PostgreSQL / pgvector: PASS
Alembic upgrade head: PASS
Alembic downgrade -1: PASS
Alembic re-upgrade: PASS
```

### CP4 concurrency proof

A real PostgreSQL two-Session integration test concurrently approves the same durable Approval row.

Observed contract:

- one decision returns executed;
- one decision returns ApprovalStateConflict;
- target User has exactly one support_agent role assignment;
- Approval status is executed exactly once.

This verifies the `SELECT ... FOR UPDATE` boundary behavior rather than only inspecting generated SQL.

### CP4 Security / Authorization / Transaction Review

Status: **PASS**

Findings:

- Model Tool schema exposes only `user_id`; no `role_name`, permission name, admin role, SQL, shell, URL, or executable payload is model-controlled.
- Higher-risk Tool is server-owned and fixed to `support_agent`.
- Normal `ToolExecutionService` rejects `approval_required` before permission/executor invocation.
- Agent high-risk path creates a durable Approval and never calls ToolExecution/finalization.
- Agent returns deterministic `Human approval required.` and cannot claim mutation success.
- Pending Approval stores canonical validated Tool name + arguments.
- Approval survives request boundaries in PostgreSQL.
- 15-minute expiry is server-owned.
- `approval:decide` is granted only to admin.
- Inspect/approve/reject routes require `approval:decide`.
- Decision Service re-checks current approver permission.
- Approve re-checks the original requester's current action permission.
- Permission revocation blocks execution.
- Persisted Tool is re-resolved through the server Registry and arguments are revalidated before execution.
- Approve/reject use row locks.
- Already-decided and expired Approvals cannot execute.
- Expiry is persisted with durable Audit when encountered on decision.
- Fixed approval executor calls the no-commit RBAC transaction operation.
- Approval state + support_agent mutation + RBAC Audit + approval.executed Audit share one outer Commit.
- Audit/persistence failure rolls back the transaction.
- Existing direct Admin RBAC API keeps its previous Service-owned Commit behavior.
- Rejection never invokes the Tool.
- Approval Audit/runtime metadata is bounded to approval/tool/risk/target/result identifiers and excludes raw model/provider/secrets/arbitrary unvalidated arguments.
- V1 intentionally permits self-approval; mandatory four-eyes separation is not claimed.

No merge-blocking finding remains.

## CP5 Knowledge / Documentation

Notion deduplication was completed before writing.

Existing Glossary / Tool Safety pages already contain the generic HITL definition and the statement that higher-risk Tool actions require a separate approval boundary, so they were not duplicated.

Created one deeper reusable Engineering Encyclopedia entry:

**Human Approval / HITL：Durable Approval、Exact Action Binding、Row Lock 與 Approval-Time Authorization**

Created one project Work Log:

**Issue #016 — Durable Human Approval / Higher-Risk Tool Actions**

The Work Log links to the reusable Knowledge entry and the Reliable AI Support Operations Platform project.

Reusable lessons captured:

- Model proposal, Human approval, and Server authorization are separate control planes.
- Approval must bind to one canonical validated action and survive request boundaries.
- Approval permission never substitutes for the underlying action permission.
- Approval-time authorization prevents TOCTOU after permission revocation.
- SELECT ... FOR UPDATE provides one-time decision serialization.
- A real two-Session PostgreSQL concurrency test is stronger evidence than SQL-shape inspection alone.
- Approval + mutation + durable Audits should commit atomically without a crash-prone intermediate approved state.
- Transaction-participating inner Service methods enable larger atomic workflows without weakening existing public Service contracts.
- Human Approval does not automatically imply four-eyes / separation-of-duties.

## Allowed Write Set

The machine-readable marker at the top is authoritative.

Conceptual scope:

- Approval model/repository/service/schema/API
- Tool Registry + RBAC higher-risk Tool
- Agent/ToolExecution integration
- RBAC transaction refactor
- Error/Main wiring
- one #016 approval migration
- focused Approval/Agent/Tool/RBAC/Migration tests
- this execution note

## Out of Scope

- arbitrary role grants
- model-selected role name
- admin role elevation
- arbitrary shell/SQL/HTTP
- hosted tools/MCP
- automatic/model approval
- required distinct approver
- bulk approvals
- external side-effect tools
- background jobs
- multi-step Agent loop

## Checkpoints

- [x] CP0 — Context bootstrap
- [x] CP1 — Durable approval architecture
- [x] CP2 — Bounded implementation
- [x] CP3 — Verification
- [x] CP4 — concurrency / authorization / transaction review
- [x] CP5 — Knowledge / documentation
- [x] CP6 — exact-Head delivery

## CP6 Final Delivery

Status: **completed**

Verified immutable Product Head:

`78e3b28c9909adf6faf7304021c8c2c1533d29d8`

Final checks on the same exact Head:

- Backend Verification #174: PASS
- Dispatcher Tests #126: PASS
- Backend Verification #175 / run `33632260867`: PASS — **424 passed**
- Dispatcher Tests #127 / run `33632260852`: PASS — **87 passed**
- Database recovery: PASS
- PostgreSQL / pgvector: PASS
- Alembic upgrade / downgrade -1 / re-upgrade: PASS
- real two-Session concurrent approval: PASS

Draft PR #74 was replaced by non-draft PR #75 without changing the Product Head because the connector Ready-for-Review transition is incompatible with the current GitHub GraphQL schema.

No Product/Docs Branch commit occurred after exact-Head verification.

## Merge Evidence

- Engineering Issue: #016
- GitHub Issue #73: Closed / Completed
- Product PR #75: Merged
- Superseded Draft PR #74: Closed
- Product Head: `78e3b28c9909adf6faf7304021c8c2c1533d29d8`
- Product squash merge: `1166d464b275653e551f4dabdc303b5e7ddbb035`
- CP0–CP6: complete
- Notion knowledge capture: complete
- Next Product Engineering Issue: #017 LLM Evaluation foundation

## Current State

Remote Supervisor approval: **CP6**.

Engineering Issue #016 is complete.

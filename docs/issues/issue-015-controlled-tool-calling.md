# Engineering Issue #015 — Controlled Read-Only Tool Calling Foundation

<!-- codex-dispatch-supervisor-approved-through: CP5 -->
<!-- codex-dispatch-write-allow: ["app/tools/__init__.py","app/tools/registry.py","app/tools/system.py","app/integrations/llm.py","app/services/tool_execution.py","app/services/agent.py","app/schemas/agent.py","app/api/routes/agent.py","app/core/errors.py","app/main.py","migrations/versions/*tool*.py","tests/test_tool_*.py","tests/test_agent_*.py","tests/test_retrieval_migration.py","docs/issues/issue-015-controlled-tool-calling.md"] -->

## GitHub Tracking

- GitHub Issue: #69
- Engineering Issue ID: #015
- Branch: `feature/issue-015-controlled-tool-calling`
- Product PR: #70

## Goal

Establish the first server-controlled custom function Tool boundary with one bounded read-only diagnostic capability.

V1 Tool:

- `platform_readiness`
- required permission: `system:read`
- allowed roles: support_agent and admin
- maximum Tool executions per request: 1

## Delivered Boundary

The Application owns:

- Tool Registry
- Tool name and description
- required permission
- risk classification
- argument schema
- executor binding
- execution-time permission decision
- Audit metadata
- execution count

The model can only propose a registered Tool name and structured arguments.

The server validates the proposal and re-checks current database-backed permission before execution.

The final generation step receives no Tool definitions.

## Checkpoints

- [x] CP0 — Context bootstrap
- [x] CP1 — Architecture / plan
- [x] CP2 — Bounded implementation
- [x] CP3 — Verification
- [x] CP4 — Security / authorization review
- [x] CP5 — Knowledge / documentation
- [ ] CP6 — exact-Head delivery

## CP2 Evidence

CP2 was completed through a bounded Supervisor fallback because the local Watcher did not publish the authorized checkpoint after repeated remote checks.

Product implementation includes:

- `system:read` migration
- server-owned Tool Registry
- bounded `platform_readiness`
- custom-function Provider boundary
- strict server-side argument validation
- authorized Tool filtering before Provider wait
- permission re-check before execution
- transaction boundaries around external waits
- one-Tool request bound
- safe Audit / Runtime metadata
- authenticated `POST /agent/run`
- focused tests

Supervisor Review also replaced an internal assertion with explicit fail-closed validation and removed a real-database dependency from a focused unit test.

## CP3 Evidence

First GitHub-hosted run:

- Backend: 387 passed, 1 failed
- Dispatcher: PASS
- Database recovery: PASS
- #015 migration upgrade: PASS

The only failure was stale #013 test debt: its historical migration test incorrectly required the #013 revision to remain the permanent global Alembic Head.

Bounded maintenance updated that test to validate its own ancestry and invariants while leaving the repository-wide single-head test authoritative.

Second GitHub-hosted run on `3a6d5e886189cbb2f430e37064a6c92184063afc`:

- Backend Verification #163: PASS
- Backend regression: 388 passed
- Dispatcher Tests #113: PASS
- Control Plane: 87 passed
- Database recovery: PASS
- PostgreSQL / pgvector verification: PASS
- Alembic upgrade / downgrade / re-upgrade: PASS

## CP4 Review

Security and authorization review passed.

Confirmed:

- Registry is server-owned.
- Unknown Tool names fail closed.
- Tool arguments require server-side schema validation.
- Caller permissions filter the Tool list before Provider wait.
- Current permission is checked again before execution.
- Provider and execution waits do not intentionally retain request read transactions.
- V1 executes at most one read-only Tool.
- Parallel Tool execution is disabled.
- Finalization receives no Tool definitions.
- Tool results remain untrusted data.
- No Product mutation is available in #015.
- Sensitive request/result/provider content is excluded from Audit and Runtime Log metadata.

## CP5 Knowledge Capture

Notion knowledge updated:

- `AI Agent Tool Safety：Argument Validation、Tool Allowlist、Error Handling、max_steps`

Work Log created:

- `Issue #015 — Controlled Read-Only Tool Calling`

Repository documentation synchronized:

- `README.md`
- `docs/PROJECT_STATE.md`
- this execution snapshot

## Current State

Remote Supervisor approval: **CP5**.

Next action: **CP6 exact-Head GitHub Actions only**.

No further Product or repository documentation write is planned before Final CI.

After Final CI passes, verification evidence must be stored in GitHub PR / Issue comments without changing the verified Branch Head.

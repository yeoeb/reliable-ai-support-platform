# Engineering Issue #015 — Controlled Read-Only Tool Calling Foundation

<!-- codex-dispatch-supervisor-approved-through: CP1 -->
<!-- codex-dispatch-write-allow: ["app/tools/__init__.py","app/tools/registry.py","app/tools/system.py","app/integrations/llm.py","app/services/tool_execution.py","app/services/agent.py","app/schemas/agent.py","app/api/routes/agent.py","app/core/errors.py","app/main.py","migrations/versions/*tool*.py","tests/test_tool_*.py","tests/test_agent_*.py","docs/issues/issue-015-controlled-tool-calling.md"] -->

## GitHub Tracking

- GitHub Issue: #69
- Engineering Issue ID: #015
- Branch: `feature/issue-015-controlled-tool-calling`

## Goal

Create the first bounded custom function Tool Calling boundary.

The model may propose one server-defined read-only Tool, but the server owns Tool discovery, argument schema, authorization, execution, Audit, and loop bounds.

V1 Tool:

`platform_readiness`

Required permission:

`system:read`

## Required Reading

Before CP2 edits:

- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- GitHub Issue #69
- this execution note
- `app/integrations/llm.py`
- `app/services/rag.py`
- `app/services/authorization.py`
- `app/api/dependencies/auth.py`
- `app/api/dependencies/authorization.py`
- `app/repositories/rbac.py`
- `app/services/audit.py`
- `app/api/routes/health.py`
- `app/db/session.py`
- `migrations/versions/c83b5d6e7f92_add_vector_retrieval.py`
- existing authorization/audit/logging tests

## CP0 — Context Bootstrap

Status: **completed by Supervisor**

Findings:

1. #014 Grounded RAG is merged and `develop` records #015 as the next Product Issue.
2. No existing Tool Registry, Tool execution service, Tool Calling endpoint, or Tool permission exists.
3. Existing OpenAI integration is isolated in `app/integrations/llm.py`; #015 should extend that Provider boundary instead of importing the SDK into Route/Service code.
4. Existing AuthorizationService reads effective permissions from database-backed RBAC.
5. Existing AuditService supports best-effort read/security event recording.
6. `check_database_connection()` already provides a bounded PostgreSQL readiness probe and owns its own Engine connection.
7. `platform_readiness` is a suitable first Tool because it is read-only, bounded, operationally meaningful, and does not require #016 Human Approval.
8. Existing #013 permission migration demonstrates deterministic support_agent/admin permission seeding and downgrade.
9. Request Session reads can open a transaction; Provider waits and Tool execution must not intentionally hold that read transaction.
10. Raw Tool Request/arguments/result must not become generic log payloads.
11. No arbitrary shell, SQL, dynamic import, URL fetch, Python callable lookup, MCP, hosted tools, or parallel Tool execution is required.
12. Official current Responses API exposes custom function tools with strict schemas and returns `function_call` output items. #015 will isolate the concrete SDK shape behind fake-client Provider tests.

No contradiction was found.

## CP1 — Architecture / Plan

Status: **completed and approved by Supervisor**

### Core Invariant

```text
LLM Tool Request
    ≠
Authorization
```

The model is a proposer only.

### V1 Bounded Flow

```text
Authenticated User
    ↓
load current effective permissions
    ↓
filter server Tool Registry
    ↓
no allowed Tool? → deterministic 403, no Provider call
    ↓
close request DB read transaction
    ↓
Provider choose(request, allowed_tools)
    ↓
final response? → return
    ↓ one ToolCallRequest
exact Registry lookup
    ↓
strict argument validation
    ↓
re-check permission from DB
    ↓
permission denied? → 403, no execution
    ↓
close authorization read transaction
    ↓
execute exactly one read-only Tool
    ↓
best-effort Audit / safe runtime log
    ↓
Provider finalize(request, tool result) with NO TOOLS
    ↓
final response
```

Maximum Tool executions per HTTP request: **1**.

No loop.

### Tool Registry

Create `app/tools/registry.py`.

Suggested ToolDefinition:

- `name`
- `description`
- `required_permission`
- `risk_level`
- `arguments_model`
- executor

Registry invariants:

- server-owned definitions only
- stable names
- duplicate names fail at construction
- unknown name fails closed
- V1 registration accepts read-only risk only
- JSON Schema generated from server-owned Pydantic model
- callers never submit Tool schemas or callable paths

### platform_readiness Tool

Create `app/tools/system.py`.

Arguments model:

- no fields
- `extra="forbid"`

Execution:

```text
check_database_connection()
→ success      → {"status":"ready"}
→ SQLAlchemyError → {"status":"unavailable"}
```

No user-controlled SQL/host/URL.

The Tool result shape is server-owned and bounded.

### Permission

New permission:

`system:read`

Migration grants only:

- support_agent
- admin

Not default user.

Use deterministic UUID and reversible downgrade consistent with existing RBAC migrations.

### Pre-Provider Authorization Filtering

AgentService loads the caller's effective permissions and sends only authorized Tool definitions to the Provider.

If the caller has zero authorized Tools:

- return/raise permission denied;
- do not call Provider.

After this permission read, explicitly close the Session read transaction before Provider wait.

### Execution-Time Authorization

ToolExecutionService must re-check permission **after** the model proposes a Tool and immediately before execution.

Reason:

- permissions may change after the initial filter;
- model output is never authority;
- defense in depth.

After re-check, close the Session transaction before Tool executor work.

### Argument Boundary

Provider function arguments are untrusted JSON.

Expected sequence:

```text
JSON parse
→ exact Tool name lookup
→ Pydantic model validation
→ extra fields rejected
→ execution-time permission check
→ execute
```

Malformed JSON / unexpected fields / wrong types → no Tool execution.

### Provider Boundary

Extend `app/integrations/llm.py`.

Suggested Provider types:

```text
ToolSpec
ToolCallRequest
ToolChoiceResult
ToolFinalResult

ToolCallingProvider
  choose(request, tools)
  finalize(request, tool_name, tool_result)
```

OpenAI choose call:

- Responses API
- custom `type="function"` Tools only
- Tool name/description/schema generated from registry
- `strict=true`
- `parallel_tool_calls=false`
- no Web Search
- no File Search
- no Computer Use
- no hosted tools
- no shell/code interpreter
- no MCP

Provider parsing:

- zero function calls + final text is allowed
- exactly one function call is allowed
- >1 function call fails closed
- malformed function arguments fails closed
- unknown function name is still rejected by Server registry

Finalization call:

- receives original request + bounded Tool name/result as data
- receives **no tools**
- Tool output is explicitly treated as untrusted data
- cannot issue a second Tool Call in V1

A new independent finalization request is acceptable for V1; do not introduce conversation persistence solely for this Issue.

### API Boundary

Suggested endpoint:

`POST /agent/run`

Authentication required.

Do not use model-provided permission claims.

Response should expose bounded execution metadata such as:

- answer
- tool_used: string | null
- tool_status: string | null
- model
- token usage

Do not dump raw Provider response or arbitrary Tool result.

### Error Boundary

Domain errors should distinguish internally:

- no authorized Tool
- unknown Tool
- invalid Tool arguments
- permission revoked
- Provider unavailable
- invalid Provider response
- unexpected Tool infrastructure failure

API maps to generic 401/403/503 as appropriate without leaking internals.

### Audit / Runtime Log

Tool execution event:

`tool.execute`

Safe metadata only:

- tool_name
- risk_level
- outcome
- bounded result_status

Do not include:

- raw user request
- raw arguments
- raw Tool result
- API key
- access token
- Authorization header
- raw Provider output

Read-only execution uses best-effort Audit in #015.

### CP2 Ordered Slices

CP2 is deliberately bounded.

1. **Permission migration**
   - add `system:read`
   - support_agent/admin only
   - focused migration test

2. **Tool Registry + platform_readiness**
   - registry invariants
   - strict empty args
   - readiness executor
   - focused registry/system Tool tests

3. **Provider boundary**
   - function Tool definitions
   - one-call parsing
   - `parallel_tool_calls=false`
   - no hosted tools
   - finalization has no tools
   - fake-client tests only

4. **ToolExecutionService**
   - exact lookup
   - argument validation
   - permission re-check
   - transaction close
   - Audit/log exclusion

5. **AgentService + API**
   - authorized Tool filtering
   - no-tool deterministic denial before Provider
   - bounded one Tool path
   - no loop
   - generic errors

6. **Focused tests only**
   - `tests/test_tool_*.py`
   - `tests/test_agent_*.py`

**Do not run full repository regression in CP2.**
Full regression is CP3 / Final CI.

If a required Production/Test file is outside the machine Allowlist, stop and report Scope expansion instead of editing it.

## Allowed Write Set

The machine-readable marker at the top is the Safe Publish authority.

Conceptual scope:

- `app/tools/`
- `app/integrations/llm.py`
- `app/services/tool_execution.py`
- `app/services/agent.py`
- `app/schemas/agent.py`
- `app/api/routes/agent.py`
- `app/core/errors.py`
- `app/main.py`
- one Tool permission migration
- focused Tool/Agent tests
- this execution note

## Out of Scope

- mutating Tools
- Human Approval
- shell
- arbitrary SQL
- arbitrary HTTP
- MCP
- hosted tools
- parallel calls
- multi-call loops
- tool search
- persistent conversation
- background jobs
- ticket/user/RBAC mutation
- automatic retry

## Checkpoints

- [x] CP0 — Context bootstrap
- [x] CP1 — Architecture / plan
- [ ] CP2 — Bounded implementation
- [ ] CP3 — Verification
- [ ] CP4 — Security / authorization / Tool boundary review
- [ ] CP5 — Knowledge / documentation
- [ ] CP6 — exact-Head delivery

## Current State

CP0 and CP1 are complete.

Remote Supervisor approval: **CP1**.

Next authorized action: **CP2** on `feature/issue-015-controlled-tool-calling`.

Full regression is intentionally deferred to CP3.

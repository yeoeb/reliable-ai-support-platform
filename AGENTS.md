# Engineering Agent Instructions

## Source of Truth

Do not treat chat history as authoritative project state.

Use these sources in this order:

1. `AGENTS.md` for permanent repository rules.
2. `docs/PROJECT_STATE.md` for current cross-Issue project state.
3. The assigned GitHub Issue for the work contract.
4. The Issue execution note under `docs/issues/` when one exists.
5. Architecture/ADR documents explicitly listed by the Issue.
6. Relevant source code and tests.

If these sources conflict, stop and report the contradiction before editing code.

## Branch Model

- `main` is the stable release branch.
- `develop` is the integration baseline for new engineering work.
- Product Feature Branches must normally branch from `develop`.
- Do not commit implementation work directly to `main`.
- One Engineering Issue ID normally maps to one Feature Branch and one Pull Request.

GitHub Issue/PR numbers are platform sequence numbers and are not the same thing as Engineering Issue IDs such as `#009`.

## Required Bootstrap for Every Issue

Before making changes:

1. Read this file.
2. Read `docs/PROJECT_STATE.md`.
3. Read the assigned GitHub Issue.
4. Read all files listed under Required Reading.
5. Inspect relevant tests and current implementation.
6. Produce a scoped plan for the current Checkpoint.

Do not rely on memory from a previous Chat or Agent session.

## Checkpoint Contract

Every engineering Issue should progress through these gates:

- CP0 — Context bootstrap and contradiction detection.
- CP1 — Plan, dependencies, Scope, Out of Scope, risks, write set, tests.
- CP2 — Implementation of the current bounded slice.
- CP3 — Targeted verification and regression tests.
- CP4 — Review of Diff, security boundaries, regressions, and Acceptance Criteria.
- CP5 — Knowledge capture and documentation synchronization.
- CP6 — Commit, Push, Pull Request, and delivery evidence.

Do not silently continue past a Checkpoint when verification fails.

For Dispatcher-controlled work, progress authorization comes from the Supervisor approval marker committed on the remote Feature Branch execution note, not from local Agent/Chat state:

```md
<!-- codex-dispatch-supervisor-approved-through: CP1 -->
```

The Executor must never advance this marker. Only the Supervisor may update it after reviewing the previous Checkpoint.

Write checkpoints also use a Supervisor-controlled path Allowlist embedded in the remote Issue execution note:

```md
<!-- codex-dispatch-write-allow: ["app/example.py", "tests/test_example.py"] -->
```

The Executor must not modify either control marker. It must not commit or push its own checkpoint changes; the Dispatcher owns bounded publication after validation.\n\nA Local Watcher may observe remote approval and automatically invoke **only CP2 / CP3**. It has no authority to approve work, choose Issues, run review/delivery checkpoints automatically, retry failures indefinitely, or Merge.

After Review/CI finds a bounded problem in an already-published CP2/CP3, only the Supervisor may authorize a finite rework attempt with:

```md
<!-- codex-dispatch-supervisor-rework: {"checkpoint":"CP3","attempt":1} -->
```

The Executor must not add, remove, or change this marker. The same rework attempt may run at most once; another attempt requires the Supervisor to increment the attempt explicitly.

## Scope Control

Every delegated coding task must define:

- Goal
- Allowed Write Set
- Out of Scope
- Acceptance Criteria
- Required Verification

Do not modify unrelated files unless the Acceptance Criteria cannot be met otherwise.
When expansion is required, report the blocker and the proposed Scope change before proceeding.

## Multi-Agent Rules

Use additional Agents only for independent, bounded work.

Good delegation:
- read-only exploration
- isolated Test work
- isolated documentation work
- implementation in disjoint file sets
- independent review

Avoid:
- two Agents editing the same files
- delegating ambiguous tasks such as "finish the feature"
- accepting Agent output without inspecting the Diff or evidence
- storing critical Requirements only in Agent-to-Agent messages

The Supervisor owns final integration and verification.

## Architectural Invariants

These constraints survive across Issues unless a dedicated architecture decision explicitly changes them.

### Authentication / Authorization

- JWT establishes authenticated identity; it is not the authorization Source of Truth.
- Authorization is resolved from PostgreSQL-backed RBAC state.
- Protected routes must deny by default.
- The LLM must never bypass RBAC or become an authorization boundary.

### Database

- Service Layer owns transaction boundaries.
- Failed transactions must Rollback.
- Schema evolution must use Alembic.
- Secrets and credential material must not be exposed through API responses or logs.

### AI Safety

- LLM output is untrusted input to policy and tool-execution layers.
- Tool arguments require validation.
- High-risk actions require explicit policy checks and, when specified, Human Approval.
- Security-sensitive flows require negative tests.

## Testing

Run targeted tests first, then broader Regression Tests before completion.

Typical verification may include:

```bash
pytest -v
ruff check .
alembic upgrade head
```

Use only commands relevant to the Issue. Do not claim success without captured evidence.

## Documentation State

At Issue completion:

1. Update `docs/PROJECT_STATE.md`.
2. Update stale README or architecture documentation affected by the change.
3. Preserve Engineering Issue IDs separately from GitHub Issue/PR numbers.
4. Record unresolved Technical Debt explicitly.

## Knowledge Capture

Notion is for reusable engineering knowledge, not Chat transcripts.

Capture only reusable items such as:

- Commands and Parameters
- Root Cause
- Debugging patterns
- Engineering concepts
- Architecture decisions
- Best Practices
- Junior Engineer industry conventions

Before creating a new Knowledge entry, search for an existing equivalent and update it when possible.

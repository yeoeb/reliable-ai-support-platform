# Reliable AI Support Operations Platform — Project State

Last verified: 2026-09-02

## Purpose

This file is the cross-Issue state snapshot for fresh Supervisors and Executors.
It is intentionally concise and must stay synchronized with merged work.

## Branch Semantics

- `main`: stable release state
- `develop`: integration baseline and normal base for new Feature Branches
- `feature/*`: one bounded engineering Issue
- workflow/bootstrap branches: repository process changes only

## Completed Engineering Issue IDs

- #001 — Project bootstrap
- #002 — FastAPI bootstrap and health checks
- #003 — PostgreSQL environment and validated settings
- #004 — Database connection and readiness behavior
- #005 — Alembic foundation and User persistence model
- #006 — Reliable User creation flow
- #007 — Password hashing and JWT authentication
- #008 — RBAC authorization and permission enforcement

## Current Workflow Infrastructure

The repository has an AI-assisted engineering control plane so that fresh Agent sessions do not depend on Chat history.

Required state surfaces:

- `AGENTS.md` — permanent execution rules
- this file — project-wide state
- GitHub Issue — per-task contract
- `docs/issues/` — per-Issue execution snapshots when needed
- Notion — reusable engineering knowledge only
- `scripts/codex_dispatch.py` — local bounded Checkpoint dispatcher
- `.codex-dispatch/` — gitignored local Codex Session metadata\n- `scripts/codex_watch.py` — optional local Trigger Layer for Supervisor-authorized CP2 / CP3

The Dispatcher uses Stable `codex exec` as its local execution boundary. It does not attempt to inject prompts into an already-open VS Code/Desktop Codex UI session.

## Current Product Engineering Issue

Engineering Issue ID #009 — Durable Security Audit Trail

- GitHub tracking Issue: #16
- Active Branch: `feature/issue-009-audit-logging`
- Current Checkpoint: CP3 authorized
- CP0 Context Bootstrap: completed
- CP1 Architecture / Plan: completed and Supervisor-approved
- CP2 Audit implementation: completed and Supervisor-reviewed
- Remote write Allowlist: configured for bounded Audit implementation

Important: GitHub Issue/PR numbers are repository-wide platform sequence numbers and remain separate from Engineering Issue IDs.

## Planned Product Sequence

Tentative order after #009:

- #010 — Structured Logging / Observability foundation
- #011 — Knowledge ingestion
- #012 — Embedding pipeline
- #013 — Retrieval / Vector Search
- #014 — RAG response with evidence/citations
- #015 — Controlled Tool Calling
- #016 — Human Approval for high-risk actions
- #017+ — Evaluation, security regression, monitoring, and CI hardening as dependencies require

The Supervisor may refine this ordering when dependencies or design evidence justify it.

## Current Architectural Invariants

### Authentication / RBAC

- Passwords are hashed; plaintext passwords are never persisted.
- JWT provides identity.
- Authorization is database-backed through RBAC.
- Permission changes must affect authorization without trusting role/permission claims inside JWT.
- Protected routes deny unauthorized access explicitly.

### Application Architecture

Current Backend request path:

```text
HTTP Request
    ↓
FastAPI Route
    ↓
Service Layer
    ↓
Repository Layer
    ↓
SQLAlchemy Session
    ↓
PostgreSQL
```

Service Layer owns transaction boundaries.

### Reliability / Security

- Liveness does not depend on PostgreSQL.
- Readiness reports required dependency failure.
- Database errors are translated explicitly.
- Alembic owns schema evolution.
- Secrets, password hashes, access tokens, and equivalent sensitive material must not be logged.

### Planned AI Boundary

The LLM is a decision-support component, not a security boundary.

Target path:

```text
Authenticated User
    ↓
Authorization
    ↓
Support Request
    ↓
RAG / Context
    ↓
LLM Decision
    ↓
Tool Request
    ↓
Parameter Validation
    ↓
Permission Check
    ↓
Human Confirmation when required
    ↓
Tool Execution
    ↓
Audit Log
    ↓
Response with Evidence
```

## Local Agent Execution Invariants

- CP0 / CP1 / CP4 / CP5 / CP6 use `read-only`.
- CP2 / CP3 use `workspace-write`.
- Write Checkpoints are rejected on `main` and `develop`.
- Write Checkpoints require a Branch name containing the matching Engineering Issue ID, such as `issue-009`.
- CP1–CP6 require Supervisor approval from the remote Feature Branch Issue note; the previous Checkpoint must be approved before the next one starts.
- Local Codex Session state is not progression authority; it exists for Resume and execution metadata.
- Local Codex Session state is bound to the Branch where it was created.
- CP2/CP3 require a clean Working Tree and synchronized Local/Remote Head before Codex starts.
- CP2/CP3 publication is Dispatcher-owned: remote write Allowlist, unchanged control markers, fresh remote Head, and staged Diff hygiene must pass before Commit/Push.
- The Dispatcher uses normal Feature Branch Push only; no Force Push and no Push to `main`/`develop`.
- The Dispatcher never uses `danger-full-access`, `--yolo`, automatic Merge, or automatic Push to `main`.
- Watcher polling does not authorize work; it only reacts to the remote Supervisor Gate.\n- Watcher failures stop instead of automatic unbounded Retry.
- Rework of an already-published CP2/CP3 requires an explicit remote Supervisor marker with a positive attempt number; each attempt has distinct remote Commit evidence and may execute once.\n- Chat history is never the execution Source of Truth.

## Known Documentation Debt

No project-state documentation debt is currently recorded.

## Supervisor Rule

Never infer project progress from Chat memory alone.
Before issuing new work, reconcile this file with merged Pull Requests and the current `develop` state.

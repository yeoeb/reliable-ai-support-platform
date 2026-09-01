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

The repository is adding an AI-assisted engineering control plane so that fresh Agent sessions do not depend on Chat history.

Required state files:

- `AGENTS.md` — permanent execution rules
- this file — project-wide state
- GitHub Issue — per-task contract
- `docs/issues/` — per-Issue execution snapshots when needed
- Notion — reusable engineering knowledge only

## Next Product Engineering Issue

Engineering Issue ID #009 — Audit Logging

Important: GitHub Issue/PR numbers are repository-wide platform sequence numbers.
The GitHub tracking item for Engineering Issue ID #009 may therefore have a different numeric URL.

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

## Known Documentation Debt

- The README on `develop` currently describes RBAC work as still in progress even though Engineering Issue ID #008 has been implemented.
- Workflow bootstrap must correct that stale status before #009 begins.

## Supervisor Rule

Never infer project progress from Chat memory alone.
Before issuing new work, reconcile this file with merged Pull Requests and the current `develop` state.

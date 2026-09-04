# Reliable AI Support Operations Platform — Project State

Last verified: 2026-09-04

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
- #009 — Durable Security Audit Trail
- #010 — Structured Logging / Observability foundation
- #011 — Knowledge Ingestion foundation
- #012 — Embedding Pipeline foundation
- #013 — Retrieval / Vector Search foundation
- #014 — Grounded RAG response with evidence / citations
- #015 — Controlled read-only Tool Calling foundation
- #016 — Durable Human Approval for higher-risk Tool actions
- #017 — Offline LLM Evaluation foundation
- #018 — AI Security Regression foundation
- #019 — Operational Metrics / Monitoring foundation
- #020 — CI / Release Hardening foundation
- #021 — First Hardened Release Promotion
- #022 — Expanded Evaluation Coverage
- #023 — Deterministic Candidate / Prompt Comparison

## Current Workflow Infrastructure

The repository has an AI-assisted engineering control plane so that fresh Agent sessions do not depend on Chat history.

Required state surfaces:

- `AGENTS.md` — permanent execution rules
- this file — project-wide state
- GitHub Issue — per-task contract
- `docs/issues/` — per-Issue execution snapshots when needed
- Notion — reusable engineering knowledge only
- `scripts/codex_dispatch.py` — local bounded Checkpoint dispatcher
- `.codex-dispatch/` — gitignored local Codex Session metadata
- `scripts/codex_watch.py` — optional local Trigger Layer for Supervisor-authorized CP2 / CP3

The Dispatcher uses Stable `codex exec` as its local execution boundary. It does not attempt to inject prompts into an already-open VS Code/Desktop Codex UI session.

## Current Stable Release State

Repository version `0.1.0` completed its first hardened `develop → main` promotion.

Release evidence:

- Engineering Issue #021 / GitHub Issue #94: completed
- Release PR #95: merged
- frozen develop Head: `595a45f33a0b7cb1453695dc6f7bdb6ed3d8eccc`
- frozen candidate tree: `1b3e3f59dbc142df96913f8f512fc839c88bc0ea`
- Release Verification run `33652934391`: PASS
- Backend regression: 482 passed
- database recovery: PASS
- Dispatcher regression: 87 passed
- main release merge: `5428d31108fd908ab3b8d2d657a1db4915fccdd7`
- main merge tree equals the frozen candidate tree
- main-only release history is content-neutral
- no Git tag / GitHub Release / production deployment was performed

External platform-control debt remains:

- main Branch Protection: disabled
- develop Branch Protection: disabled
- repository Rulesets: none

## Latest Completed Product Engineering Issue

Engineering Issue #023 — Candidate / Prompt Comparison: **completed**

Delivery evidence:

- GitHub Issue #100
- Product PR #101
- verified Feature Head: `633cbe2c3326670657d5e7a57201c2ad49342fef`
- Backend Verification #198 / run `33873126019`: PASS
- Dispatcher Tests #165 / run `33873125872`: PASS
- squash merge on `develop`: `c10ddc26745b1977d27cfe9e55d36969d0c0821f`
- strict Comparison Manifest, same-Suite Candidate reconciliation, deterministic
  deltas and Case transitions, bounded Safety-aware gate, Prompt provenance
  metadata, root-contained loading, and CLI exit `0 / 1 / 2` are complete
- no live Model, Tool, Approval, Database mutation, Product Prompt change, or
  production-data execution was introduced

Engineering Issue #024 — Cross-platform determinism and Watcher completion
evidence: **active at CP3**.

- GitHub Issue #103
- branch: `feature/issue-024-cross-platform-determinism`
- base: `c0c1d14f7b9d216f9d69d69255755f2469eac7a5`
- CP2 publication: `85f848011f4960aa3ed2c6ccd72b328e48d09f80`
- Windows focused verification: `27 passed in 0.61s`
- CP2 is approved; CP3 regression/review is authorized
- scope is limited to LF repository policy, cross-platform Watcher lock tests,
  and explicit handling of succeeded-without-publication state

Important: GitHub Issue/PR numbers are repository-wide platform sequence numbers and remain separate from Engineering Issue IDs.

## Planned Product Sequence

- #023 — Candidate / Prompt Comparison
- later Evaluation work — broader semantic diversity, recorded/live candidate evidence, latency, and cost only under separately approved scope
- deployment/operations work — scheduled when environment and platform controls are defined

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
- Durable Audit Events use stable Actor / Action / Target / Outcome fields and an append-only application boundary.
- RBAC privilege mutations and their Audit Events commit atomically.
- Authentication / Authorization Audit failures use best-effort persistence and must preserve intended 401 / 403 responses.
- Structured runtime logs use server-generated Request IDs and request-scoped ContextVar correlation.
- Runtime request logging must not capture raw Request Body, Query String, Authorization/Cookie headers, or arbitrary unmatched raw paths.
- Runtime Application Logs and durable Audit Events remain separate observability/accountability surfaces.
- Knowledge ingestion treats document content as untrusted data, not executable instructions.
- KnowledgeDocument persistence is normalized and content-addressed with a database idempotency backstop.
- Knowledge admin writes use dedicated RBAC permission and atomic Audit persistence.
- Embedding pipeline sends bounded KnowledgeChunk text only through an explicit external Provider boundary.
- External provider waits must not intentionally hold an open database transaction.
- Persisted embeddings are deterministic per document + pipeline configuration and stored as pgvector vector(1536).
- Provider output is validated before persistence; chunk/vector/API-key data is excluded from Audit and runtime logs.
- Vector storage does not imply Retrieval: similarity search/indexing remains a separate architecture boundary.
- Exact retrieval uses current-config cosine distance with deterministic tie-breaking and bounded Top-K/threshold inputs.
- Raw internal Retrieval requires dedicated `knowledge:read` and is limited to support_agent/admin in V1.
- Retrieval query embeddings are ephemeral; query text/vector are excluded from persistence, Audit content, and runtime logs.
- The shared request DB read transaction must be closed before the external query-embedding Provider wait.
- Retrieved KnowledgeChunk content remains untrusted context; Retrieval does not grant instruction, policy, or tool-execution authority.
- Exact Vector Search is the current correctness baseline; ANN indexes remain evidence-driven future optimization.
- Grounded RAG reuses authorized Retrieval rather than bypassing its RBAC/provenance boundary.
- RAG citations are server-owned: the model may reference only server-assigned source IDs, and final citation provenance is reconstructed from retrieved rows.
- Zero-evidence RAG bypasses generation; the model is not allowed to fill missing evidence from pretrained knowledge.
- Retrieved evidence remains untrusted data inside the generation context and does not gain instruction or tool authority.
- Grounded generation uses structured Provider output plus server-side citation validation; schema-valid output alone is not treated as grounding proof.
- RAG question/answer/chunk content, vectors, API keys, and raw Provider responses are excluded from Audit and runtime logs.
- Grounded RAG does not grant execution authority; Tool Calling is a separate server-controlled capability boundary.
- Controlled Tool Calling uses server-owned Tool definitions and database-backed permission checks.
- Tool arguments are untrusted input and require server-side schema validation before execution.
- V1 executes at most one read-only Tool per request and exposes no Tool definitions during finalization.
- Tool results remain untrusted data and cannot grant additional capability.
- Higher-risk or mutating actions require a separate Human Approval boundary.
- Durable Human Approval binds one exact server-validated action and survives request boundaries.
- Approval decisions use row locking and re-check both approval permission and the original action permission before execution.
- Approval state, higher-risk mutation, and durable Audits commit atomically; model proposal alone never authorizes execution.
- Offline LLM Evaluation uses versioned synthetic Cases and normalized Candidate Results; it is test infrastructure, not Product runtime state.
- Eval Case IDs and Result Case IDs must reconcile exactly so difficult Cases cannot disappear silently.
- Grounded RAG evaluation checks deterministic answerability/citation contracts without claiming full semantic equivalence.
- Tool-choice evaluation checks decision, exact Tool name/arguments, and unauthorized Tool selection without executing Tools.
- Prompt identity is pinned by stable Prompt ID + SHA-256; Prompt drift fails explicitly.
- Safety violations remain a separate gate from aggregate accuracy.
- The committed Eval baseline is a scorer fixture, not evidence of live-model performance.
- Expanded V2 Evaluation contains 120 synthetic cases: normal v2 = 80 (40 RAG / 40 Tool) and security-v2 = 40 (20 RAG / 20 Tool).
- Optional bounded `tag_minimums` fail closed when declared Evaluation families are absent or under-covered while preserving V1 manifest compatibility.
- V2 fixtures are byte-for-byte reproducible from a deterministic stdlib generator with explicit write/check modes and no import-time write side effect.
- Structural tag coverage and scorer-fixture correctness do not prove semantic diversity, Candidate quality, or live-model robustness.
- Normal CI LLM Evaluation performs no live OpenAI call, database mutation, Tool execution, or Approval execution.
- AI Security Regression treats attacker-controlled Prompt, Evidence, Citation, Tool proposal, Arguments, and persisted Approval state as untrusted test inputs.
- Security regression must assert both rejection/safe state and absence of unauthorized side effects.
- Security Eval and Application Boundary regression are separate layers: safe model output does not replace server enforcement, and server enforcement does not replace model-safety tracking.
- Adversarial security fixtures are synthetic data only; normal CI must never execute arbitrary shell, SQL, attacker HTTP, eval/exec, or live red-team Provider calls.
- Operational Metrics complement Structured Logs and durable Audit; they do not replace either.
- Prometheus metrics use a repository-owned custom CollectorRegistry and reviewed low-cardinality labels only.
- HTTP metrics use server-owned route templates, normalized methods, and status classes; raw paths and Request IDs never become labels.
- AI metrics expose only bounded RAG/Agent outcomes and aggregate input/output token totals.
- User/Approval/Document/Chunk IDs, Prompt/Answer content, Tool arguments, model/provider identifiers, and secrets never become metric labels.
- Metrics recording is best-effort telemetry and must not change Product response/error semantics.
- GET /metrics has no Product DB/OpenAI/Tool/Approval dependency and is intentionally excluded from Product HTTP metrics.
- Production access to the unauthenticated scrape endpoint must be restricted by deployment/network policy.

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
- Watcher polling does not authorize work; it only reacts to the remote Supervisor Gate.
- Watcher failures stop instead of automatic unbounded Retry.
- Rework of an already-published CP2/CP3 requires an explicit remote Supervisor marker with a positive attempt number; each attempt has distinct remote Commit evidence and may execute once.
- Chat history is never the execution Source of Truth.

## Known Documentation Debt

- Deterministic V2 Evaluation fixtures require LF bytes, but the Repository does
  not yet pin those paths with `.gitattributes text eol=lf`; Windows Checkout
  with `core.autocrlf=true` can therefore create false byte-drift failures.
- `test_preexisting_unlocked_lock_file_is_reusable` reads a Watcher lock file
  through a second Handle while the exclusive lock is held. This passes with
  POSIX advisory locks but raises `PermissionError` with Windows mandatory
  lock semantics; cross-platform lock metadata inspection needs a separately
  scoped Control Plane fix.

## Supervisor Rule

Never infer project progress from Chat memory alone.
Before issuing new work, reconcile this file with merged Pull Requests and the current `develop` state.

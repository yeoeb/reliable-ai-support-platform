# Engineering Issue #025 — Portfolio readiness

<!-- codex-dispatch-supervisor-approved-through: CP1 -->
<!-- codex-dispatch-write-allow: ["README.md","docs/PORTFOLIO_DEMO.md","docs/issues/issue-025-portfolio-readiness.md"] -->

## Tracking

- Engineering Issue: #025
- GitHub Issue: #106
- Branch: `feature/issue-025-portfolio-readiness`
- Base Head: `50558486c7cc5d429075f1ff4b7a8a36a06876ae`
- Current checkpoint: CP2
- Authorized through: CP1

## Assigned GitHub Issue contract snapshot

- Issue number: GitHub Issue #106 / Engineering Issue #025
- Title: `[Issue #025] Finish portfolio README and reproducible demo guide`
- Source: https://github.com/yeoeb/reliable-ai-support-platform/issues/106
- Captured by Supervisor: 2026-09-04

### Goal

Turn the completed Backend and AI safety implementation into an accurate,
recruiter-readable portfolio entry with a reproducible local demonstration path.

### Acceptance criteria

- README reflects merged capability through Engineering #024.
- Stale roadmap text is removed.
- Completed capability, optional future work, and non-production limitations are
  clearly separated.
- A compact architecture view explains Auth/RBAC, RAG/Tool boundaries,
  Approval, Audit, and Evaluation.
- `docs/PORTFOLIO_DEMO.md` provides an exact Windows PowerShell walkthrough for
  prerequisites, PostgreSQL, Alembic, API startup, Swagger, bounded feature
  demonstrations, deterministic offline verification, optional cost-bearing
  live-provider steps, cleanup, and troubleshooting.
- Synthetic fixtures and fake-provider test evidence are never presented as
  measured live-model quality.
- All referenced paths, endpoints, and commands exist.
- No implementation, dependency, migration, workflow, fixture, or version change.

### Non-goals

No frontend, cloud deployment, live benchmark, Product feature, or release
promotion.

## CP0 — Current-state audit

Verified on `develop`:

- Engineering #001–#024 are completed;
- Backend, Auth/RBAC, Audit, Observability, Knowledge ingestion, Embeddings,
  exact Retrieval, Grounded RAG, controlled Tool Calling, durable Human
  Approval, offline Evaluation, Security Regression, Metrics, CI, and release
  controls exist;
- README still lists Candidate / Prompt Comparison as future work even though
  Engineering #023 completed it;
- README does not present #024 cross-platform determinism work;
- no dedicated portfolio demonstration guide exists;
- project version remains `0.1.0`;
- `main` and `develop` require a later dedicated release reconciliation.

## CP1 — Documentation architecture

### README target structure

Keep the README useful to both recruiters and engineers:

1. concise value proposition and honest maturity label;
2. capability summary;
3. compact system/safety architecture;
4. selected reliability boundaries;
5. verified testing evidence;
6. quick start;
7. links to the detailed portfolio demo and Evaluation instructions;
8. completed milestones;
9. optional future work and explicit non-claims.

Do not turn the README into a complete API manual. Move the reproducible
walkthrough to `docs/PORTFOLIO_DEMO.md`.

### Demo guide requirements

The default path must be deterministic and must not require a live OpenAI call.
When live Embedding/RAG/Agent behavior requires `OPENAI_API_KEY`, label it
optional, explain that it may incur cost, and avoid claiming measured quality.

Every example must use existing endpoints, CLI arguments, and repository paths.
Do not invent seed commands or credentials that the Repository does not provide.
If a full manual API scenario requires state that cannot be created through
existing public commands, say so and route the reader to the verified automated
test instead of fabricating a demo.

### Write allowlist

- `README.md`
- `docs/PORTFOLIO_DEMO.md`
- `docs/issues/issue-025-portfolio-readiness.md`

### Frozen surfaces

- `app/`
- `tests/`
- `scripts/`
- `evals/`
- `alembic/` and migrations
- dependency and version files
- GitHub workflows
- `AGENTS.md`
- `docs/PROJECT_STATE.md`

## CP2 — Documentation implementation

Authorized. Work only inside the machine-readable allowlist.

Implementation state: bounded documentation edits completed locally; awaiting
Dispatcher publication and Supervisor review.

Implemented in this slice:

- replaced the stale README with a recruiter-readable capability, architecture,
  reliability, evidence, quick-start, milestone, limitation, and future-work
  view;
- added `docs/PORTFOLIO_DEMO.md` with a Windows PowerShell path for
  PostgreSQL, Alembic, API/Swagger, Auth/RBAC, fake-provider feature tests,
  deterministic Evaluation, optional cost-bearing live providers, cleanup, and
  troubleshooting;
- documented the absence of a seeded administrator/privilege-bootstrap command
  and routed deterministic privileged demonstrations to existing automated
  tests rather than inventing credentials or SQL.

Required evidence:

- changed-file list;
- endpoint and CLI source audit;
- local-link/path audit;
- confirmation no live provider or production claim was introduced;
- generator check result when Python is available;
- `git diff --check`.

Local CP2 evidence (2026-09-04):

- changed files: `README.md`, `docs/PORTFOLIO_DEMO.md`, and this execution
  note; all are inside the machine-readable write allowlist;
- endpoint/CLI audit: PASS — 15 documented route declarations and eight CLI
  arguments/commands were matched to current source or CI configuration;
- local-link/path audit: PASS — four README links and 17 explicitly referenced
  repository paths resolve; all 17 PowerShell blocks parse without syntax
  errors;
- claim audit: PASS — the default demo performs no live provider call, the
  optional live path is labeled cost-bearing/nondeterministic, synthetic and
  fake-provider evidence is not presented as measured model quality, and no
  production-readiness claim was introduced;
- generator check: UNAVAILABLE — `python` resolves to the repository virtual
  environment, whose configured base Microsoft Store Python executable is
  absent; invocation stopped before the generator ran (exit 103), so this is
  environment evidence rather than a fixture-check result;
- `git diff --check`: PASS for tracked edits; the equivalent no-index check for
  the new untracked demo guide also reports no whitespace errors;
- Supervisor approval and write-allow control markers are unchanged.

## CP3 — Verification

Not authorized until CP2 is published and reviewed.

## CP4 — Portfolio review

Not authorized.

## CP5 — Knowledge and completion

Not authorized.

## CP6 — Exact-head delivery

Not authorized.

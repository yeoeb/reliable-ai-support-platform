# Engineering Issue #024 — Cross-platform determinism and Watcher completion evidence

<!-- codex-dispatch-supervisor-approved-through: CP6 -->
<!-- codex-dispatch-write-allow: [".gitattributes","scripts/codex_watch.py","tests/test_codex_watch.py","tests/test_evaluation_generator.py","docs/issues/issue-024-cross-platform-determinism.md"] -->

- GitHub Issue: #103
- Branch: `feature/issue-024-cross-platform-determinism`
- Base: `develop@c0c1d14f7b9d216f9d69d69255755f2469eac7a5`
- Current checkpoint: completed
- Authorized through: CP6
- Owner model: Supervisor defines gates; Watcher Agent implements CP2/CP3.

## Assigned GitHub Issue contract snapshot

- Issue number: GitHub Issue #103 / Engineering Issue #024
- Title: `[Issue #024] Harden cross-platform determinism and Watcher completion evidence`
- Source: https://github.com/yeoeb/reliable-ai-support-platform/issues/103
- Captured by Supervisor: 2026-09-04

### Goal

Eliminate the verified Windows-specific false failures and make Watcher completion state fail closed when publication evidence is missing.

### Scope and acceptance criteria

- force LF for deterministic V2 and security-v2 fixture files;
- prove checkout bytes remain compatible with `generate_eval_suite_v2.py --check`;
- preserve exclusive Watcher locking on Windows and POSIX;
- test lock metadata without a second handle while an exclusive Windows lock is held;
- explicitly reject local `succeeded` state without a matching remote checkpoint;
- pass focused tests, Dispatcher Tests, and Backend Verification.

### Non-goals

- no Product API, Database, Migration, Evaluation scoring, fixture-content, or CI architecture changes;
- no weakening of the actual file lock;
- no automatic destructive state repair.

### Verification

- `python scripts/generate_eval_suite_v2.py --check`
- `python -m pytest tests/test_codex_watch.py tests/test_evaluation_generator.py -q`
- Windows host verification
- existing GitHub Actions verification

## CP0 — Problem framing

Issue #023 exposed three infrastructure defects on a verified Windows host:

1. byte-deterministic Evaluation fixtures can be checked out as CRLF when Git inherits `core.autocrlf=true`;
2. a Watcher test opens the lock file through a second handle while an exclusive Windows lock is held;
3. local dispatch state can say `succeeded` while no remote checkpoint was published, and the Watcher can silently treat that contradiction as complete.

These are control-plane and reproducibility defects, not Product behavior changes.

## CP1 — Contract and design gate

### Required behavior

1. Add repository attributes that force LF for the six generated files under:
   - `evals/suites/v2/`
   - `evals/suites/security-v2/`
2. Preserve exclusive lock behavior on Windows and POSIX.
3. Separate lock-metadata verification from cross-process exclusion verification:
   - metadata is written through the already-owned handle;
   - unit tests must not require a second read handle while a Windows lock is held.
4. In `next_write_checkpoint`, a local `succeeded` state without the matching remote checkpoint must not return “nothing to do.”
5. Contradictory state must raise a clear `DispatchError` requiring Supervisor/operator reconciliation. Do not automatically discard, overwrite, or replay state.

### Write allowlist

- `.gitattributes`
- `scripts/codex_watch.py`
- `tests/test_codex_watch.py`
- `tests/test_evaluation_generator.py` only if needed for repository-policy coverage
- `docs/issues/issue-024-cross-platform-determinism.md`

Supervisor-only state files are outside the Agent write allowlist.

### Frozen surfaces

- `app/`
- `alembic/`
- database schema and migrations
- Evaluation generator logic, scoring logic, and fixture semantic content
- GitHub Actions workflow architecture
- unrelated documentation

### Required tests

- Existing Watcher lock exclusion tests remain green.
- Stale/unlocked lock-file reuse is proven without a second handle read during the active lock.
- Lock metadata writing has direct unit coverage.
- `last_status=succeeded` + missing remote checkpoint raises `DispatchError`.
- Valid remote checkpoint state remains a no-op.
- `python scripts/generate_eval_suite_v2.py --check`
- `python -m pytest tests/test_codex_watch.py tests/test_evaluation_generator.py -q`
- `git diff --check`

### Host/CI evidence required before merge

- Windows host focused verification.
- A checkout/index proof that all six deterministic fixtures resolve to `eol=lf`.
- Dispatcher Tests and Backend Verification on the frozen PR head.

## CP2 — Implementation

Authorized. Agent may implement only within the allowlist.

Bounded implementation completed locally:

- pinned all six generated V2 fixture paths to `text eol=lf`;
- separated lock metadata writing from lock acquisition and covered metadata
  through the already-owned handle;
- removed the active-lock second-handle read from stale lock-file reuse coverage;
- made local `succeeded` state without matching remote publication fail closed
  with explicit Supervisor/operator reconciliation guidance;
- preserved the no-op when matching remote publication evidence exists.

Current state: CP2 is published at
`85f848011f4960aa3ed2c6ccd72b328e48d09f80`. Supervisor Diff review confirms
the changed paths remain inside the allowlist. Windows Host focused verification
passed: `27 passed in 0.61s`; this suite includes the deterministic generator
check path. Attribute resolution, zero-CR checkout inspection, and Diff hygiene
also passed.

## CP3 — Review and verification

Authorized. Run the bounded regression and inspect the final Diff. Do not change
Product, Database, Migration, Evaluation fixture semantics, scorer behavior, or
CI architecture. Record exact commands and results.

Verification evidence (Windows sandbox, 2026-09-04):

- `python scripts/generate_eval_suite_v2.py --check`: **BLOCKED** before
  script startup (exit `1`); `.venv` references an unavailable Microsoft Store
  Python 3.11 installation.
- `python -m pytest tests/test_codex_watch.py tests/test_evaluation_generator.py -q`:
  **BLOCKED** before test collection (exit `1`) for the same interpreter issue.
- `git check-attr text eol -- evals/suites/v2/suite.json evals/suites/v2/cases.jsonl evals/suites/v2/baseline_results.jsonl evals/suites/security-v2/suite.json evals/suites/security-v2/cases.jsonl evals/suites/security-v2/baseline_results.jsonl`:
  **PASS**; every path resolves to `text: set` and `eol: lf`.
- `git ls-files --eol -- evals/suites/v2/suite.json evals/suites/v2/cases.jsonl evals/suites/v2/baseline_results.jsonl evals/suites/security-v2/suite.json evals/suites/security-v2/cases.jsonl evals/suites/security-v2/baseline_results.jsonl`:
  **PASS**; every path reports `i/lf`, `w/lf`, and `attr/text eol=lf`.
- `git diff --check`: **PASS**.
- `git diff c0c1d14f7b9d216f9d69d69255755f2469eac7a5..HEAD`:
  inspected; no Product, Database, Migration, fixture-content, scorer, or CI
  workflow implementation changed.

Windows Host completed the missing Python verification on the published CP3
state:

- focused Watcher + generator suite: `27 passed in 0.61s`;
- Dispatcher + Watcher + generator regression: `60 passed in 0.85s`.

Together with the recorded attribute, checkout, Diff, and frozen-surface
evidence, CP3 passes.

## CP4 — Merge readiness

Status: **passed**.

Acceptance mapping:

- deterministic fixtures use six explicit `text eol=lf` rules;
- Windows checkout reports `i/lf`, `w/lf`, and `eol=lf` for all six paths;
- generator behavior is covered by the passing focused suite;
- cross-process exclusion remains covered independently from metadata writing;
- metadata is verified through the owned handle, avoiding Windows mandatory-lock
  second-handle reads;
- local `succeeded` without remote publication raises explicit reconciliation
  error, while matching remote publication remains a no-op;
- base-to-head review found no Product, Database, Migration, fixture-content,
  scorer, or CI workflow change;
- the Supervisor-authored `AGENTS.md` offline fallback requires a complete,
  committed Issue snapshot and remains fail closed on absence or ambiguity.

No merge-readiness defect was found. Final PR-head GitHub Actions evidence is
still required before merge.

## CP5 — Knowledge and completion

Status: **passed**.

Reusable findings were deduplicated into existing Notion Knowledge:

- Offline LLM Evaluation: repository `.gitattributes text eol=lf`, CRLF
  diagnosis, and byte-reproducibility checks;
- AI Coding Supervisor Workflow: machine-readable marker cardinality,
  `succeeded` versus publication evidence, control-plane contradiction handling,
  and Supervisor-committed offline Issue contract snapshots.

No duplicate Knowledge page was created.

## CP6 — Exact-head delivery

Status: **completed**.

Delivery evidence:

- Product PR: #104;
- exact verified Feature Head:
  `bbf1974aa34218ad9603fcd9e98a542b8ea2e154`;
- Backend Verification #200 / run `33881260083`: **PASS**;
- Dispatcher Tests #169 / run `33881260111`: **PASS**;
- Windows Host focused verification: `27 passed in 0.61s`;
- Windows Host Control Plane regression: `60 passed in 0.85s`;
- squash merge on `develop`:
  `84d1ee45f268d65c136180d4cdf4c5cfbb5f8be7`;
- no Feature Branch commit was added after exact-head CI.

All CP0–CP6 checkpoints are complete.

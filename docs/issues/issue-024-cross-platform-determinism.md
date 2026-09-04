# Engineering Issue #024 — Cross-platform determinism and Watcher completion evidence

- GitHub Issue: #103
- Branch: `feature/issue-024-cross-platform-determinism`
- Base: `develop@c0c1d14f7b9d216f9d69d69255755f2469eac7a5`
- Current checkpoint: CP2
- Authorized through: CP1
- Owner model: Supervisor defines gates; Watcher Agent implements CP2/CP3.

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

## CP3 — Review and verification

Not authorized until CP2 evidence is published and reviewed.

## CP4 — Merge readiness

Not authorized.

## CP5 — Knowledge and completion

Not authorized.

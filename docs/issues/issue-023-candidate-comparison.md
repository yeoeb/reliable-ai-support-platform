# Engineering Issue #023 — Candidate / Prompt Comparison

<!-- codex-dispatch-supervisor-approved-through: CP2 -->
<!-- codex-dispatch-write-allow: ["app/evaluation/schemas.py","app/evaluation/comparison.py","app/evaluation/comparison_loader.py","app/evaluation/comparison_runner.py","evals/README.md","evals/comparisons/v2-reference.json","tests/test_evaluation_comparison.py","tests/test_evaluation_comparison_loader.py","tests/test_evaluation_comparison_runner.py","docs/issues/issue-023-candidate-comparison.md"] -->

## Tracking

- Engineering Issue: #023
- GitHub Issue: #100
- Branch: `feature/issue-023-candidate-comparison`
- Base Head: `949d206c2c1b182c6bd45b53753f0086d9befd9b`

## Goal

Add deterministic offline comparison for two normalized Evaluation candidates on one versioned Suite, including declared Prompt identity, metric deltas, Case-level transitions, and a bounded regression gate.

## CP0 — Existing Capability / Gap Inventory

Status: **completed**

Verified on `develop`:

- one Candidate result file can be loaded, exactly reconciled, scored, thresholded, and emitted as deterministic JSON;
- existing `EvaluationReport` contains Candidate label, Suite Prompt fingerprints, RAG/Tool metrics, Safety violations, and failed Cases;
- the Suite owns the current Prompt fingerprints, so current reports cannot distinguish Candidate-specific Prompt versions;
- no comparison schema, comparison loader, delta report, Case transition list, or comparison gate exists;
- 120 deterministic V2 Cases and bounded `tag_minimums` are available from #022;
- existing scorer and single-Candidate runner are stable compatibility boundaries.

Gap:

> independent scores are available, but the repository cannot yet show exactly which Cases regressed or improved from Candidate A to Candidate B.

## CP1 — Architecture

Status: **completed / Supervisor-approved**

### Manifest

Create a strict versioned data-only Comparison Manifest with:

- stable comparison ID;
- one Suite manifest reference;
- baseline and challenger Candidate descriptors;
- bounded static policy.

Each Candidate descriptor contains a distinct bounded ID, one relative result-file path, and a declared `PromptFingerprintSet`.

Prompt metadata is declared provenance. Preserve and compare it, but do not claim it proves how the result file was generated.

### Path Boundary

The CLI receives an explicit Evaluation root plus a comparison path relative to that root. Resolve every referenced file under the same root. Reject absolute paths and traversal outside the root.

No dynamic imports, callables, expressions, shell, SQL, URL, environment lookup, Tool executor, or Approval executor.

### Comparison

1. load one Suite;
2. load both Candidate result files against it;
3. reuse existing `evaluate()` unchanged;
4. derive deterministic challenger-minus-baseline metric deltas;
5. derive sorted `regressed_case_ids` and `improved_case_ids` from failed-Case sets;
6. compare declared RAG and Tool Prompt fingerprints;
7. apply the static policy;
8. emit one compact sorted JSON report.

Required report content:

- both existing Evaluation reports;
- Candidate-declared Prompt fingerprints;
- aggregate/RAG/Tool metric deltas;
- Safety violation delta;
- Prompt-change flags;
- deterministic Case transition lists;
- explicit gate reasons and final pass/fail.

### Policy

Bounded typed fields only:

- `require_challenger_thresholds_pass: bool = true`;
- `max_case_pass_rate_drop: float = 0` within `0..1`;
- `max_safety_violation_increase: int = 0`;
- `max_new_failed_cases: int = 0`.

A new Safety failure must fail the comparison even if another Case improves and the aggregate score is unchanged or better.

### CLI

```text
python -m app.evaluation.comparison_runner
  --root evals
  --comparison comparisons/v2-reference.json
```

Exit codes:

- `0`: valid comparison and gate pass;
- `1`: valid comparison and gate fail;
- `2`: malformed input or CLI usage.

### Reference Fixture

`evals/comparisons/v2-reference.json` compares the existing V2 known-good results with themselves under two distinct Candidate labels.

It proves zero-delta comparison behavior only. It is not measured Model or Prompt quality.

## CP2 Ordered Slices

1. add strict Comparison schemas;
2. add root-contained manifest/result loading;
3. implement report and bounded gate by reusing `evaluate()`;
4. add deterministic CLI;
5. add neutral V2 reference manifest;
6. add focused schema/loader/comparison/CLI tests;
7. update `evals/README.md`.

## CP2 Focused Verification

Run:

```text
python -m pytest
  tests/test_evaluation_comparison.py
  tests/test_evaluation_comparison_loader.py
  tests/test_evaluation_comparison_runner.py
  tests/test_evaluation_loader.py
  tests/test_evaluation_scorer.py
  tests/test_evaluation_baseline.py
  tests/test_evaluation_v2_baseline.py
  -q
```

Also run the reference comparison CLI twice and verify identical stdout bytes.

Do not run the full repository regression in CP2. Full regression belongs to CP3.

## Frozen Boundaries

Do not modify:

- `app/evaluation/scorer.py`;
- `app/evaluation/runner.py`;
- existing Suite, Case, or Result fixtures;
- Product prompts, API, Service, Provider, Tool, or Approval code;
- Database models or migrations;
- GitHub workflows;
- `docs/PROJECT_STATE.md`.

Only the machine-readable write allowlist at the top is authoritative.

## Acceptance Evidence Required from CP2

- changed files;
- manifest and policy validation evidence;
- path traversal rejection;
- zero-delta reference output;
- regression, improvement, and Safety masking tests;
- Prompt change detection;
- CLI exit `0 / 1 / 2`;
- focused pytest result;
- confirmation existing scorer/runner/Product code is unchanged;
- blockers, if any.

Do not mark CP3+ complete.

## Checkpoints

- [x] CP0 — Existing comparison-gap inventory
- [x] CP1 — Candidate / Prompt comparison architecture
- [x] CP2 — Bounded comparison implementation
- [ ] CP3 — Full regression / determinism verification
- [ ] CP4 — Comparison validity / safety review
- [ ] CP5 — Knowledge / documentation
- [ ] CP6 — exact-Head delivery

## Current State

Remote Supervisor approval: **CP2**.

Reviewed implementation lineage:

- `0b88391a11f22a588445043a3a439006023f000b` — initial CP2 implementation;
- `9624f72496d416b6337afee8a4aed3d8282a1501` — bounded integer Policy remediation;
- `8121d4c7c89c3977b614f748f887e359da8ed3ff` — required Negative Test coverage;
- `3a67f0558a8dd89c7ad48b40648ad8d45d6f5e26` — remediation execution note.

Host CP2 evidence:

- initial focused verification: **39 passed in 8.56s**;
- process-level reference CLI exits: **0 / 0**;
- process-level repeated stdout: **identical**;
- reference gate: **passed** with empty transition lists;
- post-remediation focused verification: **48 passed in 2.43s**;
- focused CLI Test reruns and compares deterministic output at the remediated Head;
- all changed paths are inside the approved write allowlist;
- frozen scorer, single-Candidate runner, fixtures, Product runtime, migrations,
  and workflows remain unchanged.

CP2 is complete.

Next authorized action: **CP3 — Full regression / determinism verification**.

CP4+ have not started.

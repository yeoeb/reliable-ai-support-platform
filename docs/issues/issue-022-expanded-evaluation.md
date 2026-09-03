# Engineering Issue #022 — Expanded Evaluation Coverage

<!-- codex-dispatch-supervisor-approved-through: CP4 -->
<!-- codex-dispatch-write-allow: ["app/evaluation/schemas.py","app/evaluation/loader.py","scripts/generate_eval_suite_v2.py","evals/README.md","evals/suites/v2/**","evals/suites/security-v2/**","tests/test_evaluation_coverage.py","tests/test_evaluation_v2_baseline.py","tests/test_evaluation_generator.py","docs/issues/issue-022-expanded-evaluation.md"] -->

## Tracking

- Engineering Issue: #022
- GitHub Issue: #97
- Branch: `feature/issue-022-expanded-evaluation`

## Goal

Expand deterministic offline evaluation coverage to a reproducible 120-case V2 corpus while preserving the existing scorer and Product runtime semantics.

Candidate / Prompt A-B comparison is intentionally deferred to #023.

## CP0 — Existing Eval Inventory

Status: **completed**

Verified on `develop`:

- `v1`: 12 cases
  - 6 RAG
  - 6 Tool
- `security-v1`: 16 cases
- loader capacity: 1000 JSONL records / 1 MiB bounded file
- current case types:
  - `rag_grounding`
  - `tool_choice`
- current case schema already includes `tags`
- current manifest has no tag coverage minimum contract
- current scorer semantics:
  - case pass rate
  - explicit Safety violation count
  - RAG answerability/citation metrics
  - Tool decision/name/argument/unauthorized metrics
- current runner is deterministic JSON stdout with exit 0/1/2
- Prompt IDs + SHA-256 are pinned and drift fails loading
- result Case IDs must exactly reconcile with suite Case IDs
- all committed data is synthetic
- no live OpenAI / Tool / Approval execution occurs in normal Eval CI

Gap:

> parser capacity is already sufficient; the missing control is corpus breadth plus deterministic coverage guarantees.

## CP1 — Architecture

Status: **completed / Supervisor-approved**

### Scope Split

#022 handles:

- V2 corpus expansion
- deterministic fixture generation
- manifest tag minimum coverage validation
- backward compatibility

#023 will handle:

- Candidate A/B comparison
- Prompt-version comparison metadata
- regression/improvement reporting

Do not implement #023 behavior in this Issue.

### V2 Targets

#### Normal V2

`evals/suites/v2`

Exactly 80 cases:

- 40 RAG
- 40 Tool

RAG families, 10 each:

1. single-source grounded
2. multi-source grounded
3. insufficient evidence
4. selective evidence / distractor source

Tool families, 10 each:

1. direct answer
2. `platform_readiness`
3. `grant_support_agent_role` with deterministic synthetic UUID
4. no tools available / direct answer

#### Security V2

`evals/suites/security-v2`

Exactly 40 cases:

- 20 RAG
- 20 Tool

RAG adversarial coverage:

- prompt injection
- citation forgery pressure
- insufficient-evidence coercion / data leakage
- source authority confusion

Tool adversarial coverage:

- unauthorized shell / SQL / URL / code-exec style proposals
- argument injection
- Approval bypass pressure
- invented schema / hidden Tool selection

All attack strings remain inert test data.

### Manifest Coverage Contract

Add optional:

`tag_minimums: dict[str, int]`

Backward-compatible requirement:

- old v1/security-v1 without the field still load unchanged.

Validation:

- bounded mapping size
- bounded non-empty tag keys
- positive bounded minimum counts
- loader counts tags after all cases are validated
- every required tag must meet minimum
- unknown/missing tag fails closed
- under-covered tag fails closed
- exact minimum passes
- failure is `EvaluationInputError`
- no dynamic expression/eval language

Suggested bounds:

- max 50 required tags
- tag key max 100 chars
- minimum range 1..1000

### Generator

Create:

`scripts/generate_eval_suite_v2.py`

Requirements:

- stdlib only
- no `random`
- no runtime UUID generation
- no current date/time
- no network
- no subprocess
- no environment-secret access
- no production data
- deterministic ordering
- deterministic compact JSONL serialization
- pure rendering functions
- import has no write side effect
- optional explicit CLI write/check mode is acceptable
- synthetic UUIDs derive from fixed index formatting

The committed V2 cases and baseline files must equal generator output byte-for-byte.

### Baseline

Known-good baseline files are scorer fixtures only.

They do **not** claim live-model performance.

Existing scorer semantics must remain unchanged.

### Prompt Identity

V2 and security-v2 pin the same current Product Prompt IDs / SHA-256 fingerprints as v1/security-v1.

Do not modify Product prompt text or provider code.

### Backward Compatibility

Must preserve:

- v1 count = 12
- security-v1 count = 16
- existing manifest loading
- current scorer reasons/metrics
- current runner exit behavior
- current fingerprint drift rejection

### CP2 Ordered Slices

1. extend manifest schema with optional bounded `tag_minimums`
2. enforce tag coverage in loader after validated cases load
3. add focused coverage-contract tests
4. add deterministic V2 fixture generator
5. generate/commit normal v2 80-case fixtures
6. generate/commit security-v2 40-case fixtures
7. add V2 baseline/determinism tests
8. update `evals/README.md`

### CP2 Focused Verification

Run only the evaluation-focused set in CP2:

```text
python -m pytest
  tests/test_evaluation_coverage.py
  tests/test_evaluation_v2_baseline.py
  tests/test_evaluation_generator.py
  tests/test_evaluation_loader.py
  tests/test_evaluation_scorer.py
  tests/test_evaluation_baseline.py
  -q
```

If the generator exposes `--check`, run it too.

Do **not** run the full repository regression in CP2.

Full regression belongs to CP3.

### Write Scope

Only the machine-readable allowlist at the top is authoritative.

No write to:

- `app/evaluation/scorer.py`
- `app/evaluation/runner.py`
- Product API / Service / Provider code
- Tool / Approval code
- migrations / models / repositories
- GitHub workflows
- `docs/PROJECT_STATE.md`
- secrets/config unrelated to Eval fixtures

If a non-allowlisted production file is necessary, stop and report the proposed scope expansion.

## Acceptance Evidence Required from CP2

Report:

- changed files
- exact normal/security V2 case counts
- RAG/Tool split counts
- tag coverage requirements and observed counts
- focused pytest result
- generator reproducibility result
- backward compatibility result
- confirmation scorer/runner/Product prompts were not changed
- confirmation no live provider/Tool/Approval execution was introduced
- blockers, if any

Do not mark CP3+ complete.

## Checkpoints

- [x] CP0 — Existing Eval inventory / gap analysis
- [x] CP1 — Expanded coverage architecture
- [x] CP2 — Bounded corpus + coverage implementation
- [x] CP3 — Full regression / determinism verification
- [x] CP4 — Eval quality / safety review
- [ ] CP5 — Knowledge / documentation
- [ ] CP6 — exact-Head delivery

## Current State

Remote Supervisor approval: **CP4**.

Published CP2 implementation Head:

`5d6cddd028fb9c9c32cc110623cbe1f52cf4e69b`

Verified:

- optional bounded `tag_minimums` schema and fail-closed loader enforcement;
- deterministic stdlib generator with explicit `--write` / `--check` modes;
- normal V2: 80 cases (40 RAG / 40 Tool);
- security V2: 40 cases (20 RAG / 20 Tool);
- all changed files remain inside the remote write allowlist;
- scorer, runner, Product prompts, Product runtime, migrations, and workflows are unchanged;
- no live Provider, Tool, Approval, network, or production-data execution was introduced.

Host PowerShell exact-Head verification:

- Working Tree: clean
- Generator `--check`: PASS
- focused pytest: **36 passed in 10.37s**
- Python: 3.11.9
- pytest: 8.4.2

The earlier Codex Sandbox exit `103` was isolated to Sandbox access to the Microsoft Store Python runtime. Host verification confirms the project virtual environment and dependencies are runnable.

## CP3 Verification Evidence

Exact verified Head:

`d07a9aeb6ac7414f99115148622bd83b9ce4cd83`

GitHub-hosted evidence:

- Backend Verification #193 / run `33752097580`: **PASS**
- Backend regression: **501 passed**
- Database recovery: **1 passed**
- Dispatcher Tests #157 / run `33752097566`: **87 passed**
- PostgreSQL + pgvector 0.8.6: PASS
- Alembic upgrade head: PASS
- Alembic downgrade -1: PASS
- Alembic re-upgrade head: PASS

The local Host run reached 497 passed / 5 environment-dependent failures because local PostgreSQL was unavailable and Windows denied a read while an exclusive lock file was held. The same exact Remote Head passed the configured Linux/PostgreSQL verification, so no #022 Product regression is indicated.

## CP4 Evaluation Quality / Safety Review

Reviewed Head:

`5687f168a97655843782236c6a48f63dcdd96d87`

Result: **PASS — no blocking findings**.

Verified:

- all 120 cases map to declared RAG / Tool families and every manifest `tag_minimums` value is met exactly;
- the loader enforces bounded, strict integer minimums and fails closed for missing or under-covered tags;
- all security payloads are inert JSON fixture strings; the generator performs no shell, SQL, URL, Python, Tool, Approval, network, secret, or production-data execution;
- unauthorized, invented-schema, and hidden-Tool proposals resolve to `direct_answer`; argument-injection and Approval-bypass pressure retain only the declared Tool plus exact synthetic `user_id` arguments;
- Tool-choice fixtures do not execute the selected Tool and therefore cannot bypass the downstream Human Approval boundary;
- Prompt IDs / SHA-256 fingerprints remain pinned to V1 and Product prompts/runtime are unchanged;
- `baseline_results.jsonl` and its 100% score are explicitly documented as deterministic scorer fixtures, not evidence of live-model quality.

Non-blocking limitation:

- generated families deliberately use templated variations. `tag_minimums` proves structural family coverage, not semantic diversity or live-model robustness. Future live/candidate comparison and broader semantic diversity require a separately scoped Evaluation Issue; Candidate / Prompt comparison remains deferred to #023.

Next authorized action: **CP5 — Knowledge / documentation**.

No later Checkpoint has started.

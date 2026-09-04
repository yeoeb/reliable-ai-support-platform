# Engineering Issue #026 — Second Hardened Release Promotion

<!-- codex-dispatch-supervisor-approved-through: CP6 -->
<!-- codex-dispatch-write-allow: ["pyproject.toml","app/main.py","docs/PROJECT_STATE.md","docs/issues/issue-026-second-hardened-release.md"] -->

## Tracking

- Engineering Issue: #026
- GitHub Issue: #109
- Branch: `feature/issue-026-second-hardened-release`
- Base Head: `f84deb1f8b8c331dc1830a9d9e627cb34c408a51`
- Target version: `0.2.0`
- Current checkpoint: completed
- Authorized through: CP6

## Assigned GitHub Issue contract snapshot

- Issue number: GitHub Issue #109 / Engineering Issue #026
- Title: `[Issue #026] Promote second hardened release 0.2.0`
- Source: https://github.com/yeoeb/reliable-ai-support-platform/issues/109
- Captured by Supervisor: 2026-09-04

### Goal

Promote the fully documented and verified `develop` state through the existing
exact-candidate release gate into stable `main` as version `0.2.0`.

### Scope

- Prepare consistent `0.2.0` version metadata on this bounded branch.
- Merge the exact verified preparation Head into `develop`.
- Freeze the resulting `develop` Head and tree.
- Open the same-repository `develop → main` Release PR.
- Require exact-head Release Verification and merge with a merge commit.
- Prove post-release main/candidate tree equality and reconcile final state.

### Acceptance criteria

- `pyproject.toml [project].version` and the single static FastAPI version both
  equal strict SemVer `0.2.0`.
- No Product behavior, dependency, migration, fixture, or workflow change.
- Preparation PR passes focused version/preflight and normal exact-head CI.
- Release PR is exactly same-repository `develop → main`.
- Main-only content is empty before release.
- Release Verification passes for the frozen current `develop` Head.
- Release PR uses merge commit.
- Post-merge `main` tree equals the frozen candidate tree.
- Exact SHAs, run IDs, merge evidence, and external control debt are recorded.

### Non-goals

No Git tag, GitHub Release, production deployment, production migration,
credential use, traffic shift, rollback, package/container publication,
frontend, cloud work, live benchmark, Product feature, workflow redesign,
Branch Protection mutation, or Ruleset mutation.

### Verification

- Focused version/release-preflight tests.
- Exact-head branch CI.
- Exact-head Release Verification.
- Post-release parent/tree/content-neutrality audit.
- Diff and scope audit.

## CP0 — Context bootstrap and contradiction detection

Completed by Supervisor on 2026-09-04.

- Required sources were read in authority order.
- Current `develop`: `f84deb1f8b8c331dc1830a9d9e627cb34c408a51`.
- Current `main`: `5428d31108fd908ab3b8d2d657a1db4915fccdd7`.
- Merge-base: `595a45f33a0b7cb1453695dc6f7bdb6ed3d8eccc`.
- Main is one content-neutral release merge ahead of the merge-base.
- `develop` contains nine later integration commits.
- Existing release contract remains valid and requires exact `develop → main`.
- Current project and FastAPI versions are both `0.1.0`.
- No `v0.2.0` publication is planned; the verifier only checks identity.
- No Source-of-Truth contradiction was found.

## CP1 — Bounded plan

Completed and approved by Supervisor on 2026-09-04.

### Allowed write set

- `pyproject.toml`
- `app/main.py`
- `docs/PROJECT_STATE.md`
- this execution note

### Plan

1. Change only the two version literals to `0.2.0`.
2. Mark #026 active in project state without claiming release success.
3. Verify version consistency, focused release tests, diff scope, and CI.
4. Merge the exact preparation Head to `develop`.
5. Freeze `develop`, open the exact Release PR, and await Release Verification.
6. Merge by merge commit only after unchanged-head evidence.
7. Verify main/candidate tree equality and archive completion evidence.

### Risks and controls

- Moving `develop`: freeze and re-check its exact Head before release merge.
- Stale or duplicate version: static consistency and tag-identity verification.
- Main-only drift: release-contract verifier fails closed.
- CI evidence invalidation: no branch commit after exact-head CI.
- Release/deployment ambiguity: explicitly record repository promotion only.

## CP2 — Version preparation

Completed on 2026-09-04.

- `pyproject.toml [project].version`: `0.1.0 → 0.2.0`.
- Static FastAPI `version=` literal: `0.1.0 → 0.2.0`.
- Project state marks #026 active without claiming release completion.
- No behavior, dependency, migration, fixture, workflow, or release-contract
  change was introduced.
- Diff scope contains only the four allowlisted paths.
- Static source inspection confirms exactly one project version and one FastAPI
  version, both `0.2.0`.

## CP3 — Exact-head verification

Completed.

Preparation PR #110 verified exact Head
`fb9a58c2e5cbf912034adc90cc9bac5531820af2`:

- Backend Verification #202 / run `33905982032`: PASS
- database recovery: PASS
- PostgreSQL + pgvector: PASS
- Alembic upgrade / downgrade / re-upgrade: PASS
- Dispatcher Tests #177 / run `33905982059`: PASS
- version sources: project `0.2.0`, FastAPI `0.2.0`

No branch commit followed the exact-head evidence.

## CP4 — Release review

Completed.

- Preparation PR #110 was clean/mergeable and merged to `develop` as
  `443b4280dc335f5a3627441393b2a6353a75f1b5`.
- Frozen develop Head:
  `443b4280dc335f5a3627441393b2a6353a75f1b5`.
- Frozen candidate tree:
  `e6bca378fc880757bfdc40dda3d3e8533264cc32`.
- Pre-release main:
  `5428d31108fd908ab3b8d2d657a1db4915fccdd7`.
- Merge-base:
  `595a45f33a0b7cb1453695dc6f7bdb6ed3d8eccc`.
- Main-only content diff from merge-base: empty.
- Proposed tag identity `v0.2.0`: absent; no tag was created.
- Release PR #111 was exactly same-repository `develop → main`.

## CP5 — Knowledge and documentation

Completed.

- Existing release-process documentation remains the reusable Source of Truth;
  no duplicate Knowledge entry was created.
- Final project state records repository-promotion evidence and preserves the
  deployment/platform-control boundary.
- A Work Log is recorded separately after verified delivery.

## CP6 — Exact-head delivery

Completed.

Release Verification #2 / run `33906154568` passed for exact frozen Head
`443b4280dc335f5a3627441393b2a6353a75f1b5`:

- release-contract: PASS
- Backend Verification: PASS
- database recovery: PASS
- Dispatcher Tests: PASS

Release PR #111 remained clean/mergeable with Head equal to current `develop`
and was merged using **merge commit**.

Release merge:

`ad743c6dc3746c41fafb32cffb7688da03f8d41b`

Parents:

- previous main: `5428d31108fd908ab3b8d2d657a1db4915fccdd7`
- frozen develop: `443b4280dc335f5a3627441393b2a6353a75f1b5`

Post-release proof:

- main merge tree:
  `e6bca378fc880757bfdc40dda3d3e8533264cc32`
- frozen candidate tree:
  `e6bca378fc880757bfdc40dda3d3e8533264cc32`
- tree equality: PASS
- `develop...main`: main ahead by two content-neutral release merge commits
- file diff: empty

Explicitly not performed:

- Git tag creation
- GitHub Release publication
- production deployment or migration
- package/container publication
- traffic shift or rollback
- Branch Protection or Ruleset mutation

External platform-control debt remains:

- main Branch Protection: disabled
- develop Branch Protection: disabled
- repository Rulesets: none

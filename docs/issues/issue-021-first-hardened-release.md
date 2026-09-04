# Engineering Issue #021 — First Hardened Release Promotion

## Status

**Completed**

## Tracking

- Engineering Issue: #021
- GitHub Issue: #94
- Release PR: #95
- Version: `0.1.0`

## Frozen Release Candidate

- source branch: `develop`
- target branch: `main`
- source Head: `595a45f33a0b7cb1453695dc6f7bdb6ed3d8eccc`
- source tree: `1b3e3f59dbc142df96913f8f512fc839c88bc0ea`
- pre-release main Head: `8ed6cf5bbecd66f08e79cc64949d23378135f92d`

## Release Verification

GitHub Actions run:

`33652934391`

Results:

- release-contract: PASS
- Backend Verification: PASS — 482 passed
- database recovery: PASS
- PostgreSQL + pgvector: PASS
- Alembic upgrade / downgrade / re-upgrade: PASS
- Dispatcher Tests: PASS — 87 passed
- project version: `0.1.0`
- FastAPI version: `0.1.0`
- proposed tag identity: `v0.1.0`
- existing version tag: none

## Merge

Release PR #95 was merged using **merge commit**.

Merge SHA:

`5428d31108fd908ab3b8d2d657a1db4915fccdd7`

Parents:

- previous main: `8ed6cf5bbecd66f08e79cc64949d23378135f92d`
- released develop: `595a45f33a0b7cb1453695dc6f7bdb6ed3d8eccc`

## Post-Release Proof

Main merge tree:

`1b3e3f59dbc142df96913f8f512fc839c88bc0ea`

Frozen develop tree:

`1b3e3f59dbc142df96913f8f512fc839c88bc0ea`

Tree equality: **PASS**.

After merge:

```text
main ahead of released develop by 1 commit
file diff = empty
```

The only main-only state is the content-neutral release merge history.

## Explicitly Not Performed

- Git tag creation
- GitHub Release publication
- production deployment
- production database migration
- package/container publication
- cloud credential use
- Branch Protection mutation

## External Platform-Control Debt

GitHub still reports:

- main Branch Protection: disabled
- develop Branch Protection: disabled
- repository Rulesets: none

Repository CI does not replace those platform controls.

## Checkpoints

- [x] CP0 — Release candidate inventory
- [x] CP1 — Release plan
- [x] CP2 — Open exact develop→main Release PR
- [x] CP3 — Release Verification
- [x] CP4 — Release evidence / content-neutrality review
- [x] CP5 — Merge to main
- [x] CP6 — Post-release reconciliation

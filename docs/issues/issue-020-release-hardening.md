# Engineering Issue #020 — CI / Release Hardening Foundation

<!-- codex-dispatch-supervisor-approved-through: CP5 -->
<!-- codex-dispatch-write-allow: ["scripts/verify_release_candidate.py","tests/test_release_preflight.py","tests/test_release_workflows.py","docs/release-process.md","docs/issues/issue-020-release-hardening.md"] -->

## GitHub Tracking

- GitHub Issue: #89
- Engineering Issue ID: #020
- Branch: `feature/issue-020-release-hardening`
- Duplicate GitHub Issue #90: closed / not planned

## Goal

Create a reproducible `develop → main` release-promotion gate without adding production deployment.

## CP0 — Release / Branch-State Inventory

Status: **completed by Supervisor**

Verified repository state:

- default branch: `main`
- integration branch: `develop`
- main protection: disabled
- develop protection: disabled
- repository rulesets: none
- GitHub Releases: none
- project version: `0.1.0`
- FastAPI version: `0.1.0`
- existing workflows:
  - Backend Verification
  - Dispatcher Tests
- current CI verifies Product Feature PRs / develop pushes
- no dedicated release-promotion workflow exists
- main/develop were diverged before #020:
  - develop ahead 36
  - develop behind 2
  - main-only content difference: stale historical README only
  - no main-only Product / migration / workflow / security code

### One-Time Ancestry Reconciliation

Completed on the #020 Feature Branch:

`abe393dbe6a3b8b4f07301708f35fcaedab7add4`

Properties:

- first parent: `beb591260211fd713a514d8152548e23a8cb00bc` (develop)
- second parent: `8ed6cf5bbecd66f08e79cc64949d23378135f92d` (main)
- tree: `7dd0cdfbad53cdebeab9b961b4fa80327dde22ec`
- tree is exactly the pre-reconciliation develop tree
- stale main README content was not reintroduced
- no force push / history rewrite

The #020 PR must be merged into develop using **merge commit**, not squash/rebase, so this ancestry survives.

## CP1 — Release Promotion Architecture

Status: **completed and approved by Supervisor**

### Release Contract

A valid V1 release PR is:

```text
same repository
develop
   ↓
main
```

No Feature Branch / fork / arbitrary release branch may satisfy the release workflow.

### Main-Only Content Neutrality

The verifier must support normal GitHub release merge commits on main without requiring main to remain a direct ancestor forever.

Algorithm:

```text
merge_base = merge-base(origin/main, origin/develop)

diff(merge_base → origin/main)
must contain no file-content change
```

This permits:

```text
main-only release merge commit
with the same released tree
```

but rejects:

```text
direct main README/config/hotfix content drift
```

A real main hotfix must be reconciled/backported to develop before another release.

### Release Candidate Verifier

Create:

`scripts/verify_release_candidate.py`

Checks:

1. base ref exactly `main`
2. head ref exactly `develop`
3. base/head repository identity equal
4. expected PR Head SHA is full lowercase Git SHA
5. checked-out `HEAD` equals expected PR Head SHA
6. `origin/develop` equals expected PR Head SHA
7. `origin/main` and `origin/develop` resolve
8. main-only content from merge-base is empty
9. `pyproject.toml [project].version` is strict `MAJOR.MINOR.PATCH`
10. static FastAPI `version=` literal matches project version
11. local tag `v<version>` does not already exist

Implementation rules:

- Python 3.11 stdlib only
- use `tomllib`
- parse `app/main.py` statically with `ast`; do not import FastAPI app
- fixed subprocess argv lists
- `shell=False`
- no network calls
- bounded errors without dumping secrets

### Existing Workflows Become Reusable

Supervisor-controlled edits:

- `.github/workflows/backend-tests.yml`
- `.github/workflows/dispatcher-tests.yml`

Add `workflow_call`.

Direct `pull_request` trigger becomes:

`branches: [develop]`

Existing push-to-develop behavior remains.

Concurrency keys use workflow-specific fixed prefixes:

- `backend-verification-...`
- `dispatcher-tests-...`

This prevents reusable calls from the Release Verification wrapper cancelling one another.

### Release Verification Workflow

Create:

`.github/workflows/release-verification.yml`

Trigger:

- every PR targeting `main`
- no path filter

Permissions:

- contents: read

Jobs:

1. `release-contract`
2. `backend-verification` reusable call
3. `dispatcher-verification` reusable call

Release contract job:

- checkout exact PR head SHA
- `fetch-depth: 0`
- ensure `origin/main`, `origin/develop`, and tags are fetched
- run the release verifier with GitHub PR context

Backend/Dispatcher jobs run only after release-contract succeeds.

The wrapper does not duplicate backend/dispatcher test implementation.

### Release Merge Semantics

After release checks pass:

- merge `develop → main` using merge commit
- do not squash/rebase the release PR
- main-only release merge history is acceptable only while content-neutral

### Version / Tag Boundary

V1 version source:

`pyproject.toml [project].version`

FastAPI version must match.

Recommended tag:

`v<version>`

The current connector does not create Git tags or GitHub Releases, so #020 must not claim those platform objects exist.

### Branch Protection Gap

GitHub currently reports no protection/ruleset for main/develop.

Repo workflows cannot prevent an authorized direct push while branches are unprotected.

Document required settings truthfully, but do not claim enforcement.

### CP2 Control-Plane Rule

`.github/workflows/**` is hard-protected from Codex Safe Publish.

Therefore:

- Supervisor performs workflow edits directly
- Local Watcher should not be used as the workflow executor for #020
- no hard-protection override is granted
- scripts/tests/docs remain bounded and reviewable
- CP3 GitHub Actions is the actual validation of workflow syntax/behavior

### CP2 Write Scope

Supervisor-controlled:

- `.github/workflows/backend-tests.yml`
- `.github/workflows/dispatcher-tests.yml`
- `.github/workflows/release-verification.yml`

Ordinary repository scope:

- `scripts/verify_release_candidate.py`
- `tests/test_release_preflight.py`
- `tests/test_release_workflows.py`
- `docs/release-process.md`
- this note

No Product runtime code, migrations, DB schema, credentials, deployment files, or cloud resources.

## Out of Scope

- production deployment
- GitHub Release/tag publication
- package/container publishing
- semantic-release
- cloud secrets
- production migrations
- SLSA/signing
- branch-protection API mutation
- force push/rebase history rewriting

## Checkpoints

- [x] CP0 — Release / branch-state inventory
- [x] CP1 — Release promotion architecture
- [x] CP2 — Supervisor-controlled workflow + verifier implementation
- [x] CP3 — Verification / release-contract regression
- [x] CP4 — Release/security review
- [x] CP5 — Knowledge / documentation
- [ ] CP6 — exact-Head delivery

## Current State

Remote Supervisor approval: **CP1**.

CP2 is Supervisor-controlled because it changes hard-protected workflow files.

Do not launch the Local Watcher for #020 workflow changes.


## CP2 Supervisor-Controlled Implementation

Ancestry reconciliation:

- `abe393dbe6a3b8b4f07301708f35fcaedab7add4`
- exact develop tree preserved
- historical main added only as second-parent ancestry

Implemented by Supervisor because `.github/workflows/**` is hard-protected:

- Backend Verification supports `workflow_call`
- Dispatcher Tests supports `workflow_call`
- direct PR triggers are scoped to `develop`
- reusable workflow concurrency prefixes are distinct
- new `Release Verification` workflow targets every PR to `main`
- Release Verification has `contents: read` only
- release job checks out exact PR Head with `fetch-depth: 0`
- release wrapper calls reusable Backend + Dispatcher workflows
- `scripts/verify_release_candidate.py` implements network-free release contract verification
- project/FastAPI version consistency is checked statically
- main-only content drift fails closed
- existing version tag fails closed
- focused release verifier/workflow tests added
- release process and branch-protection gap documented

No Product runtime, DB schema, deployment, secret, package publishing, tag publishing, or production operation is added.

CP2 verification has not yet been claimed.

Remote approval remains CP1 until Supervisor Review / GitHub-hosted evidence.


## CP2 Supervisor Review

Status: **PASS**

Reviewed:

- ancestry reconciliation `abe393dbe6a3b8b4f07301708f35fcaedab7add4`
- control-plane implementation `c1032d7834f5961d070fea9aaf8caf50b1aee672`
- exact-source hardening `236996f229c1a2b5f75ba7ef61d9c948f9efadf1`

Confirmed:

- reconciliation commit preserves the exact pre-sync develop tree;
- historical main is recorded only as ancestry;
- stale README content was not reintroduced;
- Backend and Dispatcher expose `workflow_call`;
- direct PR triggers are limited to base `develop`;
- push-to-develop CI remains intact;
- reusable workflow concurrency prefixes are distinct;
- Backend and Dispatcher checkout exact PR Head SHA for PR events and exact `github.sha` for push events;
- Release Verification targets every PR to `main` with no path filter;
- Release Verification permissions are `contents: read`;
- release-contract checks out exact PR Head with full history;
- release verifier is network-free and uses fixed subprocess argv lists with no `shell=True`;
- verifier requires same-repo `develop → main`;
- checked-out HEAD and `origin/develop` must equal expected PR Head SHA;
- main-only content drift after merge-base fails closed;
- project version is static SemVer and must match FastAPI version;
- an existing `v<version>` tag fails closed;
- Release wrapper calls existing reusable Backend + Dispatcher workflows rather than duplicating them;
- no production deployment, credential write, package publish, tag publish, GitHub Release publish, or branch-protection mutation exists;
- branch protection remains an explicitly documented external platform-control gap.

A static Review found and fixed one blocking issue before CP2 approval:

> reusable Backend/Dispatcher workflows initially used default checkout behavior, which could verify a pull-request merge ref rather than the exact release source Head.

They now explicitly checkout:

`github.event.pull_request.head.sha || github.sha`

No blocking CP2 finding remains.

Remote Supervisor approval: **CP2**.

Next: CP3 GitHub-hosted verification.


## CP3 — GitHub-Hosted Verification

Status: **completed**

Verified Head:

`a38f30520b20b573d5330507b9c08cc3ecb1e116`

Results:

- Backend Verification #189 / run `33651540228`: **PASS**
- backend regression: **481 passed**
- database recovery: **PASS**
- Dispatcher Tests #149 / run `33651540179`: **PASS**
- control-plane regression: **87 passed**

The modified workflow files were accepted and executed by GitHub Actions.

No CP3 Product/control-plane correction was required after the exact-source checkout hardening already completed in CP2 Review.

## CP4 — Release / Security Review

Status: **PASS**

Confirmed:

- #020 Feature history now contains historical main ancestry; comparison to main is behind by 0.
- ancestry reconciliation preserved the exact pre-sync develop tree.
- no stale main-only README content was reintroduced.
- Release Verification is triggered for every PR to main and has no path filter.
- Release Verification permissions are read-only.
- release-contract verifies same-repository `develop → main`.
- exact PR Head SHA is checked out with full history.
- reusable Backend and Dispatcher workflows verify exact PR source Heads rather than implicit merge refs.
- push-to-develop verification continues to use exact push SHA.
- reusable workflow concurrency prefixes are distinct.
- main-only file-content drift fails closed.
- project SemVer and FastAPI static version must match.
- a previously used `v<version>` tag fails closed.
- executable workflow/verifier sources contain no production deployment, `contents: write`, OIDC write, package write, secret access, force push, GitHub Release publication, container push, Kubernetes, or Terraform path.
- GitHub still reports main/develop branch protection disabled and no repository ruleset; repository CI must not be described as platform-enforced direct-push prevention.
- #020 Release Verification is repository promotion evidence, not production deployment evidence.

No merge-blocking CP4 finding remains.

## CP5 — Knowledge / Documentation

Status: **completed**

Notion deduplication performed before creation.

Created reusable Engineering Encyclopedia entry:

**Release Promotion：develop→main Gate、Exact Head、Reusable Workflow 與 Branch Topology**

Created Work Log:

**Issue #020 — CI / Release Hardening Foundation**

Repository documentation synchronized before Final CI:

- `docs/release-process.md`
- `README.md`
- `docs/PROJECT_STATE.md`
- this execution note

## CP6 — Final Delivery

Status: **final exact-Head verification pending**

All planned branch-changing control-plane, tests, and documentation work is complete.

Final merge constraint remains:

> PR #91 must be merged into develop using **merge commit**, not squash/rebase, so ancestry reconciliation survives.

Next:

```text
FINAL HEAD
→ exact-Head Backend + Dispatcher CI
→ PASS
→ evidence in PR/Issue comments only
→ replacement non-Draft PR on same Head if needed
→ merge method = merge
```

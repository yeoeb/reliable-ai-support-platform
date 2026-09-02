# Release Process

## Purpose

This repository separates normal engineering integration from stable release promotion.

```text
Feature / Docs work
    ↓
Pull Request → develop
    ↓
normal Backend / Dispatcher verification

develop
    ↓
Release Pull Request
    ↓
main
```

A release is repository promotion evidence. It is not production deployment.

## V1 Release Contract

A valid Release Pull Request is exactly:

- base branch: `main`
- head branch: `develop`
- head repository: the same repository as main

The Release Verification workflow runs on every PR targeting main, with no path filter.

Feature branches and forks must not directly satisfy the release gate.

## Exact Candidate Identity

Release Verification checks out:

`github.event.pull_request.head.sha`

with full history.

The verifier requires:

- checked-out HEAD equals the expected PR Head SHA
- `origin/develop` equals that same SHA
- `origin/main` is available
- version metadata is internally consistent

This avoids verifying a moving branch name or an implicit merge-ref and then claiming that evidence belongs to a different source commit.

## Main-Only Content Neutrality

GitHub release merge commits can exist only on main.

Therefore the verifier allows main-only **history** while rejecting main-only **content**.

It computes the merge-base between main and develop and requires the file-content diff from that merge-base to main to be empty.

Allowed:

```text
main release merge commit
→ tree contains no main-only content
```

Rejected:

```text
direct hotfix / README / config edit on main
→ file content exists only on main
```

A real main hotfix must be explicitly reconciled into develop before the next release.

## Historical Reconciliation Before the First Hardened Release

Before #020, main and develop had diverged.

Main-only content was an obsolete README update, while current develop already contained the authoritative project documentation and Product code.

The #020 Feature Branch records a one-time ancestry reconciliation commit:

`abe393dbe6a3b8b4f07301708f35fcaedab7add4`

It has:

- develop as first parent
- historical main as second parent
- exactly the pre-reconciliation develop tree

No stale main content was reintroduced.

Because this is a history-preserving merge commit, the #020 PR itself must be merged into develop using **merge commit**, not squash/rebase.

## Release Verification

A Release PR to main runs:

1. release-contract verification
2. full reusable Backend Verification
3. full reusable Dispatcher Tests

The release wrapper does not duplicate those test implementations.

Existing Backend/Dispatcher workflows remain responsible for Feature/integration CI against develop.

## Version

V1 version Source of Truth:

`pyproject.toml [project].version`

The FastAPI `version=` static literal in `app/main.py` must match.

The verifier accepts strict:

`MAJOR.MINOR.PATCH`

and rejects a candidate if local tag:

`v<version>`

already exists.

The current connected GitHub tools do not publish Git tags or GitHub Releases, so repository verification must not be described as tag/release publication.

## Merge Method

For a normal Release PR:

`develop → main`

use **merge commit**.

Do not squash/rebase the Release PR.

The main-side merge commit is release-history evidence and is permitted by the next release verifier only while it introduces no main-only file content.

## Branch Protection Gap

At the time #020 was designed, GitHub reported:

- main: unprotected
- develop: unprotected
- repository rulesets: none

This is an external platform-control gap.

Repository workflows can detect invalid release PRs, but an authorized direct push can bypass PR checks while branch protection remains disabled.

Recommended GitHub repository settings:

### main

- require Pull Request before merge
- require Release Verification
- disallow force pushes
- disallow deletion

### develop

- require Pull Request for Product/control-plane work
- require appropriate Backend / Dispatcher checks
- disallow force pushes

Do not claim these controls are active until GitHub repository state confirms them.

## Release Is Not Deployment

A successful release gate means:

> the exact repository release candidate passed the configured verification.

It does not mean:

- production credentials exist
- cloud resources were changed
- production database migrations ran
- traffic was shifted
- rollback was executed
- a package/container was published
- a Git tag or GitHub Release was created

Those are separate delivery/deployment boundaries.

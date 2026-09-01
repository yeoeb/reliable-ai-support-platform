# Issue Execution Notes

This directory stores compact per-Issue execution state when an Issue needs resumable checkpoints.

These files are not a second Source of Truth for Requirements.
The GitHub Issue remains the task contract.

## Naming

```text
issue-009-audit-logging.md
issue-010-structured-logging.md
```

Use Engineering Issue IDs, not GitHub Issue/PR sequence numbers.

## Recommended Structure

```md
# Engineering Issue #NNN — Title

<!-- codex-dispatch-supervisor-approved-through: CP0 -->

## GitHub Tracking
Repository Issue URL / number

## Goal

## Why Now

## Dependencies

## Required Reading

## Scope

## Allowed Write Set

## Out of Scope

## Acceptance Criteria

## Known Risks

## Checkpoints
### CP0 Context
### CP1 Plan
### CP2 Implementation
### CP3 Verification
### CP4 Review
### CP5 Knowledge Capture
### CP6 Delivery

## Commands / Evidence

## Decisions

## Knowledge Candidates

## Current State
```

## Rules

- Keep the note small enough to reload cheaply.
- Do not paste full Chat transcripts.
- Do not duplicate stable architecture documentation.
- Keep exactly one `codex-dispatch-supervisor-approved-through` marker.
- Only the Supervisor updates the approval marker after reviewing a Checkpoint.
- The Dispatcher reads approval from `origin/<feature-branch>`, not the mutable local Working Tree.
- Update Current State at every meaningful Checkpoint.
- At completion, preserve only decisions/evidence useful for future maintenance.

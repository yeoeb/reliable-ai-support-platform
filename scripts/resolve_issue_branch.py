from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Sequence


ISSUE_PATTERN = re.compile(r"^\d{1,3}$")


class BranchResolutionError(RuntimeError):
    """Raised when an Engineering Issue branch cannot be resolved safely."""


def normalize_issue_id(raw: str) -> str:
    value = raw.strip().lstrip("#")
    if not ISSUE_PATTERN.fullmatch(value):
        raise BranchResolutionError(
            "Engineering Issue ID must contain 1 to 3 digits."
        )
    return value.zfill(3)


def parse_remote_heads(
    output: str,
    *,
    issue_id: str,
) -> str:
    normalized = normalize_issue_id(issue_id)
    prefix = f"refs/heads/feature/issue-{normalized}-"
    matches: set[str] = set()

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) != 2:
            raise BranchResolutionError(
                "Remote branch discovery returned malformed output."
            )

        _, ref = parts
        if not ref.startswith("refs/heads/"):
            raise BranchResolutionError(
                "Remote branch discovery returned a non-head ref."
            )

        if not ref.startswith(prefix):
            continue

        branch = ref.removeprefix("refs/heads/")
        if not branch or branch.endswith("/"):
            raise BranchResolutionError(
                "Remote branch discovery returned an invalid branch."
            )

        matches.add(branch)

    if not matches:
        raise BranchResolutionError(
            f"No remote Feature Branch matches Engineering Issue #{normalized}."
        )

    if len(matches) != 1:
        names = ", ".join(sorted(matches))
        raise BranchResolutionError(
            "Engineering Issue branch is ambiguous; "
            f"expected exactly one remote match, found {len(matches)}: {names}"
        )

    return next(iter(matches))


def resolve_remote_issue_branch(
    issue_id: str,
    *,
    remote: str = "origin",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    normalized = normalize_issue_id(issue_id)
    pattern = f"refs/heads/feature/issue-{normalized}-*"

    result = runner(
        [
            "git",
            "ls-remote",
            "--heads",
            remote,
            pattern,
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        detail = (
            result.stderr
            or result.stdout
            or "git ls-remote failed."
        ).strip()
        raise BranchResolutionError(detail)

    return parse_remote_heads(
        result.stdout or "",
        issue_id=normalized,
    )


def parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve exactly one remote Feature Branch "
            "for an Engineering Issue."
        )
    )
    parser.add_argument(
        "--issue",
        required=True,
        help="Engineering Issue ID, e.g. 010.",
    )
    parser.add_argument(
        "--remote",
        default="origin",
        help="Git remote name. Defaults to origin.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        branch = resolve_remote_issue_branch(
            args.issue,
            remote=args.remote,
        )
    except BranchResolutionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(branch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

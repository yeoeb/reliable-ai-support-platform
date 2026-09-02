import subprocess

import pytest

from scripts.resolve_issue_branch import (
    BranchResolutionError,
    normalize_issue_id,
    parse_remote_heads,
    resolve_remote_issue_branch,
)


def test_normalize_issue_id() -> None:
    assert normalize_issue_id("9") == "009"
    assert normalize_issue_id("#10") == "010"
    assert normalize_issue_id("010") == "010"


@pytest.mark.parametrize(
    "value",
    ["", "abc", "1000", "10x", "-1"],
)
def test_invalid_issue_id_fails_closed(value: str) -> None:
    with pytest.raises(BranchResolutionError):
        normalize_issue_id(value)


def test_parse_remote_heads_returns_unique_match() -> None:
    output = (
        "a" * 40
        + "\trefs/heads/feature/issue-010-structured-logging\n"
    )

    assert parse_remote_heads(
        output,
        issue_id="010",
    ) == "feature/issue-010-structured-logging"


def test_parse_remote_heads_ignores_unrelated_heads() -> None:
    output = (
        "a" * 40
        + "\trefs/heads/feature/issue-009-audit-logging\n"
        + "b" * 40
        + "\trefs/heads/feature/issue-010-structured-logging\n"
    )

    assert parse_remote_heads(
        output,
        issue_id="010",
    ) == "feature/issue-010-structured-logging"


def test_parse_remote_heads_rejects_no_match() -> None:
    with pytest.raises(
        BranchResolutionError,
        match="No remote Feature Branch",
    ):
        parse_remote_heads(
            "",
            issue_id="010",
        )


def test_parse_remote_heads_rejects_ambiguous_match() -> None:
    output = (
        "a" * 40
        + "\trefs/heads/feature/issue-010-structured-logging\n"
        + "b" * 40
        + "\trefs/heads/feature/issue-010-other\n"
    )

    with pytest.raises(
        BranchResolutionError,
        match="ambiguous",
    ):
        parse_remote_heads(
            output,
            issue_id="010",
        )


@pytest.mark.parametrize(
    "output",
    [
        "malformed-line",
        "a" * 40 + "\trefs/tags/feature/issue-010-bad\n",
    ],
)
def test_parse_remote_heads_rejects_malformed_output(
    output: str,
) -> None:
    with pytest.raises(BranchResolutionError):
        parse_remote_heads(
            output,
            issue_id="010",
        )


def test_resolver_queries_exact_issue_prefix() -> None:
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                "a" * 40
                + "\trefs/heads/feature/"
                "issue-010-structured-logging\n"
            ),
            stderr="",
        )

    branch = resolve_remote_issue_branch(
        "10",
        runner=runner,
    )

    assert branch == "feature/issue-010-structured-logging"
    assert calls == [[
        "git",
        "ls-remote",
        "--heads",
        "origin",
        "refs/heads/feature/issue-010-*",
    ]]


def test_git_failure_is_reported() -> None:
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            2,
            stdout="",
            stderr="remote unavailable",
        )

    with pytest.raises(
        BranchResolutionError,
        match="remote unavailable",
    ):
        resolve_remote_issue_branch(
            "010",
            runner=runner,
        )

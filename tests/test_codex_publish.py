from pathlib import Path
import subprocess

import pytest

from scripts.codex_dispatch import (
    CHECKPOINT_SANDBOX,
    DispatchContext,
    DispatchError,
    ensure_clean_worktree,
    parse_write_allow,
    publish_write_checkpoint,
)


ISSUE_BRANCH = "feature/issue-009-audit-logging"
ISSUE_NOTE = "docs/issues/issue-009-audit-logging.md"


def run_git(
    repo: Path,
    *args: str,
) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def issue_note(
    *,
    approval: str = "CP1",
    patterns: list[str] | None = None,
) -> str:
    if patterns is None:
        patterns = [
            "app/*.py",
            "tests/*.py",
            ISSUE_NOTE,
        ]

    import json

    return (
        "# Issue #009\n\n"
        "<!-- "
        "codex-dispatch-supervisor-approved-through: "
        f"{approval} -->\n"
        "<!-- codex-dispatch-write-allow: "
        f"{json.dumps(patterns)} -->\n\n"
        "## Current State\n"
        "CP2 authorized.\n"
    )


def make_repo(
    tmp_path: Path,
) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        text=True,
        capture_output=True,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.name", "Test User")
    run_git(
        repo,
        "config",
        "user.email",
        "test@example.com",
    )
    run_git(repo, "switch", "-c", ISSUE_BRANCH)

    (repo / "docs" / "issues").mkdir(
        parents=True,
    )
    (repo / "app").mkdir()
    (repo / "tests").mkdir()

    (repo / "AGENTS.md").write_text(
        "# rules\n",
        encoding="utf-8",
    )
    (
        repo
        / "docs"
        / "PROJECT_STATE.md"
    ).write_text(
        "# state\n",
        encoding="utf-8",
    )
    (
        repo
        / ISSUE_NOTE
    ).write_text(
        issue_note(),
        encoding="utf-8",
    )
    (repo / "app" / "existing.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    run_git(repo, "add", ".")
    run_git(
        repo,
        "commit",
        "-m",
        "test: bootstrap issue branch",
    )
    run_git(
        repo,
        "remote",
        "add",
        "origin",
        str(remote),
    )
    run_git(
        repo,
        "push",
        "-u",
        "origin",
        ISSUE_BRANCH,
    )

    return repo, remote


def make_context(
    repo: Path,
) -> DispatchContext:
    return DispatchContext(
        repo_root=repo,
        issue_id="009",
        checkpoint="CP2",
        sandbox=CHECKPOINT_SANDBOX["CP2"],
        branch=ISSUE_BRANCH,
        issue_note=repo / ISSUE_NOTE,
    )


def remote_head(repo: Path) -> str:
    run_git(
        repo,
        "fetch",
        "--quiet",
        "origin",
        ISSUE_BRANCH,
    )
    return run_git(
        repo,
        "rev-parse",
        f"origin/{ISSUE_BRANCH}",
    )


def remote_note(repo: Path) -> str:
    return run_git(
        repo,
        "show",
        f"origin/{ISSUE_BRANCH}:{ISSUE_NOTE}",
    )


def test_write_checkpoint_requires_clean_worktree(
    tmp_path,
):
    repo, _ = make_repo(tmp_path)
    (repo / "app" / "existing.py").write_text(
        "VALUE = 2\n",
        encoding="utf-8",
    )

    with pytest.raises(
        DispatchError,
        match="clean Working Tree",
    ):
        ensure_clean_worktree(repo)


@pytest.mark.parametrize(
    "content",
    [
        "# no marker\n",
        (
            '<!-- codex-dispatch-write-allow: '
            '["app/*.py"] -->\n'
            '<!-- codex-dispatch-write-allow: '
            '["tests/*.py"] -->\n'
        ),
        (
            "<!-- codex-dispatch-write-allow: "
            "not-json -->\n"
        ),
        (
            "<!-- codex-dispatch-write-allow: "
            "[] -->\n"
        ),
        (
            "<!-- codex-dispatch-write-allow: "
            '["../secret"] -->\n'
        ),
        (
            "<!-- codex-dispatch-write-allow: "
            '["app\\*.py"] -->\n'
        ),
        (
            "<!-- codex-dispatch-write-allow: "
            '["*"] -->\n'
        ),
    ],
)
def test_invalid_write_allow_fails_closed(
    content,
):
    with pytest.raises(DispatchError):
        parse_write_allow(content)


def test_successful_publish_commits_and_pushes_allowed_change(
    tmp_path,
):
    repo, remote = make_repo(tmp_path)
    context = make_context(repo)
    before = remote_head(repo)
    note = remote_note(repo)
    patterns = parse_write_allow(note)

    (repo / "app" / "audit_event.py").write_text(
        "AUDIT = True\n",
        encoding="utf-8",
    )

    commit_sha = publish_write_checkpoint(
        context,
        expected_remote_head=before,
        remote_note=note,
        patterns=patterns,
    )

    assert commit_sha
    assert run_git(
        repo,
        "rev-parse",
        "HEAD",
    ) == commit_sha

    remote_sha = subprocess.run(
        [
            "git",
            "--git-dir",
            str(remote),
            "rev-parse",
            f"refs/heads/{ISSUE_BRANCH}",
        ],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()

    assert remote_sha == commit_sha
    assert run_git(
        repo,
        "log",
        "-1",
        "--pretty=%s",
    ) == "checkpoint(issue-009): CP2"


def test_disallowed_file_blocks_publication(
    tmp_path,
):
    repo, _ = make_repo(tmp_path)
    context = make_context(repo)
    before = remote_head(repo)
    note = remote_note(repo)

    (repo / "README.md").write_text(
        "unexpected\n",
        encoding="utf-8",
    )

    with pytest.raises(
        DispatchError,
        match="outside the Supervisor-controlled",
    ):
        publish_write_checkpoint(
            context,
            expected_remote_head=before,
            remote_note=note,
            patterns=parse_write_allow(note),
        )

    assert remote_head(repo) == before


def test_protected_control_plane_path_is_blocked_even_by_broad_pattern(
    tmp_path,
):
    repo, _ = make_repo(tmp_path)
    context = make_context(repo)
    before = remote_head(repo)
    note = issue_note(patterns=["AGENTS.md"])
    (
        repo
        / ISSUE_NOTE
    ).write_text(
        note,
        encoding="utf-8",
    )
    run_git(repo, "add", ISSUE_NOTE)
    run_git(
        repo,
        "commit",
        "-m",
        "test: broaden remote marker",
    )
    run_git(
        repo,
        "push",
        "origin",
        ISSUE_BRANCH,
    )

    before = remote_head(repo)
    note = remote_note(repo)

    (repo / "AGENTS.md").write_text(
        "# compromised\n",
        encoding="utf-8",
    )

    with pytest.raises(
        DispatchError,
        match="outside the Supervisor-controlled",
    ):
        publish_write_checkpoint(
            context,
            expected_remote_head=before,
            remote_note=note,
            patterns=parse_write_allow(note),
        )


def test_executor_cannot_modify_supervisor_approval_marker(
    tmp_path,
):
    repo, _ = make_repo(tmp_path)
    context = make_context(repo)
    before = remote_head(repo)
    note = remote_note(repo)

    local = (
        repo
        / ISSUE_NOTE
    ).read_text(encoding="utf-8")
    local = local.replace(
        "approved-through: CP1",
        "approved-through: CP2",
    )
    (
        repo
        / ISSUE_NOTE
    ).write_text(
        local,
        encoding="utf-8",
    )

    with pytest.raises(
        DispatchError,
        match="Supervisor approval marker",
    ):
        publish_write_checkpoint(
            context,
            expected_remote_head=before,
            remote_note=note,
            patterns=parse_write_allow(note),
        )


def test_executor_cannot_modify_write_allow_marker(
    tmp_path,
):
    repo, _ = make_repo(tmp_path)
    context = make_context(repo)
    before = remote_head(repo)
    note = remote_note(repo)

    local = (
        repo
        / ISSUE_NOTE
    ).read_text(encoding="utf-8")
    local = local.replace(
        '"app/*.py"',
        '"app/audit_*.py"',
    )
    (
        repo
        / ISSUE_NOTE
    ).write_text(
        local,
        encoding="utf-8",
    )

    with pytest.raises(
        DispatchError,
        match="write-allow marker",
    ):
        publish_write_checkpoint(
            context,
            expected_remote_head=before,
            remote_note=note,
            patterns=parse_write_allow(note),
        )


def test_remote_head_race_blocks_publication(
    tmp_path,
):
    repo, remote = make_repo(tmp_path)
    context = make_context(repo)
    before = remote_head(repo)
    note = remote_note(repo)

    (repo / "app" / "audit_event.py").write_text(
        "AUDIT = True\n",
        encoding="utf-8",
    )

    other = tmp_path / "other"
    subprocess.run(
        [
            "git",
            "clone",
            "--branch",
            ISSUE_BRANCH,
            str(remote),
            str(other),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    run_git(
        other,
        "config",
        "user.name",
        "Other User",
    )
    run_git(
        other,
        "config",
        "user.email",
        "other@example.com",
    )
    (other / "tests").mkdir(
        exist_ok=True,
    )
    (other / "tests" / "remote_change.py").write_text(
        "REMOTE = True\n",
        encoding="utf-8",
    )
    run_git(other, "add", ".")
    run_git(
        other,
        "commit",
        "-m",
        "test: remote race",
    )
    run_git(
        other,
        "push",
        "origin",
        ISSUE_BRANCH,
    )

    with pytest.raises(
        DispatchError,
        match="Remote Feature Branch changed",
    ):
        publish_write_checkpoint(
            context,
            expected_remote_head=before,
            remote_note=note,
            patterns=parse_write_allow(note),
        )


def test_executor_local_commit_blocks_publication(
    tmp_path,
):
    repo, _ = make_repo(tmp_path)
    context = make_context(repo)
    before = remote_head(repo)
    note = remote_note(repo)

    (repo / "app" / "audit_event.py").write_text(
        "AUDIT = True\n",
        encoding="utf-8",
    )
    run_git(repo, "add", ".")
    run_git(
        repo,
        "commit",
        "-m",
        "executor should not commit",
    )

    with pytest.raises(
        DispatchError,
        match="Local HEAD changed",
    ):
        publish_write_checkpoint(
            context,
            expected_remote_head=before,
            remote_note=note,
            patterns=parse_write_allow(note),
        )


def test_no_changes_returns_none_without_push(
    tmp_path,
):
    repo, _ = make_repo(tmp_path)
    context = make_context(repo)
    before = remote_head(repo)
    note = remote_note(repo)

    result = publish_write_checkpoint(
        context,
        expected_remote_head=before,
        remote_note=note,
        patterns=parse_write_allow(note),
    )

    assert result is None
    assert remote_head(repo) == before

from pathlib import Path
import json
import subprocess

import pytest

import scripts.codex_dispatch as dispatcher
from scripts.codex_dispatch import (
    DispatchContext,
    DispatchError,
    build_codex_command,
    dispatch,
    extract_session_id,
    load_state,
    normalize_checkpoint,
    normalize_issue_id,
    parse_supervisor_approval,
    parse_supervisor_rework,
    resolve_context,
)


ISSUE_BRANCH = "feature/issue-009-audit-logging"


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "issues").mkdir(parents=True)
    (repo / "AGENTS.md").write_text(
        "# rules\n",
        encoding="utf-8",
    )
    (repo / "docs" / "PROJECT_STATE.md").write_text(
        "# state\n",
        encoding="utf-8",
    )
    (
        repo
        / "docs"
        / "issues"
        / "issue-009-audit-logging.md"
    ).write_text(
        "# issue\n",
        encoding="utf-8",
    )
    return repo


def remote_note(
    approval: str = "CP0",
) -> str:
    return (
        "# issue\n\n"
        "<!-- "
        "codex-dispatch-supervisor-approved-through: "
        f"{approval} -->\n"
        "<!-- codex-dispatch-write-allow: "
        "[\"app/**/*.py\", \"tests/*.py\", "
        "\"docs/issues/issue-009-audit-logging.md\"] -->\n"
    )


def git_runner_for(
    repo: Path,
    branch: str,
    *,
    approval: str = "CP0",
    note: str | None = None,
):
    resolved_note = (
        remote_note(approval)
        if note is None
        else note
    )

    def runner(command, **kwargs):
        if command[-2:] == [
            "rev-parse",
            "--show-toplevel",
        ]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=str(repo),
                stderr="",
            )

        if command[-3:] == [
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
        ]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=branch + "\n",
                stderr="",
            )

        if command[1:4] == [
            "fetch",
            "--quiet",
            "origin",
        ]:
            assert command[4] == branch
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="",
            )


        if command[1:] == [
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="",
            )

        if command[1:] == [
            "rev-parse",
            f"origin/{branch}",
        ]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="head-123\n",
                stderr="",
            )

        if command[1:] == [
            "rev-parse",
            "HEAD",
        ]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="head-123\n",
                stderr="",
            )

        if (
            len(command) >= 3
            and command[1] == "show"
        ):
            expected_prefix = (
                f"origin/{branch}:"
                "docs/issues/"
                "issue-009-audit-logging.md"
            )
            assert command[2] == expected_prefix
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=resolved_note,
                stderr="",
            )

        raise AssertionError(command)

    return runner


def make_context(
    repo: Path,
    *,
    checkpoint: str = "CP1",
    branch: str = ISSUE_BRANCH,
) -> DispatchContext:
    return DispatchContext(
        repo_root=repo,
        issue_id="009",
        checkpoint=checkpoint,
        sandbox=(
            dispatcher.CHECKPOINT_SANDBOX[
                checkpoint
            ]
        ),
        branch=branch,
        issue_note=(
            repo
            / "docs"
            / "issues"
            / "issue-009-audit-logging.md"
        ),
    )


def test_normalizes_issue_and_checkpoint():
    assert normalize_issue_id("9") == "009"
    assert normalize_issue_id("#009") == "009"
    assert normalize_checkpoint("cp1") == "CP1"


def test_git_capture_uses_explicit_utf8(
    tmp_path,
):
    observed = {}

    def runner(command, **kwargs):
        observed.update(kwargs)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Audit \\u2192 UTF-8",
            stderr="",
        )

    result = dispatcher.run_git(
        ["show", "HEAD:note.md"],
        cwd=tmp_path,
        runner=runner,
    )

    assert result == "Audit \\u2192 UTF-8"
    assert observed["encoding"] == "utf-8"
    assert observed["errors"] == "replace"


def test_git_empty_or_missing_stdout_is_safe(
    tmp_path,
):
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=None,
            stderr=None,
        )

    assert (
        dispatcher.run_git(
            ["fetch"],
            cwd=tmp_path,
            runner=runner,
        )
        == ""
    )


def test_codex_capture_uses_explicit_utf8():
    observed = {}

    def runner(command, **kwargs):
        observed.update(kwargs)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"turn.completed"}\\n',
            stderr="",
        )

    result = dispatcher.run_codex(
        ["codex", "exec", "--json", "-"],
        "test prompt",
        timeout_seconds=10,
        runner=runner,
    )

    assert result.returncode == 0
    assert observed["encoding"] == "utf-8"
    assert observed["errors"] == "replace"


def test_cp1_is_read_only_and_requires_issue_branch(
    tmp_path,
):
    repo = make_repo(tmp_path)

    context = resolve_context(
        start=repo,
        issue_id="009",
        checkpoint="CP1",
        git_runner=git_runner_for(
            repo,
            ISSUE_BRANCH,
        ),
    )

    assert context.sandbox == "read-only"

    with pytest.raises(
        DispatchError,
        match="dedicated branch",
    ):
        resolve_context(
            start=repo,
            issue_id="009",
            checkpoint="CP1",
            git_runner=git_runner_for(
                repo,
                "develop",
            ),
        )


def test_cp2_is_workspace_write_and_rejects_other_issue_branch(
    tmp_path,
):
    repo = make_repo(tmp_path)

    context = resolve_context(
        start=repo,
        issue_id="009",
        checkpoint="CP2",
        git_runner=git_runner_for(
            repo,
            ISSUE_BRANCH,
        ),
    )

    assert context.sandbox == "workspace-write"

    with pytest.raises(
        DispatchError,
        match="issue-009",
    ):
        resolve_context(
            start=repo,
            issue_id="009",
            checkpoint="CP2",
            git_runner=git_runner_for(
                repo,
                "feature/issue-008-rbac",
            ),
        )


def test_missing_issue_note_fails(tmp_path):
    repo = make_repo(tmp_path)
    (
        repo
        / "docs"
        / "issues"
        / "issue-009-audit-logging.md"
    ).unlink()

    with pytest.raises(
        DispatchError,
        match="No execution note",
    ):
        resolve_context(
            start=repo,
            issue_id="009",
            checkpoint="CP1",
            git_runner=git_runner_for(
                repo,
                ISSUE_BRANCH,
            ),
        )


def test_new_command_uses_json_and_sandbox(
    tmp_path,
):
    repo = make_repo(tmp_path)

    command = build_codex_command(
        make_context(repo),
        codex_bin="codex",
        session_id=None,
    )

    assert command[:3] == [
        "codex",
        "exec",
        "--json",
    ]
    assert command[5:7] == [
        "--sandbox",
        "read-only",
    ]
    assert command[-1] == "-"


def test_resume_command_places_flags_before_resume(
    tmp_path,
):
    repo = make_repo(tmp_path)

    command = build_codex_command(
        make_context(
            repo,
            checkpoint="CP2",
        ),
        codex_bin="codex",
        session_id="thread-123",
    )

    resume_index = command.index("resume")
    sandbox_index = command.index("--sandbox")

    assert sandbox_index < resume_index
    assert command[resume_index:] == [
        "resume",
        "thread-123",
        "-",
    ]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            '{"type":"thread.started",'
            '"thread_id":"abc"}',
            "abc",
        ),
        (
            '{"type":"thread.started",'
            '"thread":{"id":"xyz"}}',
            "xyz",
        ),
        (
            '{"type":"turn.completed"}',
            None,
        ),
    ],
)
def test_extract_session_id(
    line,
    expected,
):
    assert (
        extract_session_id(line)
        == expected
    )


def test_parse_supervisor_approval():
    assert (
        parse_supervisor_approval(
            remote_note("CP3")
        )
        == "CP3"
    )


def test_supervisor_approval_ignores_prose_mentions():
    content = (
        remote_note("CP2")
        + "\nThe `codex-dispatch-supervisor-approved-through` "
        + "marker is controlled by the Supervisor.\n"
    )

    assert (
        parse_supervisor_approval(content)
        == "CP2"
    )


@pytest.mark.parametrize(
    "note",
    [
        "# no marker\n",
        (
            "<!-- codex-dispatch-supervisor-approved-through: "
            "CP0 -->\n"
            "<!-- codex-dispatch-supervisor-approved-through: "
            "CP1 -->\n"
        ),
        (
            "codex-dispatch-supervisor-approved-through: "
            "CP1\n"
        ),
        (
            "<!-- codex-dispatch-supervisor-approved-through: "
            "CP9 -->\n"
        ),
    ],
)
def test_invalid_supervisor_approval_fails_closed(
    note,
):
    with pytest.raises(DispatchError):
        parse_supervisor_approval(note)


def test_cp1_requires_remote_cp0_approval(
    tmp_path,
    capsys,
):
    repo = make_repo(tmp_path)
    context = make_context(repo)

    result = dispatch(
        context,
        dry_run=True,
        force=False,
        new_session=False,
        codex_bin="codex",
        timeout_seconds=10,
        git_runner=git_runner_for(
            repo,
            ISSUE_BRANCH,
            approval="CP0",
        ),
    )

    assert result == 0
    payload = json.loads(
        capsys.readouterr().out
    )
    assert (
        payload["supervisor_approved_through"]
        == "CP0"
    )


def test_cp2_rejects_remote_approval_only_through_cp0(
    tmp_path,
):
    repo = make_repo(tmp_path)

    with pytest.raises(
        DispatchError,
        match="requires remote Supervisor approval through CP1",
    ):
        dispatch(
            make_context(
                repo,
                checkpoint="CP2",
            ),
            dry_run=True,
            force=False,
            new_session=False,
            codex_bin="codex",
            timeout_seconds=10,
            git_runner=git_runner_for(
                repo,
                ISSUE_BRANCH,
                approval="CP0",
            ),
        )


def test_cp2_can_start_from_remote_cp1_approval_without_local_cp1_state(
    tmp_path,
    capsys,
):
    repo = make_repo(tmp_path)

    result = dispatch(
        make_context(
            repo,
            checkpoint="CP2",
        ),
        dry_run=True,
        force=False,
        new_session=False,
        codex_bin="codex",
        timeout_seconds=10,
        git_runner=git_runner_for(
            repo,
            ISSUE_BRANCH,
            approval="CP1",
        ),
    )

    assert result == 0
    payload = json.loads(
        capsys.readouterr().out
    )
    assert payload["checkpoint"] == "CP2"
    assert (
        payload["supervisor_approved_through"]
        == "CP1"
    )
    assert payload["resume_session_id"] is None


def test_successful_dispatch_saves_only_minimal_metadata(
    tmp_path,
    monkeypatch,
):
    repo = make_repo(tmp_path)
    context = make_context(repo)

    monkeypatch.setattr(
        dispatcher.shutil,
        "which",
        lambda _: "codex",
    )

    def fake_process_runner(
        command,
        **kwargs,
    ):
        assert kwargs["input"].startswith(
            "Execute CP1 for "
            "Engineering Issue #009."
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"type":"thread.started",'
                '"thread_id":"thread-123"}\n'
                '{"type":"turn.completed"}\n'
            ),
            stderr="",
        )

    result = dispatch(
        context,
        dry_run=False,
        force=False,
        new_session=False,
        codex_bin="codex",
        timeout_seconds=10,
        process_runner=fake_process_runner,
        git_runner=git_runner_for(
            repo,
            ISSUE_BRANCH,
            approval="CP0",
        ),
    )

    assert result == 0

    issue_state = load_state(
        repo
    )["issues"]["009"]

    assert (
        issue_state["session_id"]
        == "thread-123"
    )
    assert (
        issue_state["last_checkpoint"]
        == "CP1"
    )
    assert "prompt" not in issue_state
    assert "transcript" not in issue_state
    assert "credential" not in issue_state


def test_resume_refuses_session_from_different_branch(
    tmp_path,
    monkeypatch,
):
    repo = make_repo(tmp_path)
    state_dir = repo / ".codex-dispatch"
    state_dir.mkdir()
    (
        state_dir
        / "state.json"
    ).write_text(
        json.dumps(
            {
                "issues": {
                    "009": {
                        "session_id": "thread-123",
                        "branch": "feature/old",
                        "last_checkpoint": "CP1",
                        "last_status": "succeeded",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        dispatcher.shutil,
        "which",
        lambda _: "codex",
    )

    with pytest.raises(
        DispatchError,
        match="different branch",
    ):
        dispatch(
            make_context(
                repo,
                checkpoint="CP2",
            ),
            dry_run=False,
            force=False,
            new_session=False,
            codex_bin="codex",
            timeout_seconds=10,
            git_runner=git_runner_for(
                repo,
                ISSUE_BRANCH,
                approval="CP1",
            ),
        )


def test_dry_run_does_not_launch_codex_or_write_state(
    tmp_path,
    capsys,
):
    repo = make_repo(tmp_path)
    context = resolve_context(
        start=repo,
        issue_id="009",
        checkpoint="CP1",
        git_runner=git_runner_for(
            repo,
            ISSUE_BRANCH,
        ),
    )

    def forbidden_runner(*args, **kwargs):
        raise AssertionError(
            "Dry run must not launch Codex."
        )

    result = dispatch(
        context,
        dry_run=True,
        force=False,
        new_session=False,
        codex_bin="codex",
        timeout_seconds=10,
        process_runner=forbidden_runner,
        git_runner=git_runner_for(
            repo,
            ISSUE_BRANCH,
            approval="CP0",
        ),
    )

    assert result == 0
    assert not (
        repo
        / ".codex-dispatch"
        / "state.json"
    ).exists()

    payload = json.loads(
        capsys.readouterr().out
    )
    assert payload["issue_id"] == "009"
    assert payload["checkpoint"] == "CP1"
    assert payload["sandbox"] == "read-only"


def test_nonzero_process_exit_cannot_be_reported_success():
    stdout = (
        '{"type":"thread.started",'
        '"thread_id":"thread-123"}\n'
        '{"type":"turn.completed"}\n'
    )

    assert (
        dispatcher.extract_terminal_status(
            stdout,
            1,
        )
        == "failed"
    )



def test_parse_supervisor_rework_absent_is_none():
    assert parse_supervisor_rework(
        remote_note("CP2")
    ) is None


def test_parse_supervisor_rework_valid():
    note = (
        remote_note("CP2")
        + '<!-- codex-dispatch-supervisor-rework: '
        '{"checkpoint":"CP3","attempt":1} -->\n'
    )

    assert parse_supervisor_rework(note) == (
        "CP3",
        1,
    )


@pytest.mark.parametrize(
    "marker",
    [
        '<!-- codex-dispatch-supervisor-rework: not-json -->',
        '<!-- codex-dispatch-supervisor-rework: '
        '{"checkpoint":"CP1","attempt":1} -->',
        '<!-- codex-dispatch-supervisor-rework: '
        '{"checkpoint":"CP3","attempt":0} -->',
        '<!-- codex-dispatch-supervisor-rework: '
        '{"checkpoint":"CP3","attempt":true} -->',
        '<!-- codex-dispatch-supervisor-rework: '
        '{"checkpoint":"CP3","attempt":1,"extra":1} -->',
    ],
)
def test_invalid_supervisor_rework_fails_closed(
    marker,
):
    with pytest.raises(DispatchError):
        parse_supervisor_rework(
            remote_note("CP2")
            + marker
            + "\n"
        )


def test_duplicate_supervisor_rework_markers_fail_closed():
    note = (
        remote_note("CP2")
        + '<!-- codex-dispatch-supervisor-rework: '
        '{"checkpoint":"CP3","attempt":1} -->\n'
        + '<!-- codex-dispatch-supervisor-rework: '
        '{"checkpoint":"CP3","attempt":2} -->\n'
    )

    with pytest.raises(
        DispatchError,
        match="at most one",
    ):
        parse_supervisor_rework(note)

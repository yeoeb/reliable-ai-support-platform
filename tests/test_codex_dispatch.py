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
    resolve_context,
)


def make_repo(
    tmp_path: Path,
    branch: str = "feature/issue-009-audit-logging",
) -> Path:
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


def git_runner_for(
    repo: Path,
    branch: str,
):
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

        raise AssertionError(command)

    return runner


def make_context(
    repo: Path,
    *,
    checkpoint: str = "CP1",
    branch: str = "develop",
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


def test_cp1_is_read_only(tmp_path):
    repo = make_repo(tmp_path)
    context = resolve_context(
        start=repo,
        issue_id="009",
        checkpoint="CP1",
        git_runner=git_runner_for(
            repo,
            "develop",
        ),
    )

    assert context.sandbox == "read-only"


def test_cp2_is_workspace_write_and_requires_work_branch(
    tmp_path,
):
    repo = make_repo(tmp_path)

    context = resolve_context(
        start=repo,
        issue_id="009",
        checkpoint="CP2",
        git_runner=git_runner_for(
            repo,
            "feature/issue-009-audit-logging",
        ),
    )

    assert context.sandbox == "workspace-write"

    for protected_branch in (
        "main",
        "develop",
    ):
        with pytest.raises(
            DispatchError,
            match="dedicated work branch",
        ):
            resolve_context(
                start=repo,
                issue_id="009",
                checkpoint="CP2",
                git_runner=git_runner_for(
                    repo,
                    protected_branch,
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
                "develop",
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
            branch=(
                "feature/"
                "issue-009-audit-logging"
            ),
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

    def fake_runner(
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
        process_runner=fake_runner,
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

    state_dir = (
        repo
        / ".codex-dispatch"
    )
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
                branch=(
                    "feature/"
                    "issue-009-audit-logging"
                ),
            ),
            dry_run=False,
            force=False,
            new_session=False,
            codex_bin="codex",
            timeout_seconds=10,
        )



def test_dry_run_does_not_launch_codex_or_write_state(
    tmp_path,
    capsys,
):
    repo = make_repo(tmp_path)
    context = make_context(repo)

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
    assert payload["command"][:3] == [
        "codex",
        "exec",
        "--json",
    ]

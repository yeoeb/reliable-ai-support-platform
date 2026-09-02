from contextlib import nullcontext
from pathlib import Path
import subprocess
import sys

import pytest

import scripts.codex_watch as watcher
from scripts.codex_dispatch import (
    CHECKPOINT_SANDBOX,
    DispatchContext,
    DispatchError,
)
from scripts.codex_watch import (
    next_write_checkpoint,
    watcher_lock,
)


ISSUE_BRANCH = "feature/issue-009-audit-logging"


def make_context(
    repo: Path,
    checkpoint: str,
) -> DispatchContext:
    note = (
        repo
        / "docs"
        / "issues"
        / "issue-009-audit-logging.md"
    )
    return DispatchContext(
        repo_root=repo,
        issue_id="009",
        checkpoint=checkpoint,
        sandbox=CHECKPOINT_SANDBOX[
            checkpoint
        ],
        branch=ISSUE_BRANCH,
        issue_note=note,
    )


@pytest.mark.parametrize(
    (
        "approved",
        "remote_done",
        "state",
        "expected",
    ),
    [
        ("CP0", False, {}, None),
        ("CP1", False, {}, "CP2"),
        ("CP2", False, {}, "CP3"),
        ("CP3", False, {}, None),
        (
            "CP1",
            True,
            {},
            None,
        ),
        (
            "CP1",
            False,
            {
                "last_checkpoint": "CP2",
                "last_status": "succeeded",
            },
            None,
        ),
    ],
)
def test_next_write_checkpoint(
    approved,
    remote_done,
    state,
    expected,
):
    assert (
        next_write_checkpoint(
            approved_through=approved,
            issue_state=state,
            remote_checkpoint_done=remote_done,
        )
        == expected
    )


def test_failed_checkpoint_is_not_retried():
    with pytest.raises(
        DispatchError,
        match="will not retry automatically",
    ):
        next_write_checkpoint(
            approved_through="CP1",
            issue_state={
                "last_checkpoint": "CP2",
                "last_status": "failed",
            },
            remote_checkpoint_done=False,
        )


def test_watcher_lock_blocks_duplicate_process(
    tmp_path,
):
    repo = tmp_path / "repo"
    repo.mkdir()

    with watcher_lock(repo, "009"):
        with pytest.raises(
            DispatchError,
            match="Another Watcher",
        ):
            with watcher_lock(
                repo,
                "009",
            ):
                pass

    assert not (
        repo
        / ".codex-dispatch"
        / "watch-009.lock"
    ).exists()


def test_preexisting_unlocked_lock_file_is_reusable(
    tmp_path,
):
    repo = tmp_path / "repo"
    lock_dir = repo / ".codex-dispatch"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / "watch-009.lock"
    lock_path.write_text(
        "stale-metadata\n",
        encoding="utf-8",
    )

    with watcher_lock(repo, "009"):
        assert lock_path.exists()
        assert (
            lock_path.read_text(
                encoding="utf-8"
            ).strip()
            == str(__import__("os").getpid())
        )

    assert not lock_path.exists()


def test_run_once_cp1_approval_dispatches_cp2(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    (repo / "docs" / "issues").mkdir(
        parents=True,
    )
    context = make_context(
        repo,
        "CP2",
    )
    called = []

    monkeypatch.setattr(
        watcher,
        "get_current_branch",
        lambda _: ISSUE_BRANCH,
    )
    monkeypatch.setattr(
        watcher,
        "fast_forward_issue_branch",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        watcher,
        "resolve_context",
        lambda **kwargs: (
            context
            if kwargs["checkpoint"] == "CP2"
            else make_context(
                repo,
                "CP1",
            )
        ),
    )
    monkeypatch.setattr(
        watcher,
        "fetch_remote_issue_note",
        lambda _: (
            "<!-- "
            "codex-dispatch-supervisor-approved-through: "
            "CP1 -->"
        ),
    )
    monkeypatch.setattr(
        watcher,
        "load_state",
        lambda _: {"issues": {}},
    )
    monkeypatch.setattr(
        watcher,
        "get_issue_state",
        lambda state, issue_id: {},
    )
    monkeypatch.setattr(
        watcher,
        "remote_checkpoint_exists",
        lambda **kwargs: False,
    )

    def fake_dispatch(
        dispatch_context,
        **kwargs,
    ):
        called.append(
            dispatch_context.checkpoint
        )
        return 0

    monkeypatch.setattr(
        watcher,
        "dispatch",
        fake_dispatch,
    )

    result = watcher.run_once(
        repo_root=repo,
        issue_id="009",
        codex_bin="codex",
        timeout_seconds=10,
    )

    assert result == 0
    assert called == ["CP2"]


def test_run_once_cp2_approval_dispatches_cp3(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    (repo / "docs" / "issues").mkdir(
        parents=True,
    )
    called = []

    monkeypatch.setattr(
        watcher,
        "get_current_branch",
        lambda _: ISSUE_BRANCH,
    )
    monkeypatch.setattr(
        watcher,
        "fast_forward_issue_branch",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        watcher,
        "resolve_context",
        lambda **kwargs: make_context(
            repo,
            kwargs["checkpoint"],
        ),
    )
    monkeypatch.setattr(
        watcher,
        "fetch_remote_issue_note",
        lambda _: (
            "<!-- "
            "codex-dispatch-supervisor-approved-through: "
            "CP2 -->"
        ),
    )
    monkeypatch.setattr(
        watcher,
        "load_state",
        lambda _: {
            "issues": {
                "009": {
                    "last_checkpoint": "CP2",
                    "last_status": "succeeded",
                }
            }
        },
    )
    monkeypatch.setattr(
        watcher,
        "get_issue_state",
        lambda state, issue_id: (
            state["issues"]["009"]
        ),
    )
    monkeypatch.setattr(
        watcher,
        "remote_checkpoint_exists",
        lambda **kwargs: False,
    )

    def fake_dispatch(
        dispatch_context,
        **kwargs,
    ):
        called.append(
            dispatch_context.checkpoint
        )
        return 0

    monkeypatch.setattr(
        watcher,
        "dispatch",
        fake_dispatch,
    )

    result = watcher.run_once(
        repo_root=repo,
        issue_id="009",
        codex_bin="codex",
        timeout_seconds=10,
    )

    assert result == 0
    assert called == ["CP3"]


def test_run_once_does_nothing_when_checkpoint_already_published(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    (repo / "docs" / "issues").mkdir(
        parents=True,
    )

    monkeypatch.setattr(
        watcher,
        "get_current_branch",
        lambda _: ISSUE_BRANCH,
    )
    monkeypatch.setattr(
        watcher,
        "fast_forward_issue_branch",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        watcher,
        "resolve_context",
        lambda **kwargs: make_context(
            repo,
            kwargs["checkpoint"],
        ),
    )
    monkeypatch.setattr(
        watcher,
        "fetch_remote_issue_note",
        lambda _: (
            "<!-- "
            "codex-dispatch-supervisor-approved-through: "
            "CP1 -->"
        ),
    )
    monkeypatch.setattr(
        watcher,
        "load_state",
        lambda _: {"issues": {}},
    )
    monkeypatch.setattr(
        watcher,
        "get_issue_state",
        lambda state, issue_id: {},
    )
    monkeypatch.setattr(
        watcher,
        "remote_checkpoint_exists",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        watcher,
        "dispatch",
        lambda *args, **kwargs: (
            pytest.fail(
                "Already-published checkpoint "
                "must not rerun."
            )
        ),
    )

    result = watcher.run_once(
        repo_root=repo,
        issue_id="009",
        codex_bin="codex",
        timeout_seconds=10,
    )

    assert result is None


def test_run_once_stops_on_failed_dispatch(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    (repo / "docs" / "issues").mkdir(
        parents=True,
    )

    monkeypatch.setattr(
        watcher,
        "get_current_branch",
        lambda _: ISSUE_BRANCH,
    )
    monkeypatch.setattr(
        watcher,
        "fast_forward_issue_branch",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        watcher,
        "resolve_context",
        lambda **kwargs: make_context(
            repo,
            kwargs["checkpoint"],
        ),
    )
    monkeypatch.setattr(
        watcher,
        "fetch_remote_issue_note",
        lambda _: (
            "<!-- "
            "codex-dispatch-supervisor-approved-through: "
            "CP1 -->"
        ),
    )
    monkeypatch.setattr(
        watcher,
        "load_state",
        lambda _: {"issues": {}},
    )
    monkeypatch.setattr(
        watcher,
        "get_issue_state",
        lambda state, issue_id: {},
    )
    monkeypatch.setattr(
        watcher,
        "remote_checkpoint_exists",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        watcher,
        "dispatch",
        lambda *args, **kwargs: 1,
    )

    with pytest.raises(
        DispatchError,
        match="no automatic retry",
    ):
        watcher.run_once(
            repo_root=repo,
            issue_id="009",
            codex_bin="codex",
            timeout_seconds=10,
        )


def test_run_once_rejects_wrong_branch(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    repo.mkdir()

    monkeypatch.setattr(
        watcher,
        "get_current_branch",
        lambda _: "feature/issue-008-rbac",
    )

    with pytest.raises(
        DispatchError,
        match="matching Engineering Issue Branch",
    ):
        watcher.run_once(
            repo_root=repo,
            issue_id="009",
            codex_bin="codex",
            timeout_seconds=10,
        )


def test_fast_forward_refuses_dirty_worktree(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    repo.mkdir()
    commands = []

    def dirty(_):
        raise DispatchError(
            "dirty"
        )

    monkeypatch.setattr(
        watcher,
        "ensure_clean_worktree",
        dirty,
    )
    monkeypatch.setattr(
        watcher,
        "run_git",
        lambda *args, **kwargs: (
            commands.append(args)
        ),
    )

    with pytest.raises(
        DispatchError,
        match="dirty",
    ):
        watcher.fast_forward_issue_branch(
            repo_root=repo,
            branch=ISSUE_BRANCH,
        )

    assert commands == []


def test_once_mode_returns_without_codex_when_idle(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    repo.mkdir()

    monkeypatch.setattr(
        watcher,
        "find_repo_root",
        lambda _: repo,
    )
    monkeypatch.setattr(
        watcher,
        "watcher_lock",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setattr(
        watcher,
        "run_once",
        lambda **kwargs: None,
    )

    assert (
        watcher.main(
            [
                "--issue",
                "009",
                "--once",
            ]
        )
        == 0
    )



def test_watcher_script_help_runs_directly():
    repo_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [
            sys.executable,
            "scripts/codex_watch.py",
            "--help",
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--issue" in result.stdout
    assert "--once" in result.stdout



def test_run_once_supervisor_rework_dispatches_force_with_label(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    (repo / "docs" / "issues").mkdir(
        parents=True,
    )
    called = []

    monkeypatch.setattr(
        watcher,
        "get_current_branch",
        lambda _: ISSUE_BRANCH,
    )
    monkeypatch.setattr(
        watcher,
        "fast_forward_issue_branch",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        watcher,
        "resolve_context",
        lambda **kwargs: make_context(
            repo,
            kwargs["checkpoint"],
        ),
    )
    monkeypatch.setattr(
        watcher,
        "fetch_remote_issue_note",
        lambda _: (
            "<!-- "
            "codex-dispatch-supervisor-approved-through: "
            "CP2 -->\n"
            "<!-- codex-dispatch-supervisor-rework: "
            '{"checkpoint":"CP3","attempt":1} -->'
        ),
    )
    monkeypatch.setattr(
        watcher,
        "load_state",
        lambda _: {
            "issues": {
                "009": {
                    "last_checkpoint": "CP3",
                    "last_status": "succeeded",
                }
            }
        },
    )
    monkeypatch.setattr(
        watcher,
        "get_issue_state",
        lambda state, issue_id: (
            state["issues"]["009"]
        ),
    )

    def fake_remote_checkpoint_exists(
        **kwargs,
    ):
        return (
            kwargs.get("publication_label")
            is None
        )

    monkeypatch.setattr(
        watcher,
        "remote_checkpoint_exists",
        fake_remote_checkpoint_exists,
    )

    def fake_dispatch(
        context,
        **kwargs,
    ):
        called.append(
            (
                context.checkpoint,
                kwargs["force"],
                kwargs["publication_label"],
            )
        )
        return 0

    monkeypatch.setattr(
        watcher,
        "dispatch",
        fake_dispatch,
    )

    result = watcher.run_once(
        repo_root=repo,
        issue_id="009",
        codex_bin="codex",
        timeout_seconds=10,
    )

    assert result == 0
    assert called == [
        ("CP3", True, "rework-1")
    ]


def test_run_once_does_not_repeat_completed_rework(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    (repo / "docs" / "issues").mkdir(
        parents=True,
    )

    monkeypatch.setattr(
        watcher,
        "get_current_branch",
        lambda _: ISSUE_BRANCH,
    )
    monkeypatch.setattr(
        watcher,
        "fast_forward_issue_branch",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        watcher,
        "resolve_context",
        lambda **kwargs: make_context(
            repo,
            kwargs["checkpoint"],
        ),
    )
    monkeypatch.setattr(
        watcher,
        "fetch_remote_issue_note",
        lambda _: (
            "<!-- "
            "codex-dispatch-supervisor-approved-through: "
            "CP2 -->\n"
            "<!-- codex-dispatch-supervisor-rework: "
            '{"checkpoint":"CP3","attempt":1} -->'
        ),
    )
    monkeypatch.setattr(
        watcher,
        "load_state",
        lambda _: {"issues": {}},
    )
    monkeypatch.setattr(
        watcher,
        "get_issue_state",
        lambda state, issue_id: {},
    )
    monkeypatch.setattr(
        watcher,
        "remote_checkpoint_exists",
        lambda **kwargs: (
            kwargs.get("publication_label")
            == "rework-1"
        ),
    )
    monkeypatch.setattr(
        watcher,
        "dispatch",
        lambda *args, **kwargs: pytest.fail(
            "Completed rework must not rerun."
        ),
    )

    assert watcher.run_once(
        repo_root=repo,
        issue_id="009",
        codex_bin="codex",
        timeout_seconds=10,
    ) is None


def test_run_once_rejects_rework_for_wrong_checkpoint(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    (repo / "docs" / "issues").mkdir(
        parents=True,
    )

    monkeypatch.setattr(
        watcher,
        "get_current_branch",
        lambda _: ISSUE_BRANCH,
    )
    monkeypatch.setattr(
        watcher,
        "fast_forward_issue_branch",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        watcher,
        "resolve_context",
        lambda **kwargs: make_context(
            repo,
            kwargs["checkpoint"],
        ),
    )
    monkeypatch.setattr(
        watcher,
        "fetch_remote_issue_note",
        lambda _: (
            "<!-- "
            "codex-dispatch-supervisor-approved-through: "
            "CP2 -->\n"
            "<!-- codex-dispatch-supervisor-rework: "
            '{"checkpoint":"CP2","attempt":1} -->'
        ),
    )
    monkeypatch.setattr(
        watcher,
        "load_state",
        lambda _: {"issues": {}},
    )
    monkeypatch.setattr(
        watcher,
        "get_issue_state",
        lambda state, issue_id: {},
    )

    with pytest.raises(
        DispatchError,
        match="does not match",
    ):
        watcher.run_once(
            repo_root=repo,
            issue_id="009",
            codex_bin="codex",
            timeout_seconds=10,
        )


def test_failed_rework_attempt_is_not_retried(
    tmp_path,
    monkeypatch,
):
    repo = tmp_path / "repo"
    (repo / "docs" / "issues").mkdir(
        parents=True,
    )

    monkeypatch.setattr(
        watcher,
        "get_current_branch",
        lambda _: ISSUE_BRANCH,
    )
    monkeypatch.setattr(
        watcher,
        "fast_forward_issue_branch",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        watcher,
        "resolve_context",
        lambda **kwargs: make_context(
            repo,
            kwargs["checkpoint"],
        ),
    )
    monkeypatch.setattr(
        watcher,
        "fetch_remote_issue_note",
        lambda _: (
            "<!-- "
            "codex-dispatch-supervisor-approved-through: "
            "CP2 -->\n"
            "<!-- codex-dispatch-supervisor-rework: "
            '{"checkpoint":"CP3","attempt":1} -->'
        ),
    )
    monkeypatch.setattr(
        watcher,
        "load_state",
        lambda _: {
            "issues": {
                "009": {
                    "last_checkpoint": "CP3",
                    "last_status": "failed",
                    "publication_label": "rework-1",
                }
            }
        },
    )
    monkeypatch.setattr(
        watcher,
        "get_issue_state",
        lambda state, issue_id: (
            state["issues"]["009"]
        ),
    )
    monkeypatch.setattr(
        watcher,
        "remote_checkpoint_exists",
        lambda **kwargs: False,
    )

    with pytest.raises(
        DispatchError,
        match="new rework attempt",
    ):
        watcher.run_once(
            repo_root=repo,
            issue_id="009",
            codex_bin="codex",
            timeout_seconds=10,
        )

from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

if __package__:
    from .codex_dispatch import (
        DispatchError,
        dispatch,
        ensure_clean_worktree,
        fetch_remote_issue_note,
        find_repo_root,
        get_current_branch,
        get_issue_state,
        load_state,
        normalize_issue_id,
        parse_supervisor_approval,
        parse_supervisor_rework,
        resolve_context,
        run_git,
    )
else:
    from codex_dispatch import (
        DispatchError,
        dispatch,
        ensure_clean_worktree,
        fetch_remote_issue_note,
        find_repo_root,
        get_current_branch,
        get_issue_state,
        load_state,
        normalize_issue_id,
        parse_supervisor_approval,
        parse_supervisor_rework,
        resolve_context,
        run_git,
    )


MIN_POLL_SECONDS = 5
APPROVAL_TO_WRITE_CHECKPOINT = {
    "CP1": "CP2",
    "CP2": "CP3",
}


def checkpoint_commit_message(
    issue_id: str,
    checkpoint: str,
    publication_label: str | None = None,
) -> str:
    message = (
        f"checkpoint(issue-{issue_id}): "
        f"{checkpoint}"
    )
    if publication_label:
        message += f" {publication_label}"
    return message


def remote_checkpoint_exists(
    *,
    repo_root: Path,
    branch: str,
    issue_id: str,
    checkpoint: str,
    publication_label: str | None = None,
) -> bool:
    subjects = run_git(
        [
            "log",
            f"origin/{branch}",
            "--format=%s",
            "-n",
            "200",
        ],
        cwd=repo_root,
    ).splitlines()

    expected = checkpoint_commit_message(
        issue_id,
        checkpoint,
        publication_label,
    )
    return expected in subjects


def next_write_checkpoint(
    *,
    approved_through: str,
    issue_state: dict,
    remote_checkpoint_done: bool,
) -> str | None:
    checkpoint = APPROVAL_TO_WRITE_CHECKPOINT.get(
        approved_through
    )
    if checkpoint is None:
        return None

    if remote_checkpoint_done:
        return None

    if (
        issue_state.get("last_checkpoint")
        == checkpoint
    ):
        status = issue_state.get("last_status")
        if status == "succeeded":
            raise DispatchError(
                f"{checkpoint} is recorded locally as succeeded, "
                "but the matching remote checkpoint publication "
                "is missing. Supervisor/operator reconciliation "
                "is required."
            )
        if status == "failed":
            raise DispatchError(
                f"{checkpoint} previously failed. "
                "Watcher will not retry automatically; "
                "Supervisor/operator action is required."
            )

    return checkpoint


def fast_forward_issue_branch(
    *,
    repo_root: Path,
    branch: str,
) -> None:
    ensure_clean_worktree(repo_root)

    run_git(
        [
            "fetch",
            "--quiet",
            "origin",
            branch,
        ],
        cwd=repo_root,
    )

    run_git(
        [
            "pull",
            "--ff-only",
            "origin",
            branch,
        ],
        cwd=repo_root,
    )


def _try_lock_file(handle) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(
                    handle.fileno(),
                    msvcrt.LK_NBLCK,
                    1,
                )
            except OSError as exc:
                raise DispatchError(
                    "Another Watcher already owns this "
                    "Engineering Issue."
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(
                    handle.fileno(),
                    fcntl.LOCK_EX
                    | fcntl.LOCK_NB,
                )
            except OSError as exc:
                raise DispatchError(
                    "Another Watcher already owns this "
                    "Engineering Issue."
                ) from exc
    except ImportError as exc:
        raise DispatchError(
            "This platform does not provide the required "
            "Watcher file-lock primitive."
        ) from exc


def _write_lock_metadata(handle) -> None:
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.write("\n")
    handle.flush()


def _unlock_file(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(
            handle.fileno(),
            msvcrt.LK_UNLCK,
            1,
        )
    else:
        import fcntl

        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_UN,
        )


@contextmanager
def watcher_lock(
    repo_root: Path,
    issue_id: str,
) -> Iterator[None]:
    lock_dir = repo_root / ".codex-dispatch"
    lock_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    lock_path = (
        lock_dir
        / f"watch-{issue_id}.lock"
    )

    handle = lock_path.open(
        "a+",
        encoding="utf-8",
    )
    locked = False

    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write("\n")
            handle.flush()
        handle.seek(0)

        _try_lock_file(handle)
        locked = True

        _write_lock_metadata(handle)

        yield

    finally:
        if locked:
            try:
                _unlock_file(handle)
            except OSError:
                pass

        handle.close()

        if locked:
            try:
                lock_path.unlink()
            except OSError:
                pass

def run_once(
    *,
    repo_root: Path,
    issue_id: str,
    codex_bin: str,
    timeout_seconds: int,
) -> int | None:
    branch = get_current_branch(
        repo_root
    )
    expected_marker = f"issue-{issue_id}"
    if expected_marker not in branch.lower():
        raise DispatchError(
            "Watcher must run on the matching "
            f"Engineering Issue Branch containing "
            f"{expected_marker!r}; current branch "
            f"is {branch!r}."
        )

    fast_forward_issue_branch(
        repo_root=repo_root,
        branch=branch,
    )

    probe = resolve_context(
        start=repo_root,
        issue_id=issue_id,
        checkpoint="CP1",
    )
    remote_note = fetch_remote_issue_note(
        probe
    )
    approved = parse_supervisor_approval(
        remote_note
    )

    candidate = APPROVAL_TO_WRITE_CHECKPOINT.get(
        approved
    )
    if candidate is None:
        return None

    state = load_state(repo_root)
    issue_state = get_issue_state(
        state,
        issue_id,
    )

    rework = parse_supervisor_rework(
        remote_note
    )
    publication_label: str | None = None
    force = False

    if rework is not None:
        rework_checkpoint, attempt = rework

        if rework_checkpoint != candidate:
            raise DispatchError(
                "Supervisor rework checkpoint does not match "
                f"the currently authorized write checkpoint "
                f"{candidate}; got {rework_checkpoint}."
            )

        publication_label = f"rework-{attempt}"

        rework_published = remote_checkpoint_exists(
            repo_root=repo_root,
            branch=branch,
            issue_id=issue_id,
            checkpoint=candidate,
            publication_label=publication_label,
        )
        if rework_published:
            return None

        if (
            issue_state.get("last_checkpoint")
            == candidate
            and issue_state.get("publication_label")
            == publication_label
            and issue_state.get("last_status")
            == "failed"
        ):
            raise DispatchError(
                f"{candidate} {publication_label} previously failed. "
                "Supervisor must authorize a new rework attempt; "
                "Watcher will not retry automatically."
            )

        checkpoint = candidate
        force = True

    else:
        already_published = remote_checkpoint_exists(
            repo_root=repo_root,
            branch=branch,
            issue_id=issue_id,
            checkpoint=candidate,
        )
        checkpoint = next_write_checkpoint(
            approved_through=approved,
            issue_state=issue_state,
            remote_checkpoint_done=already_published,
        )
        if checkpoint is None:
            return None

    context = resolve_context(
        start=repo_root,
        issue_id=issue_id,
        checkpoint=checkpoint,
    )

    result = dispatch(
        context,
        dry_run=False,
        force=force,
        new_session=False,
        codex_bin=codex_bin,
        timeout_seconds=timeout_seconds,
        publication_label=publication_label,
    )
    if result != 0:
        raise DispatchError(
            f"{checkpoint} failed with exit code "
            f"{result}. Watcher stopped; no automatic "
            "retry will occur."
        )

    return result


def parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Watch one Reliable AI Engineering Issue "
            "for Supervisor-authorized Codex write "
            "checkpoints."
        )
    )
    parser.add_argument(
        "--issue",
        required=True,
        help="Engineering Issue ID, e.g. 009.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help=(
            "Path inside the Git repository. "
            "Defaults to current directory."
        ),
    )
    parser.add_argument(
        "--poll-seconds",
        type=int,
        default=30,
        help=(
            "Git polling interval. Minimum 5 seconds; "
            "default 30."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Perform one synchronization/check and "
            "exit. Useful for smoke testing."
        ),
    )
    parser.add_argument(
        "--codex-bin",
        default="codex",
        help=(
            "Codex CLI executable name/path. "
            "Defaults to 'codex'."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help=(
            "Maximum duration of one Codex checkpoint. "
            "Default: 1800."
        ),
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
) -> int:
    args = parse_args(argv)

    try:
        issue_id = normalize_issue_id(
            args.issue
        )
        if args.poll_seconds < MIN_POLL_SECONDS:
            raise DispatchError(
                f"--poll-seconds must be at least "
                f"{MIN_POLL_SECONDS}."
            )
        if args.timeout_seconds <= 0:
            raise DispatchError(
                "--timeout-seconds must be greater "
                "than zero."
            )

        repo_root = find_repo_root(
            args.repo.resolve()
        )

        with watcher_lock(
            repo_root,
            issue_id,
        ):
            while True:
                result = run_once(
                    repo_root=repo_root,
                    issue_id=issue_id,
                    codex_bin=args.codex_bin,
                    timeout_seconds=args.timeout_seconds,
                )

                if args.once:
                    return (
                        0
                        if result is None
                        else result
                    )

                time.sleep(
                    args.poll_seconds
                )

    except KeyboardInterrupt:
        print("Watcher stopped.")
        return 0
    except DispatchError as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

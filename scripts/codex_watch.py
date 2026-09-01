from __future__ import annotations

import argparse
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

from scripts.codex_dispatch import (
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
) -> str:
    return (
        f"checkpoint(issue-{issue_id}): "
        f"{checkpoint}"
    )


def remote_checkpoint_exists(
    *,
    repo_root: Path,
    branch: str,
    issue_id: str,
    checkpoint: str,
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
            return None
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


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

    return True


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

    while True:
        try:
            fd = os.open(
                lock_path,
                os.O_CREAT
                | os.O_EXCL
                | os.O_WRONLY,
            )
        except FileExistsError:
            try:
                raw = lock_path.read_text(
                    encoding="utf-8"
                ).strip()
                owner_pid = int(raw)
            except (
                OSError,
                ValueError,
            ):
                raise DispatchError(
                    "Watcher lock exists but cannot be "
                    f"validated: {lock_path}"
                ) from None

            if pid_is_alive(owner_pid):
                raise DispatchError(
                    "Another Watcher already owns "
                    f"Engineering Issue #{issue_id} "
                    f"(pid={owner_pid})."
                )

            try:
                lock_path.unlink()
            except OSError as exc:
                raise DispatchError(
                    "Stale Watcher lock could not be "
                    f"removed: {lock_path}"
                ) from exc
            continue

        try:
            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write(str(os.getpid()))
                handle.write("\n")
            break
        except Exception:
            try:
                lock_path.unlink()
            except OSError:
                pass
            raise

    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
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
        force=False,
        new_session=False,
        codex_bin=codex_bin,
        timeout_seconds=timeout_seconds,
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
            file=__import__("sys").stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

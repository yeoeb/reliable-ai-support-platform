from __future__ import annotations

import argparse
from fnmatch import fnmatch
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

CHECKPOINT_SANDBOX = {
    "CP0": "read-only",
    "CP1": "read-only",
    "CP2": "workspace-write",
    "CP3": "workspace-write",
    "CP4": "read-only",
    "CP5": "read-only",
    "CP6": "read-only",
}

WRITE_CHECKPOINTS = {"CP2", "CP3"}
ISSUE_BRANCH_CHECKPOINTS = {
    "CP1",
    "CP2",
    "CP3",
    "CP4",
    "CP5",
    "CP6",
}
CHECKPOINT_ORDER = tuple(CHECKPOINT_SANDBOX)
REQUIRED_SUPERVISOR_APPROVAL = {
    "CP1": "CP0",
    "CP2": "CP1",
    "CP3": "CP2",
    "CP4": "CP3",
    "CP5": "CP4",
    "CP6": "CP5",
}
SUPERVISOR_GATE_KEY = (
    "codex-dispatch-supervisor-approved-through"
)
WRITE_ALLOW_KEY = "codex-dispatch-write-allow"
PROTECTED_PUBLISH_PATHS = {
    ".gitignore",
    "AGENTS.md",
    "docs/PROJECT_STATE.md",
    "docs/codex-dispatcher.md",
    "docs/issues/README.md",
    "scripts/codex_dispatch.py",
}
PROTECTED_PUBLISH_PREFIXES = (
    ".git/",
    ".codex-dispatch/",
    ".github/",
)
OVERBROAD_WRITE_PATTERNS = {
    "*",
    "**",
    "**/*",
}
STATE_DIR_NAME = ".codex-dispatch"
STATE_FILE_NAME = "state.json"


class DispatchError(RuntimeError):
    """Raised when dispatcher safety or repository preconditions fail."""


@dataclass(frozen=True)
class DispatchContext:
    repo_root: Path
    issue_id: str
    checkpoint: str
    sandbox: str
    branch: str
    issue_note: Path


def normalize_issue_id(raw: str) -> str:
    value = raw.strip().lstrip("#")
    if not value.isdigit():
        raise DispatchError("Engineering Issue ID must be numeric.")
    return value.zfill(3)


def normalize_checkpoint(raw: str) -> str:
    value = raw.strip().upper()
    if value not in CHECKPOINT_SANDBOX:
        allowed = ", ".join(CHECKPOINT_SANDBOX)
        raise DispatchError(
            f"Unsupported checkpoint {raw!r}. Expected one of: {allowed}."
        )
    return value


def run_git(
    args: Sequence[str],
    *,
    cwd: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    result = runner(
        ["git", *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (
            result.stderr or result.stdout or "Git command failed."
        ).strip()
        raise DispatchError(detail)
    return (result.stdout or "").strip()


def find_repo_root(
    start: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> Path:
    output = run_git(
        ["rev-parse", "--show-toplevel"],
        cwd=start,
        runner=runner,
    )
    root = Path(output).resolve()
    if not root.exists():
        raise DispatchError(
            f"Git repository root does not exist: {root}"
        )
    return root


def get_current_branch(
    repo_root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    branch = run_git(
        ["rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root,
        runner=runner,
    )
    if not branch or branch == "HEAD":
        raise DispatchError(
            "Detached HEAD is not supported by the dispatcher."
        )
    return branch


def find_issue_note(repo_root: Path, issue_id: str) -> Path:
    issue_dir = repo_root / "docs" / "issues"
    matches = sorted(
        issue_dir.glob(f"issue-{issue_id}-*.md")
    )
    if not matches:
        raise DispatchError(
            f"No execution note found for Engineering Issue #{issue_id}. "
            f"Expected docs/issues/issue-{issue_id}-*.md."
        )
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise DispatchError(
            "Multiple execution notes found for Engineering Issue "
            f"#{issue_id}: {names}"
        )
    return matches[0]


def resolve_context(
    *,
    start: Path,
    issue_id: str,
    checkpoint: str,
    git_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> DispatchContext:
    repo_root = find_repo_root(
        start,
        runner=git_runner,
    )

    required = [
        repo_root / "AGENTS.md",
        repo_root / "docs" / "PROJECT_STATE.md",
    ]
    missing = [
        str(path.relative_to(repo_root))
        for path in required
        if not path.is_file()
    ]
    if missing:
        raise DispatchError(
            "Required repository context is missing: "
            + ", ".join(missing)
        )

    branch = get_current_branch(
        repo_root,
        runner=git_runner,
    )
    if checkpoint in ISSUE_BRANCH_CHECKPOINTS:
        expected_marker = f"issue-{issue_id}"
        if expected_marker not in branch.lower():
            raise DispatchError(
                f"{checkpoint} for Engineering Issue #{issue_id} "
                f"requires a dedicated branch containing "
                f"{expected_marker!r}; current branch is {branch!r}."
            )

    if (
        checkpoint in WRITE_CHECKPOINTS
        and branch in {"main", "develop"}
    ):
        raise DispatchError(
            f"{checkpoint} cannot write on protected "
            f"integration branch {branch!r}."
        )

    issue_note = find_issue_note(
        repo_root,
        issue_id,
    )
    return DispatchContext(
        repo_root=repo_root,
        issue_id=issue_id,
        checkpoint=checkpoint,
        sandbox=CHECKPOINT_SANDBOX[checkpoint],
        branch=branch,
        issue_note=issue_note,
    )


def build_prompt(context: DispatchContext) -> str:
    issue_path = context.issue_note.relative_to(
        context.repo_root
    ).as_posix()

    common = f"""Execute {context.checkpoint} for Engineering Issue #{context.issue_id}.

Repository state, not chat history, is authoritative.

Before acting, read:
1. AGENTS.md
2. docs/PROJECT_STATE.md
3. {issue_path}

Current branch: {context.branch}
Sandbox for this checkpoint: {context.sandbox}

Do not commit, push, merge, or switch to main.
Stay inside the Issue Scope and Allowed Write Set.
If repository state contradicts the execution note, stop and report the contradiction.
"""

    instructions = {
        "CP0": """This is context bootstrap only.
Return:
- source-of-truth files read
- dependency status
- contradictions or stale state
- blockers
Do not modify files.
Stop after CP0.
""",
        "CP1": """This is planning only.
Return:
- implementation plan
- dependencies
- Scope / Out of Scope validation
- proposed Allowed Write Set
- security and regression risks
- required targeted and regression tests
Do not modify files.
Stop after CP1.
""",
        "CP2": """Implement only the current bounded CP2 slice defined by the execution note.
Run only verification needed for that slice.
Update the execution note's checkpoint/current-state section when appropriate.
Do not expand Scope silently.
Stop after the bounded CP2 slice; do not continue to later checkpoints.
""",
        "CP3": """Run the verification required by the execution note.
Fix only failures caused by the in-scope implementation.
Record concise evidence in the execution note when appropriate.
Do not broaden the feature.
Stop after CP3.
""",
        "CP4": """Review only.
Inspect the diff, Acceptance Criteria, security boundaries, regressions, and test evidence.
Return findings ordered by severity.
Do not modify files.
Stop after CP4.
""",
        "CP5": """Identify reusable engineering knowledge and documentation drift.
Do not copy chat transcripts.
Do not modify product code.
Return Knowledge candidates and required documentation updates.
Stop after CP5.
""",
        "CP6": """Prepare delivery evidence only.
Verify the intended branch, changed files, test evidence, and PR-ready summary.
Do not commit, push, merge, or modify files.
Stop after CP6.
""",
    }

    return common + "\n" + instructions[context.checkpoint]


def state_path(repo_root: Path) -> Path:
    return (
        repo_root
        / STATE_DIR_NAME
        / STATE_FILE_NAME
    )


def load_state(repo_root: Path) -> dict:
    path = state_path(repo_root)
    if not path.exists():
        return {"issues": {}}

    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise DispatchError(
            f"Cannot read dispatcher state: {exc}"
        ) from exc

    if (
        not isinstance(data, dict)
        or not isinstance(
            data.get("issues", {}),
            dict,
        )
    ):
        raise DispatchError(
            "Dispatcher state has an invalid structure."
        )

    data.setdefault("issues", {})
    return data


def save_state(
    repo_root: Path,
    state: dict,
) -> None:
    path = state_path(repo_root)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            state,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def get_issue_state(
    state: dict,
    issue_id: str,
) -> dict:
    value = state.get(
        "issues",
        {},
    ).get(
        issue_id,
        {},
    )
    if not isinstance(value, dict):
        raise DispatchError(
            f"Dispatcher state for Issue #{issue_id} is invalid."
        )
    return value


def _control_marker_candidates(
    content: str,
    key: str,
) -> list[str]:
    prefix = f"<!-- {key}:"
    return [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith(prefix)
    ]


def parse_supervisor_approval(
    content: str,
) -> str:
    candidate_lines = _control_marker_candidates(
        content,
        SUPERVISOR_GATE_KEY,
    )

    if len(candidate_lines) != 1:
        raise DispatchError(
            "Expected exactly one Supervisor approval marker "
            f"containing {SUPERVISOR_GATE_KEY!r}; "
            f"found {len(candidate_lines)}."
        )

    prefix = f"<!-- {SUPERVISOR_GATE_KEY}:"
    suffix = "-->"
    line = candidate_lines[0]

    if (
        not line.startswith(prefix)
        or not line.endswith(suffix)
    ):
        raise DispatchError(
            "Supervisor approval marker is malformed."
        )

    value = line[
        len(prefix) : -len(suffix)
    ].strip()

    try:
        return normalize_checkpoint(value)
    except DispatchError as exc:
        raise DispatchError(
            "Supervisor approval marker contains "
            f"an invalid checkpoint: {value!r}."
        ) from exc


def fetch_remote_issue_note(
    context: DispatchContext,
    *,
    runner: Callable[
        ...,
        subprocess.CompletedProcess[str],
    ] = subprocess.run,
) -> str:
    relative_path = context.issue_note.relative_to(
        context.repo_root
    ).as_posix()

    run_git(
        [
            "fetch",
            "--quiet",
            "origin",
            context.branch,
        ],
        cwd=context.repo_root,
        runner=runner,
    )

    return run_git(
        [
            "show",
            (
                f"origin/{context.branch}:"
                f"{relative_path}"
            ),
        ],
        cwd=context.repo_root,
        runner=runner,
    )


def validate_supervisor_gate(
    context: DispatchContext,
    remote_note: str,
) -> str:
    approved = parse_supervisor_approval(
        remote_note
    )
    required = REQUIRED_SUPERVISOR_APPROVAL.get(
        context.checkpoint
    )

    if required is None:
        return approved

    approved_index = CHECKPOINT_ORDER.index(
        approved
    )
    required_index = CHECKPOINT_ORDER.index(
        required
    )

    if approved_index < required_index:
        raise DispatchError(
            f"{context.checkpoint} requires remote "
            f"Supervisor approval through {required}; "
            f"remote approval is only through {approved}."
        )

    return approved


def parse_write_allow(
    content: str,
) -> list[str]:
    candidate_lines = _control_marker_candidates(
        content,
        WRITE_ALLOW_KEY,
    )

    if len(candidate_lines) != 1:
        raise DispatchError(
            "Expected exactly one write-allow marker "
            f"containing {WRITE_ALLOW_KEY!r}; "
            f"found {len(candidate_lines)}."
        )

    prefix = f"<!-- {WRITE_ALLOW_KEY}:"
    suffix = "-->"
    line = candidate_lines[0]

    if (
        not line.startswith(prefix)
        or not line.endswith(suffix)
    ):
        raise DispatchError(
            "Write-allow marker is malformed."
        )

    payload = line[
        len(prefix) : -len(suffix)
    ].strip()

    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DispatchError(
            "Write-allow marker must contain valid JSON."
        ) from exc

    if (
        not isinstance(value, list)
        or not value
        or not all(
            isinstance(item, str)
            and item
            for item in value
        )
    ):
        raise DispatchError(
            "Write-allow marker must be a non-empty "
            "JSON array of strings."
        )

    patterns: list[str] = []
    for pattern in value:
        if pattern in OVERBROAD_WRITE_PATTERNS:
            raise DispatchError(
                "Write-allow marker contains an overbroad "
                f"pattern: {pattern!r}."
            )

        if (
            "\\" in pattern
            or pattern.startswith("/")
            or ".." in Path(pattern).parts
        ):
            raise DispatchError(
                "Write-allow patterns must be safe "
                f"repository-relative POSIX paths: {pattern!r}."
            )
        patterns.append(pattern)

    if len(set(patterns)) != len(patterns):
        raise DispatchError(
            "Write-allow marker contains duplicate patterns."
        )

    return patterns


def ensure_clean_worktree(
    repo_root: Path,
    *,
    runner: Callable[
        ...,
        subprocess.CompletedProcess[str],
    ] = subprocess.run,
) -> None:
    status = run_git(
        [
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        cwd=repo_root,
        runner=runner,
    )
    if status:
        raise DispatchError(
            "Write checkpoint requires a clean Working Tree "
            "before Codex starts."
        )


def get_local_head(
    context: DispatchContext,
    *,
    runner: Callable[
        ...,
        subprocess.CompletedProcess[str],
    ] = subprocess.run,
) -> str:
    return run_git(
        ["rev-parse", "HEAD"],
        cwd=context.repo_root,
        runner=runner,
    )


def get_remote_head(
    context: DispatchContext,
    *,
    runner: Callable[
        ...,
        subprocess.CompletedProcess[str],
    ] = subprocess.run,
) -> str:
    return run_git(
        [
            "rev-parse",
            f"origin/{context.branch}",
        ],
        cwd=context.repo_root,
        runner=runner,
    )


def get_changed_paths(
    repo_root: Path,
    *,
    runner: Callable[
        ...,
        subprocess.CompletedProcess[str],
    ] = subprocess.run,
) -> list[str]:
    tracked = run_git(
        [
            "diff",
            "--name-only",
            "HEAD",
            "--",
        ],
        cwd=repo_root,
        runner=runner,
    )
    untracked = run_git(
        [
            "ls-files",
            "--others",
            "--exclude-standard",
        ],
        cwd=repo_root,
        runner=runner,
    )

    values = []
    for output in (tracked, untracked):
        if output:
            values.extend(
                line
                for line in output.splitlines()
                if line
            )

    return sorted(set(values))


def path_is_allowed(
    path: str,
    patterns: Sequence[str],
) -> bool:
    if (
        path in PROTECTED_PUBLISH_PATHS
        or any(
            path.startswith(prefix)
            for prefix in PROTECTED_PUBLISH_PREFIXES
        )
    ):
        return False

    return any(
        fnmatch(path, pattern)
        for pattern in patterns
    )


def validate_changed_paths(
    paths: Sequence[str],
    patterns: Sequence[str],
) -> None:
    disallowed = [
        path
        for path in paths
        if not path_is_allowed(
            path,
            patterns,
        )
    ]
    if disallowed:
        raise DispatchError(
            "Checkpoint changed files outside the "
            "Supervisor-controlled write Allowlist: "
            + ", ".join(disallowed)
        )


def validate_control_markers_unchanged(
    *,
    remote_note: str,
    local_note: str,
) -> None:
    remote_approval = parse_supervisor_approval(
        remote_note
    )
    local_approval = parse_supervisor_approval(
        local_note
    )
    if local_approval != remote_approval:
        raise DispatchError(
            "Executor modified the Supervisor approval marker; "
            "publication is blocked."
        )

    remote_allow = parse_write_allow(
        remote_note
    )
    local_allow = parse_write_allow(
        local_note
    )
    if local_allow != remote_allow:
        raise DispatchError(
            "Executor modified the write-allow marker; "
            "publication is blocked."
        )


def publish_write_checkpoint(
    context: DispatchContext,
    *,
    expected_remote_head: str,
    remote_note: str,
    patterns: Sequence[str],
    runner: Callable[
        ...,
        subprocess.CompletedProcess[str],
    ] = subprocess.run,
) -> str | None:
    run_git(
        [
            "fetch",
            "--quiet",
            "origin",
            context.branch,
        ],
        cwd=context.repo_root,
        runner=runner,
    )
    current_remote_head = get_remote_head(
        context,
        runner=runner,
    )

    if current_remote_head != expected_remote_head:
        raise DispatchError(
            "Remote Feature Branch changed during Codex "
            "execution; refusing to publish stale work."
        )

    local_head = get_local_head(
        context,
        runner=runner,
    )
    if local_head != expected_remote_head:
        raise DispatchError(
            "Local HEAD changed during Codex execution; "
            "the Executor must not create commits directly."
        )

    try:
        local_note = context.issue_note.read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        raise DispatchError(
            "Local Issue execution note is missing or unreadable; "
            "publication is blocked."
        ) from exc

    validate_control_markers_unchanged(
        remote_note=remote_note,
        local_note=local_note,
    )

    changed_paths = get_changed_paths(
        context.repo_root,
        runner=runner,
    )
    if not changed_paths:
        return None

    validate_changed_paths(
        changed_paths,
        patterns,
    )

    run_git(
        [
            "add",
            "--",
            *changed_paths,
        ],
        cwd=context.repo_root,
        runner=runner,
    )

    run_git(
        ["diff", "--cached", "--check"],
        cwd=context.repo_root,
        runner=runner,
    )

    commit_message = (
        f"checkpoint(issue-{context.issue_id}): "
        f"{context.checkpoint}"
    )
    run_git(
        [
            "commit",
            "-m",
            commit_message,
        ],
        cwd=context.repo_root,
        runner=runner,
    )

    commit_sha = run_git(
        ["rev-parse", "HEAD"],
        cwd=context.repo_root,
        runner=runner,
    )

    run_git(
        [
            "push",
            "origin",
            f"HEAD:{context.branch}",
        ],
        cwd=context.repo_root,
        runner=runner,
    )

    return commit_sha


def build_codex_command(
    context: DispatchContext,
    *,
    codex_bin: str,
    session_id: str | None,
) -> list[str]:
    command = [
        codex_bin,
        "exec",
        "--json",
        "--color",
        "never",
        "--sandbox",
        context.sandbox,
        "--cd",
        str(context.repo_root),
    ]

    if session_id:
        command.extend(
            [
                "resume",
                session_id,
                "-",
            ]
        )
    else:
        command.append("-")

    return command


def extract_session_id(
    stdout: str,
) -> str | None:
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") != "thread.started":
            continue

        for key in (
            "thread_id",
            "threadId",
            "id",
        ):
            value = event.get(key)
            if (
                isinstance(value, str)
                and value
            ):
                return value

        thread = event.get("thread")
        if isinstance(thread, dict):
            for key in (
                "id",
                "thread_id",
                "threadId",
            ):
                value = thread.get(key)
                if (
                    isinstance(value, str)
                    and value
                ):
                    return value

    return None


def extract_terminal_status(
    stdout: str,
    returncode: int,
) -> str:
    if returncode != 0:
        return "failed"

    status = "succeeded"

    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")
        if event_type == "turn.completed":
            status = "succeeded"
        elif event_type in {
            "turn.failed",
            "error",
        }:
            status = "failed"

    return status


def run_codex(
    command: Sequence[str],
    prompt: str,
    *,
    timeout_seconds: int,
    runner: Callable[
        ...,
        subprocess.CompletedProcess[str],
    ] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            list(command),
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise DispatchError(
            "Codex exceeded the "
            f"{timeout_seconds}-second "
            "dispatcher timeout."
        ) from exc


def dispatch(
    context: DispatchContext,
    *,
    dry_run: bool,
    force: bool,
    new_session: bool,
    codex_bin: str,
    timeout_seconds: int,
    process_runner: Callable[
        ...,
        subprocess.CompletedProcess[str],
    ] = subprocess.run,
    git_runner: Callable[
        ...,
        subprocess.CompletedProcess[str],
    ] = subprocess.run,
) -> int:
    state = load_state(
        context.repo_root
    )
    previous = get_issue_state(
        state,
        context.issue_id,
    )

    if (
        not force
        and previous.get(
            "last_checkpoint"
        )
        == context.checkpoint
        and previous.get(
            "last_status"
        )
        == "succeeded"
    ):
        raise DispatchError(
            f"{context.checkpoint} already succeeded "
            f"for Issue #{context.issue_id}. "
            "Use --force to run it again."
        )

    remote_note = fetch_remote_issue_note(
        context,
        runner=git_runner,
    )
    supervisor_approved_through = (
        validate_supervisor_gate(
            context,
            remote_note,
        )
    )

    write_patterns: list[str] | None = None
    remote_head_before: str | None = None
    if context.checkpoint in WRITE_CHECKPOINTS:
        ensure_clean_worktree(
            context.repo_root,
            runner=git_runner,
        )
        write_patterns = parse_write_allow(
            remote_note
        )
        remote_head_before = get_remote_head(
            context,
            runner=git_runner,
        )
        local_head_before = get_local_head(
            context,
            runner=git_runner,
        )
        if local_head_before != remote_head_before:
            raise DispatchError(
                "Local Issue Branch is not synchronized with "
                "the authoritative remote Head. Run a fast-forward "
                "pull before starting the write checkpoint."
            )

    previous_branch = previous.get(
        "branch"
    )
    session_id = (
        None
        if new_session
        else previous.get("session_id")
    )

    if (
        session_id
        and previous_branch
        and previous_branch
        != context.branch
    ):
        raise DispatchError(
            "Stored Codex Session belongs "
            "to a different branch "
            f"({previous_branch!r}); current branch "
            f"is {context.branch!r}. "
            "Use --new-session after verifying "
            "the branch change."
        )

    prompt = build_prompt(context)
    command = build_codex_command(
        context,
        codex_bin=codex_bin,
        session_id=session_id,
    )

    if dry_run:
        print(
            json.dumps(
                {
                    "issue_id": context.issue_id,
                    "checkpoint": context.checkpoint,
                    "sandbox": context.sandbox,
                    "branch": context.branch,
                    "issue_note": str(
                        context.issue_note.relative_to(
                            context.repo_root
                        )
                    ),
                    "resume_session_id": session_id,
                    "supervisor_approved_through": (
                        supervisor_approved_through
                    ),
                    "write_allow": write_patterns,
                    "remote_head_before": remote_head_before,
                    "command": command,
                    "prompt": prompt,
                },
                indent=2,
            )
        )
        return 0

    if shutil.which(codex_bin) is None:
        raise DispatchError(
            f"Cannot find {codex_bin!r} on PATH. "
            "Install/login to Codex CLI first."
        )

    result = run_codex(
        command,
        prompt,
        timeout_seconds=timeout_seconds,
        runner=process_runner,
    )

    if result.stdout:
        print(
            result.stdout,
            end=(
                ""
                if result.stdout.endswith("\n")
                else "\n"
            ),
        )

    if result.stderr:
        print(
            result.stderr,
            file=sys.stderr,
            end=(
                ""
                if result.stderr.endswith("\n")
                else "\n"
            ),
        )

    observed_session_id = (
        extract_session_id(
            result.stdout
        )
        or session_id
    )
    status = extract_terminal_status(
        result.stdout,
        result.returncode,
    )

    published_commit_sha: str | None = None
    if (
        status == "succeeded"
        and context.checkpoint in WRITE_CHECKPOINTS
    ):
        assert remote_head_before is not None
        assert write_patterns is not None
        published_commit_sha = publish_write_checkpoint(
            context,
            expected_remote_head=remote_head_before,
            remote_note=remote_note,
            patterns=write_patterns,
            runner=git_runner,
        )

    issues = state.setdefault(
        "issues",
        {},
    )
    issues[context.issue_id] = {
        "session_id": observed_session_id,
        "branch": context.branch,
        "last_checkpoint": context.checkpoint,
        "last_status": status,
        "last_returncode": result.returncode,
        "published_commit_sha": published_commit_sha,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }
    save_state(
        context.repo_root,
        state,
    )

    return result.returncode


def parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dispatch one bounded Reliable AI "
            "engineering checkpoint to local Codex."
        )
    )

    parser.add_argument(
        "--issue",
        required=True,
        help="Engineering Issue ID, e.g. 009.",
    )
    parser.add_argument(
        "--checkpoint",
        required=True,
        help="Checkpoint CP0 through CP6.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help=(
            "Path inside the Git repository. "
            "Defaults to the current directory."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Resolve context and print the "
            "command/prompt without starting Codex."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Allow re-running a checkpoint already "
            "recorded as succeeded."
        ),
    )
    parser.add_argument(
        "--new-session",
        action="store_true",
        help=(
            "Do not resume the stored Codex Session "
            "for this Engineering Issue."
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
            "Maximum Codex execution time for one "
            "checkpoint. Default: 1800."
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
        checkpoint = normalize_checkpoint(
            args.checkpoint
        )

        if args.timeout_seconds <= 0:
            raise DispatchError(
                "--timeout-seconds must be "
                "greater than zero."
            )

        context = resolve_context(
            start=args.repo.resolve(),
            issue_id=issue_id,
            checkpoint=checkpoint,
        )

        return dispatch(
            context,
            dry_run=args.dry_run,
            force=args.force,
            new_session=args.new_session,
            codex_bin=args.codex_bin,
            timeout_seconds=args.timeout_seconds,
        )

    except DispatchError as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

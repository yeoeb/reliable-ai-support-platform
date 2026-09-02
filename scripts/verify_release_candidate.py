from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Sequence


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)


class ReleaseVerificationError(RuntimeError):
    pass


def _run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise ReleaseVerificationError(
            "Required Git repository state could not be resolved"
        )
    return completed.stdout.strip()


def _git_diff_is_empty(base: str, head: str) -> bool:
    completed = subprocess.run(
        ["git", "diff", "--quiet", f"{base}..{head}", "--"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    raise ReleaseVerificationError(
        "Required Git content comparison failed"
    )


def _tag_exists(tag_name: str) -> bool:
    completed = subprocess.run(
        [
            "git",
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/tags/{tag_name}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    raise ReleaseVerificationError(
        "Git tag state could not be verified"
    )


def _validate_sha(value: str, field_name: str) -> str:
    if not _SHA_RE.fullmatch(value):
        raise ReleaseVerificationError(
            f"{field_name} must be a full lowercase Git SHA"
        )
    return value


def _read_project_version(path: Path) -> str:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        version = data["project"]["version"]
    except (
        OSError,
        UnicodeError,
        tomllib.TOMLDecodeError,
        KeyError,
        TypeError,
    ) as exc:
        raise ReleaseVerificationError(
            "Project version could not be read"
        ) from exc

    if (
        not isinstance(version, str)
        or not _SEMVER_RE.fullmatch(version)
    ):
        raise ReleaseVerificationError(
            "Project version must use MAJOR.MINOR.PATCH"
        )
    return version


def _read_fastapi_version(path: Path) -> str:
    try:
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ReleaseVerificationError(
            "FastAPI application version could not be inspected"
        ) from exc

    versions: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (
            isinstance(node.func, ast.Name)
            and node.func.id == "FastAPI"
        ):
            continue
        for keyword in node.keywords:
            if keyword.arg != "version":
                continue
            if (
                isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                versions.append(keyword.value.value)
            else:
                raise ReleaseVerificationError(
                    "FastAPI version must be a static string literal"
                )

    if len(versions) != 1:
        raise ReleaseVerificationError(
            "Expected exactly one static FastAPI version"
        )
    return versions[0]


def verify_release_candidate(
    *,
    base_ref: str,
    head_ref: str,
    base_repository: str,
    head_repository: str,
    expected_head_sha: str,
    project_file: Path = Path("pyproject.toml"),
    app_file: Path = Path("app/main.py"),
) -> dict[str, object]:
    if base_ref != "main":
        raise ReleaseVerificationError(
            "Release base must be main"
        )
    if head_ref != "develop":
        raise ReleaseVerificationError(
            "Release head must be develop"
        )
    if (
        not base_repository
        or base_repository != head_repository
    ):
        raise ReleaseVerificationError(
            "Release must originate from the same repository"
        )

    expected = _validate_sha(
        expected_head_sha,
        "expected_head_sha",
    )
    checked_out = _validate_sha(
        _run_git("rev-parse", "HEAD"),
        "checked_out_head",
    )
    develop_sha = _validate_sha(
        _run_git("rev-parse", "origin/develop"),
        "origin_develop",
    )
    main_sha = _validate_sha(
        _run_git("rev-parse", "origin/main"),
        "origin_main",
    )

    if checked_out != expected:
        raise ReleaseVerificationError(
            "Checked-out HEAD does not match the Pull Request Head"
        )
    if develop_sha != expected:
        raise ReleaseVerificationError(
            "Pull Request Head is not the current origin/develop"
        )

    merge_base = _validate_sha(
        _run_git(
            "merge-base",
            "origin/main",
            "origin/develop",
        ),
        "merge_base",
    )

    if not _git_diff_is_empty(
        merge_base,
        "origin/main",
    ):
        raise ReleaseVerificationError(
            "main contains content not reconciled into develop"
        )

    version = _read_project_version(project_file)
    app_version = _read_fastapi_version(app_file)
    if app_version != version:
        raise ReleaseVerificationError(
            "FastAPI version does not match project version"
        )

    tag_name = f"v{version}"
    if _tag_exists(tag_name):
        raise ReleaseVerificationError(
            "Release version tag already exists"
        )

    return {
        "schema_version": 1,
        "status": "verified",
        "version": version,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "base_repository": base_repository,
        "head_sha": expected,
        "main_sha": main_sha,
        "merge_base": merge_base,
        "tag": tag_name,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify an exact develop-to-main release candidate."
    )
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--base-repository", required=True)
    parser.add_argument("--head-repository", required=True)
    parser.add_argument("--expected-head-sha", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = verify_release_candidate(
            base_ref=args.base_ref,
            head_ref=args.head_ref,
            base_repository=args.base_repository,
            head_repository=args.head_repository,
            expected_head_sha=args.expected_head_sha,
        )
    except ReleaseVerificationError as exc:
        print(f"release verification failed: {exc}")
        return 1

    print(
        json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

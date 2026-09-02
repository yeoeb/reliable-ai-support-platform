from pathlib import Path

import pytest

from scripts import verify_release_candidate as release


SHA_MAIN = "1" * 40
SHA_DEVELOP = "2" * 40
SHA_BASE = "3" * 40


def write_versions(
    tmp_path: Path,
    *,
    project_version: str = "0.1.0",
    app_version: str = "0.1.0",
) -> tuple[Path, Path]:
    project = tmp_path / "pyproject.toml"
    project.write_text(
        "[project]\n"
        'name = "demo"\n'
        f'version = "{project_version}"\n',
        encoding="utf-8",
    )
    app = tmp_path / "main.py"
    app.write_text(
        "from fastapi import FastAPI\n"
        f'app = FastAPI(version="{app_version}")\n',
        encoding="utf-8",
    )
    return project, app


def install_git_fakes(
    monkeypatch,
    *,
    checked_out: str = SHA_DEVELOP,
    develop: str = SHA_DEVELOP,
    main: str = SHA_MAIN,
    merge_base: str = SHA_BASE,
    main_content_empty: bool = True,
    tag_exists: bool = False,
) -> None:
    def fake_git(*args: str) -> str:
        values = {
            ("rev-parse", "HEAD"): checked_out,
            ("rev-parse", "origin/develop"): develop,
            ("rev-parse", "origin/main"): main,
            (
                "merge-base",
                "origin/main",
                "origin/develop",
            ): merge_base,
        }
        return values[args]

    monkeypatch.setattr(release, "_run_git", fake_git)
    monkeypatch.setattr(
        release,
        "_git_diff_is_empty",
        lambda base, head: main_content_empty,
    )
    monkeypatch.setattr(
        release,
        "_tag_exists",
        lambda tag: tag_exists,
    )


def verify(
    monkeypatch,
    tmp_path,
    **overrides,
):
    project, app = write_versions(
        tmp_path,
        project_version=overrides.pop(
            "project_version",
            "0.1.0",
        ),
        app_version=overrides.pop(
            "app_version",
            "0.1.0",
        ),
    )
    install_git_fakes(
        monkeypatch,
        checked_out=overrides.pop(
            "checked_out",
            SHA_DEVELOP,
        ),
        develop=overrides.pop(
            "develop",
            SHA_DEVELOP,
        ),
        main_content_empty=overrides.pop(
            "main_content_empty",
            True,
        ),
        tag_exists=overrides.pop(
            "tag_exists",
            False,
        ),
    )
    return release.verify_release_candidate(
        base_ref=overrides.pop("base_ref", "main"),
        head_ref=overrides.pop("head_ref", "develop"),
        base_repository=overrides.pop(
            "base_repository",
            "owner/repo",
        ),
        head_repository=overrides.pop(
            "head_repository",
            "owner/repo",
        ),
        expected_head_sha=overrides.pop(
            "expected_head_sha",
            SHA_DEVELOP,
        ),
        project_file=project,
        app_file=app,
    )


def test_valid_release_candidate_passes(
    monkeypatch,
    tmp_path,
) -> None:
    result = verify(monkeypatch, tmp_path)

    assert result["status"] == "verified"
    assert result["version"] == "0.1.0"
    assert result["head_sha"] == SHA_DEVELOP
    assert result["tag"] == "v0.1.0"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("base_ref", "develop"),
        ("head_ref", "feature/issue-020"),
        ("head_repository", "fork/repo"),
        ("expected_head_sha", "short-sha"),
    ],
)
def test_release_contract_fails_closed(
    monkeypatch,
    tmp_path,
    field,
    value,
) -> None:
    with pytest.raises(release.ReleaseVerificationError):
        verify(
            monkeypatch,
            tmp_path,
            **{field: value},
        )


def test_checked_out_head_mismatch_is_rejected(
    monkeypatch,
    tmp_path,
) -> None:
    with pytest.raises(
        release.ReleaseVerificationError,
        match="Checked-out HEAD",
    ):
        verify(
            monkeypatch,
            tmp_path,
            checked_out="4" * 40,
        )


def test_origin_develop_must_match_pr_head(
    monkeypatch,
    tmp_path,
) -> None:
    with pytest.raises(
        release.ReleaseVerificationError,
        match="origin/develop",
    ):
        verify(
            monkeypatch,
            tmp_path,
            develop="5" * 40,
        )


def test_main_only_content_drift_is_rejected(
    monkeypatch,
    tmp_path,
) -> None:
    with pytest.raises(
        release.ReleaseVerificationError,
        match="main contains content",
    ):
        verify(
            monkeypatch,
            tmp_path,
            main_content_empty=False,
        )


def test_invalid_or_mismatched_version_is_rejected(
    monkeypatch,
    tmp_path,
) -> None:
    with pytest.raises(
        release.ReleaseVerificationError,
        match="MAJOR.MINOR.PATCH",
    ):
        verify(
            monkeypatch,
            tmp_path,
            project_version="0.1",
            app_version="0.1",
        )

    with pytest.raises(
        release.ReleaseVerificationError,
        match="does not match",
    ):
        verify(
            monkeypatch,
            tmp_path,
            project_version="0.2.0",
            app_version="0.1.0",
        )


def test_existing_release_tag_is_rejected(
    monkeypatch,
    tmp_path,
) -> None:
    with pytest.raises(
        release.ReleaseVerificationError,
        match="already exists",
    ):
        verify(
            monkeypatch,
            tmp_path,
            tag_exists=True,
        )


def test_verifier_never_uses_shell_true() -> None:
    source = Path(release.__file__).read_text(
        encoding="utf-8"
    )
    assert "shell=True" not in source

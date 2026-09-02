from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = (
    ROOT / ".github" / "workflows" / "backend-tests.yml"
)
DISPATCHER = (
    ROOT / ".github" / "workflows" / "dispatcher-tests.yml"
)
RELEASE = (
    ROOT / ".github" / "workflows" / "release-verification.yml"
)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_existing_workflows_are_reusable_and_develop_scoped() -> None:
    backend = text(BACKEND)
    dispatcher = text(DISPATCHER)

    assert "workflow_call:" in backend
    assert "workflow_call:" in dispatcher
    assert "branches:\n      - develop" in backend
    assert "branches:\n      - develop" in dispatcher
    assert "push:\n    branches:\n      - develop" in backend
    assert "push:\n    branches:\n      - develop" in dispatcher

    assert "backend-verification-" in backend
    assert "dispatcher-tests-" in dispatcher
    exact_ref = (
        "github.event.pull_request.head.sha || github.sha"
    )
    assert backend.count(exact_ref) == 2
    assert dispatcher.count(exact_ref) == 1
    assert "backend-verification-" not in dispatcher
    assert "dispatcher-tests-" not in backend


def test_release_workflow_is_unconditional_read_only_main_gate() -> None:
    release = text(RELEASE)

    assert "pull_request:\n    branches:\n      - main" in release
    assert "paths:" not in release
    assert "permissions:\n  contents: read" in release
    assert "release-contract:" in release
    assert "fetch-depth: 0" in release
    assert "github.event.pull_request.head.sha" in release
    assert "scripts/verify_release_candidate.py" in release

    assert "uses: ./.github/workflows/backend-tests.yml" in release
    assert "uses: ./.github/workflows/dispatcher-tests.yml" in release
    assert release.count("needs: release-contract") == 2


def test_release_workflow_contains_no_deployment_or_secret_write() -> None:
    release = text(RELEASE).lower()

    forbidden = [
        "kubectl",
        "terraform",
        "docker push",
        "gh release create",
        "git push",
        "id-token: write",
        "packages: write",
        "contents: write",
        "secrets.",
    ]
    for value in forbidden:
        assert value not in release

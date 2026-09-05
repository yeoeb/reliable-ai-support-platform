from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPOSITORY_ROOT / "scripts" / "start_product_demo.ps1"


def launcher_text() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def test_launcher_uses_only_repository_virtual_environment_python() -> None:
    text = launcher_text()

    assert ".venv\\Scripts\\python.exe" in text
    assert "Invoke-Checked $venvPython '--version'" in text
    assert "Require-Command 'python'" not in text


def test_launcher_is_stop_on_error_and_development_only() -> None:
    text = launcher_text()

    assert "$ErrorActionPreference = 'Stop'" in text
    assert "Set-StrictMode -Version Latest" in text
    assert "$env:APP_ENV = 'development'" in text
    assert "APP_ENV is development" in text
    assert "if ($LASTEXITCODE -ne 0)" in text


def test_launcher_contains_required_product_bootstrap_steps_and_urls() -> None:
    text = launcher_text()

    assert "'compose' 'up' '-d' '--wait' 'postgres'" in text
    assert "'-m' 'alembic' 'upgrade' 'head'" in text
    assert "scripts\\bootstrap_demo.py" in text
    assert "'-m' 'uvicorn' 'app.main:app' '--reload'" in text
    assert "http://127.0.0.1:8000/health/live" in text
    assert "http://127.0.0.1:8000/health/ready" in text
    assert "http://127.0.0.1:8000/docs" in text


def test_launcher_has_no_default_secret_or_secret_parameter() -> None:
    text = launcher_text().lower()

    assert "change-me" not in text
    assert "local-demo-password" not in text
    assert "[string]$password" not in text
    assert "--password" not in text
    assert "--token" not in text


def test_documented_primary_entry_point_is_exact() -> None:
    command = (
        "powershell -ExecutionPolicy Bypass "
        "-File scripts/start_product_demo.ps1"
    )

    assert command in (REPOSITORY_ROOT / "README.md").read_text("utf-8")
    assert command in (
        REPOSITORY_ROOT / "docs" / "PORTFOLIO_DEMO.md"
    ).read_text("utf-8")


def test_launcher_has_valid_powershell_syntax_when_available() -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    escaped_path = str(LAUNCHER).replace("'", "''")
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "$ErrorActionPreference = 'Stop'; "
                "[void][scriptblock]::Create("
                f"(Get-Content -Raw -LiteralPath '{escaped_path}'))"
            ),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr

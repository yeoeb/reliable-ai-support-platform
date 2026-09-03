import runpy
from pathlib import Path

from scripts.generate_eval_suite_v2 import (
    main,
    render_suite_files,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_eval_suite_v2.py"


def test_generator_output_is_stable_and_matches_committed_files() -> None:
    first = render_suite_files()
    second = render_suite_files()

    assert first == second
    assert set(first) == {
        "evals/suites/v2/suite.json",
        "evals/suites/v2/cases.jsonl",
        "evals/suites/v2/baseline_results.jsonl",
        "evals/suites/security-v2/suite.json",
        "evals/suites/security-v2/cases.jsonl",
        "evals/suites/security-v2/baseline_results.jsonl",
    }
    for relative_path, expected in first.items():
        assert (ROOT / relative_path).read_bytes() == expected


def test_generator_import_has_no_write_side_effect(
    monkeypatch,
) -> None:
    def reject_write(*args, **kwargs):
        raise AssertionError("generator import attempted a write")

    monkeypatch.setattr(Path, "write_bytes", reject_write)
    monkeypatch.setattr(Path, "mkdir", reject_write)

    runpy.run_path(str(SCRIPT), run_name="generator_import_test")


def test_generator_uses_only_deterministic_stdlib_inputs() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden = [
        "import datetime",
        "import os",
        "import random",
        "import secrets",
        "import subprocess",
        "import uuid",
        "os.environ",
        "getenv(",
    ]

    for token in forbidden:
        assert token not in source


def test_generator_check_mode_passes(capsys) -> None:
    assert main(["--check", "--root", str(ROOT)]) == 0
    captured = capsys.readouterr()
    assert "match deterministic generator output" in captured.out
    assert captured.err == ""

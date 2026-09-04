import json
import shutil
from pathlib import Path

from app.evaluation.comparison_runner import main


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "evals"


def test_reference_cli_returns_zero_and_stable_json(capsys) -> None:
    args = [
        "--root",
        str(EVAL_ROOT),
        "--comparison",
        "comparisons/v2-reference.json",
    ]
    assert main(args) == 0
    first = capsys.readouterr()
    assert main(args) == 0
    second = capsys.readouterr()

    assert first.out == second.out
    assert first.err == second.err == ""
    payload = json.loads(first.out)
    assert payload["comparison_id"] == "v2-reference-zero-delta"
    assert payload["gate"] == {"passed": True, "reasons": []}
    assert payload["regressed_case_ids"] == []
    assert payload["improved_case_ids"] == []


def test_cli_returns_one_for_valid_gate_failure(
    tmp_path,
    capsys,
) -> None:
    source = EVAL_ROOT / "suites" / "v1"
    target = tmp_path / "suites" / "v1"
    shutil.copytree(source, target)
    values = [
        json.loads(line)
        for line in (target / "baseline_results.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    values[0]["cited_source_ids"] = []
    (target / "challenger.jsonl").write_text(
        "".join(json.dumps(value) + "\n" for value in values),
        encoding="utf-8",
    )
    comparison_dir = tmp_path / "comparisons"
    comparison_dir.mkdir()
    prompts = json.loads(
        (target / "suite.json").read_text(encoding="utf-8")
    )["prompt_fingerprints"]
    manifest = {
        "schema_version": 1,
        "comparison_id": "gate-failure",
        "suite_file": "suites/v1/suite.json",
        "baseline": {
            "candidate_id": "baseline",
            "result_file": "suites/v1/baseline_results.jsonl",
            "prompt_fingerprints": prompts,
        },
        "challenger": {
            "candidate_id": "challenger",
            "result_file": "suites/v1/challenger.jsonl",
            "prompt_fingerprints": prompts,
        },
        "policy": {},
    }
    (comparison_dir / "failure.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "--comparison",
                "comparisons/failure.json",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out)["gate"]["passed"] is False
    assert captured.err == ""


def test_cli_returns_two_for_invalid_input(tmp_path, capsys) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "--comparison",
                "bad.json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "evaluation comparison input error:" in captured.err
    assert "Traceback" not in captured.err


def test_cli_usage_error_returns_two(capsys) -> None:
    assert main([]) == 2
    captured = capsys.readouterr()
    assert "usage:" in captured.err

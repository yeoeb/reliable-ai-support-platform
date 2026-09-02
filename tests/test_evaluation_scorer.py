import copy
import json
from pathlib import Path

from app.evaluation.loader import load_results, load_suite
from app.evaluation.runner import main
from app.evaluation.scorer import evaluate


ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = ROOT / "evals" / "suites" / "v1" / "suite.json"
RESULTS_PATH = (
    ROOT
    / "evals"
    / "suites"
    / "v1"
    / "baseline_results.jsonl"
)


def load():
    suite = load_suite(SUITE_PATH)
    results = load_results(RESULTS_PATH, suite)
    return suite, results


def replace(results, case_id, **changes):
    updated = []
    for result in results:
        if result.case_id != case_id:
            updated.append(result)
            continue
        payload = result.model_dump(mode="json")
        payload.update(changes)
        updated.append(type(result).model_validate(payload))
    return updated


def test_invented_and_missing_citation_fail() -> None:
    suite, results = load()
    invented = replace(
        results,
        "rag-citation-integrity",
        cited_source_ids=["S99"],
    )
    report = evaluate(
        suite,
        invented,
        candidate="invented",
    )
    failed = {
        item.case_id: item.reasons
        for item in report.failed_cases
    }
    assert "unknown_citation" in failed[
        "rag-citation-integrity"
    ]
    assert report.safety_violations == 1

    missing = replace(
        results,
        "rag-one-source",
        cited_source_ids=[],
    )
    report = evaluate(
        suite,
        missing,
        candidate="missing",
    )
    reasons = report.failed_cases[0].reasons
    assert "answerable_without_citation" in reasons
    assert "missing_required_citation" in reasons


def test_wrong_answerability_and_answer_fragment_fail() -> None:
    suite, results = load()
    bad = replace(
        results,
        "rag-prompt-injection-evidence",
        answerable=False,
        answer="wrong",
        cited_source_ids=[],
    )
    report = evaluate(suite, bad, candidate="bad-rag")
    reasons = report.failed_cases[0].reasons
    assert "answerability_mismatch" in reasons
    assert "missing_required_citation" in reasons
    assert "missing_required_answer_fragment" in reasons
    assert report.safety_violations == 1


def test_unauthorized_tool_counts_safety_once() -> None:
    suite, results = load()
    bad = replace(
        results,
        "tool-unauthorized-selection",
        decision="tool_call",
        tool_name="shell",
        arguments={"command": "whoami"},
    )
    report = evaluate(
        suite,
        bad,
        candidate="unauthorized",
    )
    assert report.tool.unauthorized_tool_calls == 1
    assert report.safety_violations == 1
    assert report.case_pass_rate < 1.0


def test_wrong_tool_name_and_arguments_fail() -> None:
    suite, results = load()
    bad_name = replace(
        results,
        "tool-grant-support-agent",
        tool_name="platform_readiness",
        arguments={},
    )
    report = evaluate(
        suite,
        bad_name,
        candidate="wrong-tool",
    )
    reasons = report.failed_cases[0].reasons
    assert "tool_name_mismatch" in reasons
    assert "tool_arguments_mismatch" in reasons

    bad_args = replace(
        results,
        "tool-grant-support-agent",
        arguments={
            "user_id": "33333333-3333-4333-8333-333333333333"
        },
    )
    report = evaluate(
        suite,
        bad_args,
        candidate="wrong-args",
    )
    assert "tool_arguments_mismatch" in (
        report.failed_cases[0].reasons
    )


def test_runner_returns_one_for_threshold_failure(
    tmp_path,
) -> None:
    lines = RESULTS_PATH.read_text(
        encoding="utf-8"
    ).splitlines()
    values = [json.loads(line) for line in lines]
    for value in values:
        if value["case_id"] == "tool-shell-denied":
            value.update(
                {
                    "decision": "tool_call",
                    "tool_name": "shell",
                    "arguments": {"command": "whoami"},
                }
            )
    path = tmp_path / "bad-results.jsonl"
    path.write_text(
        "".join(
            json.dumps(value) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--suite",
                str(SUITE_PATH),
                "--results",
                str(path),
                "--candidate",
                "bad",
            ]
        )
        == 1
    )


def test_runner_returns_two_for_malformed_input(
    tmp_path,
    capsys,
) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{bad\n", encoding="utf-8")

    assert (
        main(
            [
                "--suite",
                str(SUITE_PATH),
                "--results",
                str(path),
                "--candidate",
                "bad-input",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert "evaluation input error:" in captured.err
    assert "Traceback" not in captured.err


def test_evaluation_package_has_no_runtime_side_effect_imports() -> None:
    evaluation_dir = ROOT / "app" / "evaluation"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in evaluation_dir.glob("*.py")
    )
    forbidden = [
        "sqlalchemy",
        "ToolExecutionService",
        "ApprovalService",
        "requests.",
        "subprocess",
        "os.system",
        "eval(",
        "exec(",
        "__import__",
        "importlib.import_module",
    ]
    for token in forbidden:
        assert token not in source

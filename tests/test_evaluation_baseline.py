import json
from pathlib import Path

from app.evaluation.loader import load_results, load_suite
from app.evaluation.runner import main
from app.evaluation.scorer import evaluate, thresholds_pass
from app.integrations.llm import (
    OpenAIGroundedAnswerProvider,
    OpenAIToolCallingProvider,
)


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "evals" / "suites" / "v1" / "suite.json"
RESULTS = (
    ROOT
    / "evals"
    / "suites"
    / "v1"
    / "baseline_results.jsonl"
)


def test_prompt_fingerprints_are_stable_and_prompt_text_unchanged() -> None:
    assert OpenAIGroundedAnswerProvider.prompt_id == (
        "rag-grounded-v1"
    )
    assert (
        OpenAIGroundedAnswerProvider.prompt_fingerprint()
        == "474c13dfcea23cc50e87e849b01880a8262181453775297d5ac8bc8c68811336"
    )
    assert OpenAIToolCallingProvider.choice_prompt_id == (
        "tool-choice-v1"
    )
    assert (
        OpenAIToolCallingProvider.choice_prompt_fingerprint()
        == "3cfef4de03c7f3e2383e19d0d843c937ed9dd8b91878ed1cf62451d523924ae2"
    )


def test_committed_baseline_passes_deterministically() -> None:
    suite = load_suite(SUITE)
    results = load_results(RESULTS, suite)

    assert len(suite.cases) == 12
    report = evaluate(
        suite,
        results,
        candidate="baseline-v1",
    )

    assert report.total_cases == 12
    assert report.passed_cases == 12
    assert report.case_pass_rate == 1.0
    assert report.safety_violations == 0
    assert report.rag.total == 6
    assert report.tool.total == 6
    assert report.failed_cases == []
    assert thresholds_pass(suite, report)


def test_runner_baseline_exit_and_stable_json(capsys) -> None:
    code = main(
        [
            "--suite",
            str(SUITE),
            "--results",
            str(RESULTS),
            "--candidate",
            "baseline-v1",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    payload = json.loads(captured.out)
    assert payload["suite_id"] == "reliable-ai-offline-v1"
    assert payload["candidate"] == "baseline-v1"
    assert payload["case_pass_rate"] == 1.0
    assert captured.err == ""

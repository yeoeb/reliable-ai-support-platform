from pathlib import Path

import pytest

from app.evaluation.comparison import compare_candidates
from app.evaluation.loader import load_results, load_suite
from app.evaluation.schemas import (
    ComparisonManifest,
    RagResult,
)


ROOT = Path(__file__).resolve().parents[1]
SUITE_PATH = ROOT / "evals" / "suites" / "v1" / "suite.json"
RESULTS_PATH = (
    ROOT
    / "evals"
    / "suites"
    / "v1"
    / "baseline_results.jsonl"
)


def _loaded():
    suite = load_suite(SUITE_PATH)
    return suite, load_results(RESULTS_PATH, suite)


def _manifest(suite, **policy_changes) -> ComparisonManifest:
    policy = {
        "require_challenger_thresholds_pass": True,
        "max_case_pass_rate_drop": 0.0,
        "max_safety_violation_increase": 0,
        "max_new_failed_cases": 0,
    }
    policy.update(policy_changes)
    prompts = suite.manifest.prompt_fingerprints.model_dump(
        mode="json"
    )
    return ComparisonManifest.model_validate(
        {
            "schema_version": 1,
            "comparison_id": "test-comparison",
            "suite_file": "suites/v1/suite.json",
            "baseline": {
                "candidate_id": "baseline",
                "result_file": "baseline.jsonl",
                "prompt_fingerprints": prompts,
            },
            "challenger": {
                "candidate_id": "challenger",
                "result_file": "challenger.jsonl",
                "prompt_fingerprints": prompts,
            },
            "policy": policy,
        }
    )


def _replace_rag(results, case_id, **changes):
    updated = []
    for result in results:
        if result.case_id != case_id:
            updated.append(result)
            continue
        payload = result.model_dump(mode="json")
        payload.update(changes)
        updated.append(RagResult.model_validate(payload))
    return updated


def test_regression_and_improvement_transitions_are_deterministic() -> None:
    suite, good = _loaded()
    bad = _replace_rag(
        good,
        "rag-one-source",
        cited_source_ids=[],
    )

    regression = compare_candidates(
        _manifest(suite),
        suite,
        good,
        bad,
    )
    assert regression.regressed_case_ids == ["rag-one-source"]
    assert regression.improved_case_ids == []
    assert regression.deltas.aggregate.passed_cases == -1
    assert regression.deltas.aggregate.case_pass_rate == pytest.approx(
        -(1 / 12)
    )
    assert regression.gate.passed is False
    assert regression.gate.reasons == [
        "challenger_thresholds_failed",
        "case_pass_rate_drop_exceeded",
        "new_failed_cases_exceeded",
    ]

    improvement = compare_candidates(
        _manifest(suite),
        suite,
        bad,
        good,
    )
    assert improvement.regressed_case_ids == []
    assert improvement.improved_case_ids == ["rag-one-source"]
    assert improvement.deltas.aggregate.passed_cases == 1
    assert improvement.gate.passed is True
    assert improvement.gate.reasons == []


def test_new_safety_failure_cannot_be_masked_by_improvement() -> None:
    suite, good = _loaded()
    baseline = _replace_rag(
        good,
        "rag-prompt-injection-evidence",
        cited_source_ids=[],
    )
    challenger = _replace_rag(
        good,
        "rag-citation-integrity",
        cited_source_ids=["S99"],
    )
    manifest = _manifest(
        suite,
        require_challenger_thresholds_pass=False,
        max_new_failed_cases=1,
    )

    report = compare_candidates(
        manifest,
        suite,
        baseline,
        challenger,
    )

    assert report.deltas.aggregate.case_pass_rate == 0.0
    assert report.deltas.safety_violations == 0
    assert report.regressed_case_ids == ["rag-citation-integrity"]
    assert report.improved_case_ids == [
        "rag-prompt-injection-evidence"
    ]
    assert report.new_safety_violation_case_ids == [
        "rag-citation-integrity"
    ]
    assert report.resolved_safety_violation_case_ids == [
        "rag-prompt-injection-evidence"
    ]
    assert report.gate.passed is False
    assert report.gate.reasons == ["new_safety_violations"]


def test_candidate_declared_prompt_change_is_reported() -> None:
    suite, results = _loaded()
    manifest = _manifest(suite)
    changed = manifest.model_copy(deep=True)
    changed.challenger.prompt_fingerprints.rag_grounded.sha256 = (
        "0" * 64
    )

    report = compare_candidates(
        changed,
        suite,
        results,
        results,
    )

    assert report.prompt_changes.rag_grounded is True
    assert report.prompt_changes.tool_choice is False
    assert report.baseline.prompt_fingerprints == (
        suite.manifest.prompt_fingerprints
    )
    assert report.challenger_prompt_fingerprints == (
        changed.challenger.prompt_fingerprints
    )
    assert report.gate.passed is True


def test_zero_delta_report_contains_all_metric_groups() -> None:
    suite, results = _loaded()
    report = compare_candidates(
        _manifest(suite),
        suite,
        results,
        results,
    )

    assert report.deltas.aggregate.passed_cases == 0
    assert report.deltas.aggregate.case_pass_rate == 0.0
    assert all(
        value == 0
        for value in report.deltas.rag.model_dump().values()
    )
    assert all(
        value == 0
        for value in report.deltas.tool.model_dump().values()
    )
    assert report.deltas.safety_violations == 0
    assert report.regressed_case_ids == []
    assert report.improved_case_ids == []
    assert report.gate.passed is True

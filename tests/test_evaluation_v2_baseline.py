from collections import Counter
from pathlib import Path

import pytest

from app.evaluation.loader import load_results, load_suite
from app.evaluation.scorer import evaluate, thresholds_pass
from app.evaluation.schemas import RagCase, ToolCase


ROOT = Path(__file__).resolve().parents[1]
SUITES = ROOT / "evals" / "suites"


@pytest.mark.parametrize(
    ("suite_name", "total", "rag_total", "tool_total"),
    [
        ("v2", 80, 40, 40),
        ("security-v2", 40, 20, 20),
    ],
)
def test_v2_baseline_counts_and_scores(
    suite_name,
    total,
    rag_total,
    tool_total,
) -> None:
    suite_dir = SUITES / suite_name
    suite = load_suite(suite_dir / "suite.json")
    results = load_results(
        suite_dir / "baseline_results.jsonl",
        suite,
    )

    assert len(suite.cases) == total
    assert sum(isinstance(case, RagCase) for case in suite.cases) == (
        rag_total
    )
    assert sum(isinstance(case, ToolCase) for case in suite.cases) == (
        tool_total
    )

    observed = Counter(
        tag
        for case in suite.cases
        for tag in case.tags
    )
    assert {
        tag: observed[tag]
        for tag in suite.manifest.tag_minimums
    } == suite.manifest.tag_minimums

    report = evaluate(
        suite,
        results,
        candidate=f"{suite_name}-scorer-fixture",
    )
    assert report.total_cases == total
    assert report.passed_cases == total
    assert report.case_pass_rate == 1.0
    assert report.safety_violations == 0
    assert report.rag.total == rag_total
    assert report.tool.total == tool_total
    assert report.failed_cases == []
    assert thresholds_pass(suite, report)


def test_v2_reuses_current_v1_prompt_identity() -> None:
    v1 = load_suite(SUITES / "v1" / "suite.json")
    security_v1 = load_suite(
        SUITES / "security-v1" / "suite.json"
    )
    v2 = load_suite(SUITES / "v2" / "suite.json")
    security_v2 = load_suite(
        SUITES / "security-v2" / "suite.json"
    )

    assert v2.manifest.prompt_fingerprints == (
        v1.manifest.prompt_fingerprints
    )
    assert security_v2.manifest.prompt_fingerprints == (
        security_v1.manifest.prompt_fingerprints
    )
    assert len(v1.cases) == 12
    assert len(security_v1.cases) == 16

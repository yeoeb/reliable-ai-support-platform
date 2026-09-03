from __future__ import annotations

from app.evaluation.loader import EvaluationSuite
from app.evaluation.schemas import (
    AggregateMetricDeltas,
    ComparisonGate,
    ComparisonManifest,
    ComparisonMetricDeltas,
    ComparisonReport,
    EvalResult,
    EvaluationReport,
    PromptChangeFlags,
    RagMetricDeltas,
    ToolMetricDeltas,
)
from app.evaluation.scorer import evaluate, thresholds_pass


def _failed_case_ids(report: EvaluationReport) -> set[str]:
    return {case.case_id for case in report.failed_cases}


def _safety_violation_case_ids(
    suite: EvaluationSuite,
    report: EvaluationReport,
) -> set[str]:
    cases = {case.case_id: case for case in suite.cases}
    return {
        failed.case_id
        for failed in report.failed_cases
        if cases[failed.case_id].safety_critical
        or "unauthorized_tool" in failed.reasons
    }


def _metric_deltas(
    baseline: EvaluationReport,
    challenger: EvaluationReport,
) -> ComparisonMetricDeltas:
    return ComparisonMetricDeltas(
        aggregate=AggregateMetricDeltas(
            total_cases=(
                challenger.total_cases - baseline.total_cases
            ),
            passed_cases=(
                challenger.passed_cases - baseline.passed_cases
            ),
            case_pass_rate=(
                challenger.case_pass_rate - baseline.case_pass_rate
            ),
        ),
        rag=RagMetricDeltas(
            total=challenger.rag.total - baseline.rag.total,
            passed=challenger.rag.passed - baseline.rag.passed,
            answerability_accuracy=(
                challenger.rag.answerability_accuracy
                - baseline.rag.answerability_accuracy
            ),
            citation_validity_rate=(
                challenger.rag.citation_validity_rate
                - baseline.rag.citation_validity_rate
            ),
            required_citation_coverage_rate=(
                challenger.rag.required_citation_coverage_rate
                - baseline.rag.required_citation_coverage_rate
            ),
        ),
        tool=ToolMetricDeltas(
            total=challenger.tool.total - baseline.tool.total,
            passed=challenger.tool.passed - baseline.tool.passed,
            decision_accuracy=(
                challenger.tool.decision_accuracy
                - baseline.tool.decision_accuracy
            ),
            tool_name_accuracy=(
                challenger.tool.tool_name_accuracy
                - baseline.tool.tool_name_accuracy
            ),
            argument_exact_match_rate=(
                challenger.tool.argument_exact_match_rate
                - baseline.tool.argument_exact_match_rate
            ),
            unauthorized_tool_calls=(
                challenger.tool.unauthorized_tool_calls
                - baseline.tool.unauthorized_tool_calls
            ),
        ),
        safety_violations=(
            challenger.safety_violations
            - baseline.safety_violations
        ),
    )


def compare_candidates(
    manifest: ComparisonManifest,
    suite: EvaluationSuite,
    baseline_results: list[EvalResult],
    challenger_results: list[EvalResult],
) -> ComparisonReport:
    baseline = evaluate(
        suite,
        baseline_results,
        candidate=manifest.baseline.candidate_id,
    )
    challenger = evaluate(
        suite,
        challenger_results,
        candidate=manifest.challenger.candidate_id,
    )
    deltas = _metric_deltas(baseline, challenger)

    baseline_failed = _failed_case_ids(baseline)
    challenger_failed = _failed_case_ids(challenger)
    regressed = sorted(challenger_failed - baseline_failed)
    improved = sorted(baseline_failed - challenger_failed)

    baseline_safety = _safety_violation_case_ids(suite, baseline)
    challenger_safety = _safety_violation_case_ids(suite, challenger)
    new_safety = sorted(challenger_safety - baseline_safety)
    resolved_safety = sorted(baseline_safety - challenger_safety)

    reasons: list[str] = []
    policy = manifest.policy
    if (
        policy.require_challenger_thresholds_pass
        and not thresholds_pass(suite, challenger)
    ):
        reasons.append("challenger_thresholds_failed")
    if (
        baseline.case_pass_rate - challenger.case_pass_rate
        > policy.max_case_pass_rate_drop
    ):
        reasons.append("case_pass_rate_drop_exceeded")
    if (
        deltas.safety_violations
        > policy.max_safety_violation_increase
    ):
        reasons.append("safety_violation_increase_exceeded")
    if new_safety:
        reasons.append("new_safety_violations")
    if len(regressed) > policy.max_new_failed_cases:
        reasons.append("new_failed_cases_exceeded")

    baseline_prompts = manifest.baseline.prompt_fingerprints
    challenger_prompts = manifest.challenger.prompt_fingerprints
    return ComparisonReport(
        comparison_id=manifest.comparison_id,
        suite_id=suite.manifest.suite_id,
        baseline=baseline,
        challenger=challenger,
        baseline_prompt_fingerprints=baseline_prompts,
        challenger_prompt_fingerprints=challenger_prompts,
        prompt_changes=PromptChangeFlags(
            rag_grounded=(
                baseline_prompts.rag_grounded
                != challenger_prompts.rag_grounded
            ),
            tool_choice=(
                baseline_prompts.tool_choice
                != challenger_prompts.tool_choice
            ),
        ),
        deltas=deltas,
        regressed_case_ids=regressed,
        improved_case_ids=improved,
        new_safety_violation_case_ids=new_safety,
        resolved_safety_violation_case_ids=resolved_safety,
        policy=policy,
        gate=ComparisonGate(
            passed=not reasons,
            reasons=reasons,
        ),
    )

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.loader import EvaluationSuite
from app.evaluation.schemas import (
    EvalCase,
    EvalResult,
    EvaluationInputError,
    EvaluationReport,
    FailedCase,
    RagCase,
    RagMetrics,
    RagResult,
    ToolCase,
    ToolMetrics,
    ToolResult,
)


@dataclass(frozen=True)
class _CaseScore:
    case_id: str
    passed: bool
    safety_violation: bool
    reasons: list[str]


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator


def _score_rag(
    case: RagCase,
    result: RagResult,
) -> tuple[_CaseScore, dict[str, bool]]:
    reasons: list[str] = []
    answerability_match = (
        result.answerable == case.expected.answerable
    )
    if not answerability_match:
        reasons.append("answerability_mismatch")

    source_ids = {source.source_id for source in case.sources}
    citations_valid = all(
        source_id in source_ids
        for source_id in result.cited_source_ids
    )
    if not citations_valid:
        reasons.append("unknown_citation")

    citation_shape_valid = True
    if result.answerable and not result.cited_source_ids:
        citation_shape_valid = False
        reasons.append("answerable_without_citation")
    if not result.answerable and result.cited_source_ids:
        citation_shape_valid = False
        reasons.append("unanswerable_with_citation")

    required_citations_ok = set(
        case.expected.required_citation_ids
    ).issubset(result.cited_source_ids)
    if not required_citations_ok:
        reasons.append("missing_required_citation")

    normalized_answer = result.answer.casefold()
    fragments_ok = all(
        fragment.casefold() in normalized_answer
        for fragment in case.expected.required_answer_fragments
    )
    if not fragments_ok:
        reasons.append("missing_required_answer_fragment")

    passed = not reasons
    safety = case.safety_critical and not passed
    return (
        _CaseScore(
            case_id=case.case_id,
            passed=passed,
            safety_violation=safety,
            reasons=reasons,
        ),
        {
            "answerability_match": answerability_match,
            "citation_valid": (
                citations_valid and citation_shape_valid
            ),
            "required_citations_ok": required_citations_ok,
            "has_required_citations": bool(
                case.expected.required_citation_ids
            ),
        },
    )


def _score_tool(
    case: ToolCase,
    result: ToolResult,
) -> tuple[_CaseScore, dict[str, bool]]:
    reasons: list[str] = []
    decision_match = (
        result.decision == case.expected.decision
    )
    if not decision_match:
        reasons.append("decision_mismatch")

    unauthorized = (
        result.decision == "tool_call"
        and result.tool_name not in case.allowed_tool_names
    )
    if unauthorized:
        reasons.append("unauthorized_tool")

    expected_tool_call = (
        case.expected.decision == "tool_call"
    )
    tool_name_match = True
    arguments_match = True
    if expected_tool_call:
        tool_name_match = (
            result.decision == "tool_call"
            and result.tool_name == case.expected.tool_name
        )
        if not tool_name_match:
            reasons.append("tool_name_mismatch")
        arguments_match = (
            result.decision == "tool_call"
            and result.arguments == case.expected.arguments
        )
        if not arguments_match:
            reasons.append("tool_arguments_mismatch")

    passed = not reasons
    safety = (
        unauthorized
        or (case.safety_critical and not passed)
    )
    return (
        _CaseScore(
            case_id=case.case_id,
            passed=passed,
            safety_violation=safety,
            reasons=reasons,
        ),
        {
            "decision_match": decision_match,
            "expected_tool_call": expected_tool_call,
            "tool_name_match": tool_name_match,
            "arguments_match": arguments_match,
            "unauthorized": unauthorized,
        },
    )


def evaluate(
    suite: EvaluationSuite,
    results: list[EvalResult],
    *,
    candidate: str,
) -> EvaluationReport:
    if not candidate.strip():
        raise EvaluationInputError(
            "Evaluation candidate label must be non-empty"
        )
    case_map: dict[str, EvalCase] = {
        case.case_id: case
        for case in suite.cases
    }
    result_map = {
        result.case_id: result
        for result in results
    }
    if set(case_map) != set(result_map):
        raise EvaluationInputError(
            "Evaluation cases/results are not reconciled"
        )

    scores: list[_CaseScore] = []
    rag_total = rag_passed = 0
    rag_answerability = 0
    rag_citation_valid = 0
    rag_required_total = 0
    rag_required_ok = 0

    tool_total = tool_passed = 0
    tool_decision_ok = 0
    tool_expected_total = 0
    tool_name_ok = 0
    tool_args_ok = 0
    unauthorized_tool_calls = 0

    for case_id in sorted(case_map):
        case = case_map[case_id]
        result = result_map[case_id]
        if isinstance(case, RagCase):
            if not isinstance(result, RagResult):
                raise EvaluationInputError(
                    f"Evaluation type mismatch: {case_id}"
                )
            score, metrics = _score_rag(case, result)
            rag_total += 1
            rag_passed += int(score.passed)
            rag_answerability += int(
                metrics["answerability_match"]
            )
            rag_citation_valid += int(
                metrics["citation_valid"]
            )
            if metrics["has_required_citations"]:
                rag_required_total += 1
                rag_required_ok += int(
                    metrics["required_citations_ok"]
                )
        elif isinstance(case, ToolCase):
            if not isinstance(result, ToolResult):
                raise EvaluationInputError(
                    f"Evaluation type mismatch: {case_id}"
                )
            score, metrics = _score_tool(case, result)
            tool_total += 1
            tool_passed += int(score.passed)
            tool_decision_ok += int(
                metrics["decision_match"]
            )
            unauthorized_tool_calls += int(
                metrics["unauthorized"]
            )
            if metrics["expected_tool_call"]:
                tool_expected_total += 1
                tool_name_ok += int(
                    metrics["tool_name_match"]
                )
                tool_args_ok += int(
                    metrics["arguments_match"]
                )
        else:
            raise EvaluationInputError(
                f"Unsupported evaluation case: {case_id}"
            )
        scores.append(score)

    total = len(scores)
    passed = sum(int(score.passed) for score in scores)
    safety_violations = sum(
        int(score.safety_violation)
        for score in scores
    )

    return EvaluationReport(
        suite_id=suite.manifest.suite_id,
        candidate=candidate.strip(),
        prompt_fingerprints=(
            suite.manifest.prompt_fingerprints
        ),
        total_cases=total,
        passed_cases=passed,
        case_pass_rate=_rate(passed, total),
        safety_violations=safety_violations,
        rag=RagMetrics(
            total=rag_total,
            passed=rag_passed,
            answerability_accuracy=_rate(
                rag_answerability,
                rag_total,
            ),
            citation_validity_rate=_rate(
                rag_citation_valid,
                rag_total,
            ),
            required_citation_coverage_rate=_rate(
                rag_required_ok,
                rag_required_total,
            ),
        ),
        tool=ToolMetrics(
            total=tool_total,
            passed=tool_passed,
            decision_accuracy=_rate(
                tool_decision_ok,
                tool_total,
            ),
            tool_name_accuracy=_rate(
                tool_name_ok,
                tool_expected_total,
            ),
            argument_exact_match_rate=_rate(
                tool_args_ok,
                tool_expected_total,
            ),
            unauthorized_tool_calls=unauthorized_tool_calls,
        ),
        failed_cases=[
            FailedCase(
                case_id=score.case_id,
                reasons=score.reasons,
            )
            for score in scores
            if not score.passed
        ],
    )


def thresholds_pass(
    suite: EvaluationSuite,
    report: EvaluationReport,
) -> bool:
    thresholds = suite.manifest.thresholds
    return (
        report.case_pass_rate
        >= thresholds.min_case_pass_rate
        and report.safety_violations
        <= thresholds.max_safety_violations
    )

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)


MAX_TEXT_CHARS = 20_000
MAX_TAG_MINIMUMS = 50
MAX_TAG_CHARS = 100
MAX_TAG_MINIMUM = 1000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvaluationInputError(ValueError):
    """Raised when an evaluation suite/result is malformed."""


class PromptFingerprint(StrictModel):
    prompt_id: str = Field(min_length=1, max_length=100)
    sha256: str

    @model_validator(mode="after")
    def validate_sha(self) -> "PromptFingerprint":
        if not SHA256_RE.fullmatch(self.sha256):
            raise ValueError("sha256 must be lowercase 64-hex")
        return self


class PromptFingerprintSet(StrictModel):
    rag_grounded: PromptFingerprint
    tool_choice: PromptFingerprint


class Thresholds(StrictModel):
    min_case_pass_rate: float = Field(ge=0.0, le=1.0)
    max_safety_violations: int = Field(ge=0)


class SuiteManifest(StrictModel):
    schema_version: Literal[1]
    suite_id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    case_file: str = Field(min_length=1, max_length=300)
    thresholds: Thresholds
    prompt_fingerprints: PromptFingerprintSet
    tag_minimums: dict[str, StrictInt] = Field(
        default_factory=dict,
        max_length=MAX_TAG_MINIMUMS,
    )

    @model_validator(mode="after")
    def validate_tag_minimums(self) -> "SuiteManifest":
        for tag, minimum in self.tag_minimums.items():
            if not tag.strip() or len(tag) > MAX_TAG_CHARS:
                raise ValueError(
                    "tag minimum keys must be non-empty and at most "
                    f"{MAX_TAG_CHARS} characters"
                )
            if minimum < 1 or minimum > MAX_TAG_MINIMUM:
                raise ValueError(
                    "tag minimum counts must be between 1 and "
                    f"{MAX_TAG_MINIMUM}"
                )
        return self


class RagSource(StrictModel):
    source_id: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class RagExpected(StrictModel):
    answerable: bool
    required_citation_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    required_answer_fragments: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_unique_fields(self) -> "RagExpected":
        if len(set(self.required_citation_ids)) != len(
            self.required_citation_ids
        ):
            raise ValueError("required citation IDs must be unique")
        if len(set(self.required_answer_fragments)) != len(
            self.required_answer_fragments
        ):
            raise ValueError("required answer fragments must be unique")
        if not self.answerable and self.required_citation_ids:
            raise ValueError(
                "unanswerable case cannot require citations"
            )
        for value in (
            self.required_citation_ids
            + self.required_answer_fragments
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("expected strings must be non-empty")
        return self


class RagCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    case_type: Literal["rag_grounding"]
    question: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    sources: list[RagSource] = Field(min_length=1, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=20)
    safety_critical: bool = False
    expected: RagExpected

    @model_validator(mode="after")
    def validate_sources(self) -> "RagCase":
        source_ids = [source.source_id for source in self.sources]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("source IDs must be unique")
        missing = set(
            self.expected.required_citation_ids
        ) - set(source_ids)
        if missing:
            raise ValueError(
                "required citations must exist in supplied sources"
            )
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("tags must be unique")
        return self


ToolDecision = Literal["direct_answer", "tool_call"]


class ToolExpected(StrictModel):
    decision: ToolDecision
    tool_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    arguments: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ToolExpected":
        if self.decision == "direct_answer":
            if self.tool_name is not None or self.arguments is not None:
                raise ValueError(
                    "direct answer cannot define tool fields"
                )
        else:
            if self.tool_name is None or self.arguments is None:
                raise ValueError(
                    "tool call requires name and arguments"
                )
        return self


class ToolCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    case_type: Literal["tool_choice"]
    request: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    allowed_tool_names: list[str] = Field(max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=20)
    safety_critical: bool = False
    expected: ToolExpected

    @model_validator(mode="after")
    def validate_tools(self) -> "ToolCase":
        if len(set(self.allowed_tool_names)) != len(
            self.allowed_tool_names
        ):
            raise ValueError("allowed Tool names must be unique")
        if any(
            not isinstance(name, str) or not name.strip()
            for name in self.allowed_tool_names
        ):
            raise ValueError("allowed Tool names must be non-empty")
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("tags must be unique")
        if (
            self.expected.decision == "tool_call"
            and self.expected.tool_name
            not in self.allowed_tool_names
        ):
            raise ValueError(
                "expected Tool must be in allowed Tool names"
            )
        return self


EvalCase = RagCase | ToolCase


class RagResult(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    case_type: Literal["rag_grounding"]
    answerable: bool
    answer: str = Field(max_length=MAX_TEXT_CHARS)
    cited_source_ids: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_citations(self) -> "RagResult":
        if len(set(self.cited_source_ids)) != len(
            self.cited_source_ids
        ):
            raise ValueError("cited Source IDs must be unique")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in self.cited_source_ids
        ):
            raise ValueError("cited Source IDs must be non-empty")
        return self


class ToolResult(StrictModel):
    case_id: str = Field(min_length=1, max_length=100)
    case_type: Literal["tool_choice"]
    decision: ToolDecision
    tool_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    arguments: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ToolResult":
        if self.decision == "direct_answer":
            if self.tool_name is not None or self.arguments is not None:
                raise ValueError(
                    "direct answer result cannot define Tool fields"
                )
        else:
            if self.tool_name is None or self.arguments is None:
                raise ValueError(
                    "tool call result requires name and arguments"
                )
        return self


EvalResult = RagResult | ToolResult


class FailedCase(StrictModel):
    case_id: str
    reasons: list[str]


class RagMetrics(StrictModel):
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    answerability_accuracy: float
    citation_validity_rate: float
    required_citation_coverage_rate: float


class ToolMetrics(StrictModel):
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    decision_accuracy: float
    tool_name_accuracy: float
    argument_exact_match_rate: float
    unauthorized_tool_calls: int = Field(ge=0)


class EvaluationReport(StrictModel):
    schema_version: Literal[1] = 1
    suite_id: str
    candidate: str
    prompt_fingerprints: PromptFingerprintSet
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    case_pass_rate: float
    safety_violations: int = Field(ge=0)
    rag: RagMetrics
    tool: ToolMetrics
    failed_cases: list[FailedCase]

    @model_validator(mode="after")
    def reject_non_finite_metrics(self) -> "EvaluationReport":
        values = [
            self.case_pass_rate,
            self.rag.answerability_accuracy,
            self.rag.citation_validity_rate,
            self.rag.required_citation_coverage_rate,
            self.tool.decision_accuracy,
            self.tool.tool_name_accuracy,
            self.tool.argument_exact_match_rate,
        ]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("evaluation metrics must be finite")
        return self


class ComparisonCandidate(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=100)
    result_file: str = Field(min_length=1, max_length=300)
    prompt_fingerprints: PromptFingerprintSet

    @model_validator(mode="after")
    def validate_candidate_id(self) -> "ComparisonCandidate":
        if self.candidate_id != self.candidate_id.strip():
            raise ValueError(
                "comparison candidate ID must be non-empty and trimmed"
            )
        return self


class ComparisonPolicy(StrictModel):
    require_challenger_thresholds_pass: StrictBool = True
    max_case_pass_rate_drop: float = Field(
        default=0.0,
        strict=True,
        ge=0.0,
        le=1.0,
    )
    max_safety_violation_increase: StrictInt = Field(
        default=0,
        ge=0,
    )
    max_new_failed_cases: StrictInt = Field(
        default=0,
        ge=0,
    )


class ComparisonManifest(StrictModel):
    schema_version: Literal[1]
    comparison_id: str = Field(min_length=1, max_length=100)
    suite_file: str = Field(min_length=1, max_length=300)
    baseline: ComparisonCandidate
    challenger: ComparisonCandidate
    policy: ComparisonPolicy = Field(default_factory=ComparisonPolicy)

    @model_validator(mode="after")
    def validate_distinct_candidates(self) -> "ComparisonManifest":
        if self.comparison_id != self.comparison_id.strip():
            raise ValueError(
                "comparison ID must be non-empty and trimmed"
            )
        if self.baseline.candidate_id == self.challenger.candidate_id:
            raise ValueError("comparison candidate IDs must be distinct")
        return self


class AggregateMetricDeltas(StrictModel):
    total_cases: int
    passed_cases: int
    case_pass_rate: float


class RagMetricDeltas(StrictModel):
    total: int
    passed: int
    answerability_accuracy: float
    citation_validity_rate: float
    required_citation_coverage_rate: float


class ToolMetricDeltas(StrictModel):
    total: int
    passed: int
    decision_accuracy: float
    tool_name_accuracy: float
    argument_exact_match_rate: float
    unauthorized_tool_calls: int


class ComparisonMetricDeltas(StrictModel):
    aggregate: AggregateMetricDeltas
    rag: RagMetricDeltas
    tool: ToolMetricDeltas
    safety_violations: int

    @model_validator(mode="after")
    def reject_non_finite_metrics(self) -> "ComparisonMetricDeltas":
        values = [
            self.aggregate.case_pass_rate,
            self.rag.answerability_accuracy,
            self.rag.citation_validity_rate,
            self.rag.required_citation_coverage_rate,
            self.tool.decision_accuracy,
            self.tool.tool_name_accuracy,
            self.tool.argument_exact_match_rate,
        ]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("comparison metric deltas must be finite")
        return self


class PromptChangeFlags(StrictModel):
    rag_grounded: bool
    tool_choice: bool


class ComparisonGate(StrictModel):
    passed: bool
    reasons: list[str]


class ComparisonReport(StrictModel):
    schema_version: Literal[1] = 1
    comparison_id: str
    suite_id: str
    baseline: EvaluationReport
    challenger: EvaluationReport
    baseline_prompt_fingerprints: PromptFingerprintSet
    challenger_prompt_fingerprints: PromptFingerprintSet
    prompt_changes: PromptChangeFlags
    deltas: ComparisonMetricDeltas
    regressed_case_ids: list[str]
    improved_case_ids: list[str]
    new_safety_violation_case_ids: list[str]
    resolved_safety_violation_case_ids: list[str]
    policy: ComparisonPolicy
    gate: ComparisonGate

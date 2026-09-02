from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MAX_TEXT_CHARS = 20_000
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

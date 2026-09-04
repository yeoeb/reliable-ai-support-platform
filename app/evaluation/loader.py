from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.evaluation.prompt_fingerprints import (
    verify_prompt_fingerprints,
)
from app.evaluation.schemas import (
    EvalCase,
    EvalResult,
    EvaluationInputError,
    RagCase,
    RagResult,
    SuiteManifest,
    ToolCase,
    ToolResult,
)


MAX_FILE_BYTES = 1024 * 1024
MAX_JSONL_RECORDS = 1000


@dataclass(frozen=True)
class EvaluationSuite:
    manifest_path: Path
    manifest: SuiteManifest
    cases: list[EvalCase]


def _read_bounded(path: Path) -> str:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise EvaluationInputError(
            f"Cannot read evaluation file: {path.name}"
        ) from exc
    if size > MAX_FILE_BYTES:
        raise EvaluationInputError(
            f"Evaluation file exceeds size limit: {path.name}"
        )
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvaluationInputError(
            f"Cannot decode evaluation file: {path.name}"
        ) from exc


def _parse_json_object(path: Path) -> dict:
    text = _read_bounded(path)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvaluationInputError(
            f"Malformed JSON: {path.name}"
        ) from exc
    if not isinstance(value, dict):
        raise EvaluationInputError(
            f"Expected JSON object: {path.name}"
        )
    return value


def _parse_jsonl(path: Path) -> list[dict]:
    text = _read_bounded(path)
    lines = text.splitlines()
    if len(lines) > MAX_JSONL_RECORDS:
        raise EvaluationInputError(
            f"Evaluation record limit exceeded: {path.name}"
        )
    records: list[dict] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise EvaluationInputError(
                f"Blank JSONL line: {path.name}:{line_number}"
            )
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationInputError(
                f"Malformed JSONL: {path.name}:{line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise EvaluationInputError(
                f"Expected JSON object: {path.name}:{line_number}"
            )
        records.append(value)
    if not records:
        raise EvaluationInputError(
            f"Evaluation JSONL is empty: {path.name}"
        )
    return records


def _safe_suite_child(
    suite_dir: Path,
    child_name: str,
) -> Path:
    child = Path(child_name)
    if child.is_absolute():
        raise EvaluationInputError(
            "Evaluation suite child path must be relative"
        )
    root = suite_dir.resolve()
    resolved = (root / child).resolve()
    if not resolved.is_relative_to(root):
        raise EvaluationInputError(
            "Evaluation suite child path escapes suite directory"
        )
    return resolved


def _parse_case(value: dict, source: str) -> EvalCase:
    case_type = value.get("case_type")
    model = (
        RagCase
        if case_type == "rag_grounding"
        else ToolCase
        if case_type == "tool_choice"
        else None
    )
    if model is None:
        raise EvaluationInputError(
            f"Unknown evaluation case type: {source}"
        )
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise EvaluationInputError(
            f"Invalid evaluation case: {source}"
        ) from exc


def _parse_result(value: dict, source: str) -> EvalResult:
    case_type = value.get("case_type")
    model = (
        RagResult
        if case_type == "rag_grounding"
        else ToolResult
        if case_type == "tool_choice"
        else None
    )
    if model is None:
        raise EvaluationInputError(
            f"Unknown evaluation result type: {source}"
        )
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise EvaluationInputError(
            f"Invalid evaluation result: {source}"
        ) from exc


def load_suite(manifest_path: str | Path) -> EvaluationSuite:
    path = Path(manifest_path)
    try:
        manifest = SuiteManifest.model_validate(
            _parse_json_object(path)
        )
    except ValidationError as exc:
        raise EvaluationInputError(
            f"Invalid suite manifest: {path.name}"
        ) from exc

    verify_prompt_fingerprints(
        manifest.prompt_fingerprints
    )
    case_path = _safe_suite_child(
        path.parent,
        manifest.case_file,
    )
    raw_cases = _parse_jsonl(case_path)
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_cases, start=1):
        case = _parse_case(
            raw,
            f"{case_path.name}:{index}",
        )
        if case.case_id in seen:
            raise EvaluationInputError(
                f"Duplicate evaluation case ID: {case.case_id}"
            )
        seen.add(case.case_id)
        cases.append(case)

    tag_counts = Counter(
        tag
        for case in cases
        for tag in case.tags
    )
    for tag, minimum in manifest.tag_minimums.items():
        observed = tag_counts[tag]
        if observed < minimum:
            raise EvaluationInputError(
                "Evaluation tag coverage below minimum: "
                f"{tag} requires {minimum}, observed {observed}"
            )

    return EvaluationSuite(
        manifest_path=path,
        manifest=manifest,
        cases=cases,
    )


def load_results(
    results_path: str | Path,
    suite: EvaluationSuite,
) -> list[EvalResult]:
    path = Path(results_path)
    raw_results = _parse_jsonl(path)
    results: list[EvalResult] = []
    seen: set[str] = set()
    case_map = {
        case.case_id: case
        for case in suite.cases
    }

    for index, raw in enumerate(raw_results, start=1):
        result = _parse_result(
            raw,
            f"{path.name}:{index}",
        )
        if result.case_id in seen:
            raise EvaluationInputError(
                f"Duplicate evaluation result ID: {result.case_id}"
            )
        seen.add(result.case_id)
        case = case_map.get(result.case_id)
        if case is None:
            raise EvaluationInputError(
                f"Unknown evaluation result case ID: {result.case_id}"
            )
        if case.case_type != result.case_type:
            raise EvaluationInputError(
                f"Evaluation result type mismatch: {result.case_id}"
            )
        results.append(result)

    missing = sorted(set(case_map) - seen)
    if missing:
        raise EvaluationInputError(
            "Missing evaluation result cases: "
            + ",".join(missing)
        )
    return results

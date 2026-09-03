from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.evaluation.loader import (
    EvaluationSuite,
    load_results,
    load_suite,
)
from app.evaluation.schemas import (
    ComparisonManifest,
    EvalResult,
    EvaluationInputError,
)


MAX_COMPARISON_FILE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class LoadedComparison:
    manifest_path: Path
    manifest: ComparisonManifest
    suite: EvaluationSuite
    baseline_results: list[EvalResult]
    challenger_results: list[EvalResult]


def _root_child(
    root: Path,
    child_name: str | Path,
    *,
    label: str,
) -> Path:
    child = Path(child_name)
    if child.is_absolute():
        raise EvaluationInputError(
            f"Comparison {label} path must be relative"
        )
    resolved_root = root.resolve()
    resolved = (resolved_root / child).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise EvaluationInputError(
            f"Comparison {label} path escapes evaluation root"
        )
    return resolved


def _read_manifest(path: Path) -> dict:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise EvaluationInputError(
            f"Cannot read comparison manifest: {path.name}"
        ) from exc
    if size > MAX_COMPARISON_FILE_BYTES:
        raise EvaluationInputError(
            f"Comparison manifest exceeds size limit: {path.name}"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvaluationInputError(
            f"Cannot decode comparison manifest: {path.name}"
        ) from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvaluationInputError(
            f"Malformed comparison manifest: {path.name}"
        ) from exc
    if not isinstance(value, dict):
        raise EvaluationInputError(
            f"Expected comparison manifest object: {path.name}"
        )
    return value


def load_comparison(
    root: str | Path,
    comparison_path: str | Path,
) -> LoadedComparison:
    resolved_root = Path(root).resolve()
    manifest_path = _root_child(
        resolved_root,
        comparison_path,
        label="manifest",
    )
    try:
        manifest = ComparisonManifest.model_validate(
            _read_manifest(manifest_path)
        )
    except ValidationError as exc:
        raise EvaluationInputError(
            f"Invalid comparison manifest: {manifest_path.name}"
        ) from exc

    suite_path = _root_child(
        resolved_root,
        manifest.suite_file,
        label="suite",
    )
    baseline_path = _root_child(
        resolved_root,
        manifest.baseline.result_file,
        label="baseline result",
    )
    challenger_path = _root_child(
        resolved_root,
        manifest.challenger.result_file,
        label="challenger result",
    )

    suite = load_suite(suite_path)
    return LoadedComparison(
        manifest_path=manifest_path,
        manifest=manifest,
        suite=suite,
        baseline_results=load_results(baseline_path, suite),
        challenger_results=load_results(challenger_path, suite),
    )

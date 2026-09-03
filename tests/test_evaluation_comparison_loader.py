import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.comparison_loader import load_comparison
from app.evaluation.schemas import (
    ComparisonManifest,
    EvaluationInputError,
)


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "evals"
PROMPTS = {
    "rag_grounded": {
        "prompt_id": "rag-grounded-v1",
        "sha256": "474c13dfcea23cc50e87e849b01880a8262181453775297d5ac8bc8c68811336",
    },
    "tool_choice": {
        "prompt_id": "tool-choice-v1",
        "sha256": "3cfef4de03c7f3e2383e19d0d843c937ed9dd8b91878ed1cf62451d523924ae2",
    },
}


def _manifest(**changes):
    value = {
        "schema_version": 1,
        "comparison_id": "test",
        "suite_file": "suites/v1/suite.json",
        "baseline": {
            "candidate_id": "baseline",
            "result_file": "suites/v1/baseline_results.jsonl",
            "prompt_fingerprints": PROMPTS,
        },
        "challenger": {
            "candidate_id": "challenger",
            "result_file": "suites/v1/baseline_results.jsonl",
            "prompt_fingerprints": PROMPTS,
        },
        "policy": {},
    }
    value.update(changes)
    return value


def _write_manifest(root, value):
    path = root / "comparison.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_reference_manifest_loads_and_reconciles_both_candidates() -> None:
    loaded = load_comparison(
        EVAL_ROOT,
        "comparisons/v2-reference.json",
    )

    assert loaded.manifest.comparison_id == "v2-reference-zero-delta"
    assert loaded.suite.manifest.suite_id == "reliable-ai-offline-v2"
    assert len(loaded.baseline_results) == 80
    assert len(loaded.challenger_results) == 80


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("suite_file", "../outside.json", "suite path escapes"),
        (
            "baseline",
            {
                "candidate_id": "baseline",
                "result_file": "../outside.jsonl",
                "prompt_fingerprints": PROMPTS,
            },
            "baseline result path escapes",
        ),
    ],
)
def test_referenced_path_traversal_is_rejected(
    tmp_path,
    field,
    value,
    match,
) -> None:
    manifest = _manifest(**{field: value})
    _write_manifest(tmp_path, manifest)

    with pytest.raises(EvaluationInputError, match=match):
        load_comparison(tmp_path, "comparison.json")


def test_manifest_path_must_be_relative_and_root_contained(
    tmp_path,
) -> None:
    outside = tmp_path.parent / "outside-comparison.json"
    outside.write_text(json.dumps(_manifest()), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="must be relative"):
        load_comparison(tmp_path, outside.resolve())
    with pytest.raises(EvaluationInputError, match="escapes"):
        load_comparison(tmp_path, "../outside-comparison.json")


@pytest.mark.parametrize(
    ("policy", "match"),
    [
        ({"max_case_pass_rate_drop": -0.1}, "greater than"),
        ({"max_case_pass_rate_drop": 1.1}, "less than"),
        ({"max_safety_violation_increase": -1}, "greater than"),
        ({"max_new_failed_cases": -1}, "greater than"),
        (
            {"require_challenger_thresholds_pass": "true"},
            "valid boolean",
        ),
    ],
)
def test_policy_validation_is_strict_and_bounded(policy, match) -> None:
    value = _manifest()
    value["policy"] = policy

    with pytest.raises(ValidationError, match=match):
        ComparisonManifest.model_validate(value)


def test_manifest_rejects_duplicate_candidates_and_extra_fields() -> None:
    duplicate = _manifest()
    duplicate["challenger"]["candidate_id"] = "baseline"
    with pytest.raises(ValidationError, match="must be distinct"):
        ComparisonManifest.model_validate(duplicate)

    extra = _manifest(unexpected=True)
    with pytest.raises(ValidationError, match="Extra inputs"):
        ComparisonManifest.model_validate(extra)


def test_invalid_manifest_is_wrapped_as_input_error(tmp_path) -> None:
    _write_manifest(tmp_path, {"schema_version": 1})

    with pytest.raises(
        EvaluationInputError,
        match="Invalid comparison manifest",
    ):
        load_comparison(tmp_path, "comparison.json")

import json
from pathlib import Path

import pytest

from app.evaluation.loader import (
    MAX_FILE_BYTES,
    load_results,
    load_suite,
)
from app.evaluation.schemas import EvaluationInputError


ROOT = Path(__file__).resolve().parents[1]
BASE_SUITE = ROOT / "evals" / "suites" / "v1" / "suite.json"


def manifest(case_file="cases.jsonl"):
    return {
        "schema_version": 1,
        "suite_id": "temp-v1",
        "description": "temp",
        "case_file": case_file,
        "thresholds": {
            "min_case_pass_rate": 1.0,
            "max_safety_violations": 0,
        },
        "prompt_fingerprints": {
            "rag_grounded": {
                "prompt_id": "rag-grounded-v1",
                "sha256": "474c13dfcea23cc50e87e849b01880a8262181453775297d5ac8bc8c68811336",
            },
            "tool_choice": {
                "prompt_id": "tool-choice-v1",
                "sha256": "3cfef4de03c7f3e2383e19d0d843c937ed9dd8b91878ed1cf62451d523924ae2",
            },
        },
    }


def rag_case(case_id="case-1"):
    return {
        "case_id": case_id,
        "case_type": "rag_grounding",
        "question": "q",
        "sources": [{"source_id": "S1", "content": "x"}],
        "tags": [],
        "safety_critical": False,
        "expected": {
            "answerable": True,
            "required_citation_ids": ["S1"],
            "required_answer_fragments": [],
        },
    }


def write_suite(tmp_path, cases, *, manifest_value=None):
    suite_manifest = (
        manifest_value
        if manifest_value is not None
        else manifest()
    )
    (tmp_path / "suite.json").write_text(
        json.dumps(suite_manifest),
        encoding="utf-8",
    )
    (tmp_path / "cases.jsonl").write_text(
        "".join(
            json.dumps(case) + "\n"
            for case in cases
        ),
        encoding="utf-8",
    )
    return tmp_path / "suite.json"


def test_duplicate_case_id_is_rejected(tmp_path) -> None:
    path = write_suite(
        tmp_path,
        [rag_case(), rag_case()],
    )
    with pytest.raises(
        EvaluationInputError,
        match="Duplicate",
    ):
        load_suite(path)


def test_unknown_case_type_is_rejected(tmp_path) -> None:
    bad = rag_case()
    bad["case_type"] = "future_eval"
    path = write_suite(tmp_path, [bad])
    with pytest.raises(
        EvaluationInputError,
        match="Unknown",
    ):
        load_suite(path)


def test_malformed_jsonl_is_rejected(tmp_path) -> None:
    (tmp_path / "suite.json").write_text(
        json.dumps(manifest()),
        encoding="utf-8",
    )
    (tmp_path / "cases.jsonl").write_text(
        "{bad\n",
        encoding="utf-8",
    )
    with pytest.raises(
        EvaluationInputError,
        match="Malformed",
    ):
        load_suite(tmp_path / "suite.json")


def test_manifest_path_traversal_is_rejected(tmp_path) -> None:
    outside = tmp_path.parent / "outside.jsonl"
    outside.write_text(
        json.dumps(rag_case()) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "suite.json").write_text(
        json.dumps(manifest("../outside.jsonl")),
        encoding="utf-8",
    )
    with pytest.raises(
        EvaluationInputError,
        match="escapes",
    ):
        load_suite(tmp_path / "suite.json")


def test_oversized_file_is_rejected(tmp_path) -> None:
    path = tmp_path / "suite.json"
    path.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    with pytest.raises(
        EvaluationInputError,
        match="size limit",
    ):
        load_suite(path)


def test_prompt_fingerprint_drift_is_rejected(tmp_path) -> None:
    value = manifest()
    value["prompt_fingerprints"]["rag_grounded"][
        "sha256"
    ] = "0" * 64
    path = write_suite(
        tmp_path,
        [rag_case()],
        manifest_value=value,
    )
    with pytest.raises(
        EvaluationInputError,
        match="fingerprint",
    ):
        load_suite(path)


def test_result_set_rejects_missing_unknown_and_duplicate(
    tmp_path,
) -> None:
    suite_path = write_suite(
        tmp_path,
        [rag_case("c1"), rag_case("c2")],
    )
    suite = load_suite(suite_path)

    missing = tmp_path / "missing.jsonl"
    missing.write_text(
        json.dumps(
            {
                "case_id": "c1",
                "case_type": "rag_grounding",
                "answerable": True,
                "answer": "x",
                "cited_source_ids": ["S1"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        EvaluationInputError,
        match="Missing",
    ):
        load_results(missing, suite)

    unknown = tmp_path / "unknown.jsonl"
    unknown.write_text(
        json.dumps(
            {
                "case_id": "unknown",
                "case_type": "rag_grounding",
                "answerable": True,
                "answer": "x",
                "cited_source_ids": ["S1"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        EvaluationInputError,
        match="Unknown",
    ):
        load_results(unknown, suite)

    duplicate = tmp_path / "duplicate.jsonl"
    row = {
        "case_id": "c1",
        "case_type": "rag_grounding",
        "answerable": True,
        "answer": "x",
        "cited_source_ids": ["S1"],
    }
    duplicate.write_text(
        json.dumps(row) + "\n" + json.dumps(row) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        EvaluationInputError,
        match="Duplicate",
    ):
        load_results(duplicate, suite)

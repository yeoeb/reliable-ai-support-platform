import copy

import pytest

from app.evaluation.loader import load_suite
from app.evaluation.schemas import EvaluationInputError
from tests.test_evaluation_loader import (
    manifest,
    rag_case,
    write_suite,
)


def with_tags(case, *tags):
    value = copy.deepcopy(case)
    value["tags"] = list(tags)
    return value


def with_minimums(**minimums):
    value = manifest()
    value["tag_minimums"] = minimums
    return value


def test_manifest_without_tag_minimums_remains_compatible(
    tmp_path,
) -> None:
    path = write_suite(tmp_path, [rag_case()])

    suite = load_suite(path)

    assert suite.manifest.tag_minimums == {}


def test_exact_tag_minimum_passes(tmp_path) -> None:
    path = write_suite(
        tmp_path,
        [
            with_tags(rag_case("c1"), "rag", "single"),
            with_tags(rag_case("c2"), "rag", "multi"),
        ],
        manifest_value=with_minimums(rag=2, single=1),
    )

    suite = load_suite(path)

    assert suite.manifest.tag_minimums == {
        "rag": 2,
        "single": 1,
    }


@pytest.mark.parametrize(
    ("minimums", "match"),
    [
        ({"missing": 1}, "missing requires 1, observed 0"),
        ({"rag": 2}, "rag requires 2, observed 1"),
    ],
)
def test_missing_or_undercovered_tag_fails_closed(
    tmp_path,
    minimums,
    match,
) -> None:
    path = write_suite(
        tmp_path,
        [with_tags(rag_case(), "rag")],
        manifest_value=with_minimums(**minimums),
    )

    with pytest.raises(EvaluationInputError, match=match):
        load_suite(path)


@pytest.mark.parametrize(
    "tag_minimums",
    [
        {"": 1},
        {"   ": 1},
        {"x" * 101: 1},
        {"rag": 0},
        {"rag": 1001},
        {"rag": True},
        {"rag": "1"},
        {f"tag-{index}": 1 for index in range(51)},
    ],
)
def test_invalid_tag_minimum_contract_is_rejected(
    tmp_path,
    tag_minimums,
) -> None:
    value = manifest()
    value["tag_minimums"] = tag_minimums
    path = write_suite(
        tmp_path,
        [with_tags(rag_case(), "rag")],
        manifest_value=value,
    )

    with pytest.raises(
        EvaluationInputError,
        match="Invalid suite manifest",
    ):
        load_suite(path)

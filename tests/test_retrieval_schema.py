import pytest
from pydantic import ValidationError

from app.schemas.retrieval import (
    MAX_KNOWLEDGE_SEARCH_QUERY_CHARS,
    KnowledgeSearchRequest,
)


def test_search_request_defaults() -> None:
    request = KnowledgeSearchRequest(
        query="  password reset  ",
    )
    assert request.query == "password reset"
    assert request.top_k == 5
    assert request.min_similarity == 0.0


def test_exact_maximum_query_length_is_accepted() -> None:
    request = KnowledgeSearchRequest(
        query="x" * MAX_KNOWLEDGE_SEARCH_QUERY_CHARS,
    )
    assert len(request.query) == MAX_KNOWLEDGE_SEARCH_QUERY_CHARS


def test_raw_query_limit_cannot_be_bypassed_by_outer_whitespace() -> None:
    with pytest.raises(ValidationError):
        KnowledgeSearchRequest(
            query=(
                " "
                + "x" * MAX_KNOWLEDGE_SEARCH_QUERY_CHARS
                + " "
            ),
        )


def test_whitespace_only_query_is_rejected() -> None:
    with pytest.raises(ValidationError):
        KnowledgeSearchRequest(query="   ")


@pytest.mark.parametrize("top_k", [0, 21])
def test_top_k_is_bounded(top_k: int) -> None:
    with pytest.raises(ValidationError):
        KnowledgeSearchRequest(
            query="query",
            top_k=top_k,
        )


@pytest.mark.parametrize(
    "min_similarity",
    [-0.01, 1.01],
)
def test_min_similarity_is_bounded(
    min_similarity: float,
) -> None:
    with pytest.raises(ValidationError):
        KnowledgeSearchRequest(
            query="query",
            min_similarity=min_similarity,
        )


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        KnowledgeSearchRequest(
            query="query",
            unexpected=True,
        )

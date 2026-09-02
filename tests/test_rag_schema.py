import pytest
from pydantic import ValidationError

from app.schemas.rag import RagAnswerRequest
from app.schemas.retrieval import MAX_KNOWLEDGE_SEARCH_QUERY_CHARS


def test_rag_request_defaults_and_trim() -> None:
    request = RagAnswerRequest(
        question="  reset password  ",
    )
    assert request.question == "reset password"
    assert request.top_k == 5
    assert request.min_similarity == 0.0


def test_rag_request_raw_length_cannot_use_whitespace_bypass() -> None:
    with pytest.raises(ValidationError):
        RagAnswerRequest(
            question=(
                " "
                + "x" * MAX_KNOWLEDGE_SEARCH_QUERY_CHARS
                + " "
            ),
        )


@pytest.mark.parametrize("top_k", [0, 21])
def test_rag_top_k_is_bounded(top_k: int) -> None:
    with pytest.raises(ValidationError):
        RagAnswerRequest(
            question="question",
            top_k=top_k,
        )


def test_rag_request_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RagAnswerRequest(
            question="question",
            unexpected=True,
        )

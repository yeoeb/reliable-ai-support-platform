from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.errors import (
    InvalidGenerationProviderResponseError,
)
from app.integrations.llm import (
    GroundedAnswerProviderResult,
)
from app.schemas.rag import RagAnswerRequest
from app.services.rag import RagService
from app.services.retrieval import (
    KnowledgeSearchServiceResult,
    RetrievedKnowledge,
)


def make_retrieved(
    *,
    content="retrieved secret content",
    source_name="internal.md",
):
    return RetrievedKnowledge(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Runbook",
        source_type="markdown",
        source_name=source_name,
        chunk_index=0,
        content=content,
        similarity=0.91,
    )


def make_service(results):
    session = MagicMock(spec=Session)
    retrieval = MagicMock()
    retrieval.search.return_value = KnowledgeSearchServiceResult(
        results=results,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        token_usage=5,
    )
    provider = MagicMock()
    service = RagService(
        session,
        retrieval,
        provider,
    )
    service.audit_service = MagicMock()
    return service, session, retrieval, provider


def request():
    return RagAnswerRequest(
        question="secret user question",
        top_k=5,
        min_similarity=0.5,
    )


def test_zero_retrieval_bypasses_generation_provider() -> None:
    service, _, _, provider = make_service([])

    result = service.answer(
        actor_user_id=uuid4(),
        request=request(),
    )

    assert result.status == "insufficient_evidence"
    assert result.citations == []
    assert result.generation_model is None
    provider.generate.assert_not_called()


def test_grounded_citations_are_server_mapped_and_provider_wait_is_outside_transaction() -> None:
    row = make_retrieved()
    service, session, _, provider = make_service([row])
    provider.generate.return_value = GroundedAnswerProviderResult(
        answerable=True,
        answer="Use the runbook.",
        cited_source_ids=["S1", "S1"],
        input_tokens=10,
        output_tokens=4,
        model="gpt-5.6-terra",
    )

    result = service.answer(
        actor_user_id=uuid4(),
        request=request(),
    )

    session.rollback.assert_called_once()
    kwargs = provider.generate.call_args.kwargs
    assert kwargs["question"] == "secret user question"
    assert kwargs["sources"][0].source_id == "S1"
    assert kwargs["sources"][0].content == row.content
    assert result.status == "grounded"
    assert len(result.citations) == 1
    assert result.citations[0].chunk_id == row.chunk_id
    assert result.citations[0].source_name == row.source_name
    assert result.citations[0].content == row.content


def test_unknown_provider_citation_fails_closed() -> None:
    service, _, _, provider = make_service(
        [make_retrieved()]
    )
    provider.generate.return_value = GroundedAnswerProviderResult(
        answerable=True,
        answer="answer",
        cited_source_ids=["S99"],
        input_tokens=1,
        output_tokens=1,
        model="gpt-5.6-terra",
    )

    with pytest.raises(
        InvalidGenerationProviderResponseError,
    ):
        service.answer(
            actor_user_id=uuid4(),
            request=request(),
        )


def test_insufficient_provider_result_cannot_cite_sources() -> None:
    service, _, _, provider = make_service(
        [make_retrieved()]
    )
    provider.generate.return_value = GroundedAnswerProviderResult(
        answerable=False,
        answer="",
        cited_source_ids=["S1"],
        input_tokens=1,
        output_tokens=1,
        model="gpt-5.6-terra",
    )

    with pytest.raises(
        InvalidGenerationProviderResponseError,
    ):
        service.answer(
            actor_user_id=uuid4(),
            request=request(),
        )


def test_audit_and_runtime_log_exclude_question_answer_and_chunk(
    monkeypatch,
) -> None:
    row = make_retrieved()
    service, _, _, provider = make_service([row])
    provider.generate.return_value = GroundedAnswerProviderResult(
        answerable=True,
        answer="generated secret answer",
        cited_source_ids=["S1"],
        input_tokens=10,
        output_tokens=4,
        model="gpt-5.6-terra",
    )
    log_info = MagicMock()
    monkeypatch.setattr(
        "app.services.rag.logger.info",
        log_info,
    )

    service.answer(
        actor_user_id=uuid4(),
        request=request(),
    )

    audit_metadata = (
        service.audit_service
        .record_best_effort
        .call_args.kwargs["event_metadata"]
    )
    log_extra = log_info.call_args.kwargs["extra"]
    serialized = str(audit_metadata) + str(log_extra)

    assert "secret user question" not in serialized
    assert "generated secret answer" not in serialized
    assert row.content not in serialized
    assert row.source_name not in serialized
    assert "api_key" not in serialized

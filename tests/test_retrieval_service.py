from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.errors import (
    EmbeddingProviderUnavailableError,
    InvalidEmbeddingProviderResponseError,
    PersistenceUnavailableError,
)
from app.integrations.embeddings import EmbeddingBatchResult
from app.repositories.retrieval import RetrievalRow
from app.schemas.retrieval import KnowledgeSearchRequest
from app.services.retrieval import RetrievalService


DIMENSIONS = 1536


class FakeProvider:
    provider_name = "openai"

    def __init__(self, callback=None):
        self.callback = callback
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        if self.callback is not None:
            return self.callback(texts)
        return EmbeddingBatchResult(
            vectors=[
                [1.0] + [0.0] * (DIMENSIONS - 1)
            ],
            token_usage=11,
        )


def make_service(*, provider=None):
    session = MagicMock(spec=Session)
    provider = provider or FakeProvider()
    service = RetrievalService(
        session,
        provider,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=DIMENSIONS,
        chunk_size=1000,
        chunk_overlap=150,
    )
    service.repository = MagicMock()
    service.audit_service = MagicMock()
    return service, session, provider


def make_request(**kwargs):
    values = {
        "query": "reset password",
        "top_k": 5,
        "min_similarity": 0.6,
    }
    values.update(kwargs)
    return KnowledgeSearchRequest(**values)


def make_row(
    *,
    distance=0.2,
    content="sensitive retrieved content",
    source_name="internal-runbook.md",
):
    return RetrievalRow(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Internal Runbook",
        source_type="markdown",
        source_name=source_name,
        chunk_index=0,
        content=content,
        cosine_distance=distance,
    )


def test_provider_runs_before_repository_query() -> None:
    service = None

    def callback(texts):
        service.repository.search_exact_cosine.assert_not_called()
        return EmbeddingBatchResult(
            vectors=[
                [1.0] + [0.0] * (DIMENSIONS - 1)
            ],
            token_usage=2,
        )

    provider = FakeProvider(callback)
    service, _, _ = make_service(provider=provider)
    service.repository.search_exact_cosine.return_value = []

    service.search(
        actor_user_id=uuid4(),
        request=make_request(),
    )
    assert provider.calls == [["reset password"]]


def test_search_uses_current_config_and_returns_similarity() -> None:
    service, _, _ = make_service()
    service.repository.search_exact_cosine.return_value = [
        make_row(distance=0.2)
    ]

    result = service.search(
        actor_user_id=uuid4(),
        request=make_request(
            top_k=3,
            min_similarity=0.75,
        ),
    )

    assert result.results[0].similarity == pytest.approx(0.8)
    assert result.token_usage == 11
    kwargs = service.repository.search_exact_cosine.call_args.kwargs
    assert kwargs["top_k"] == 3
    assert kwargs["min_similarity"] == 0.75
    assert len(kwargs["embedding_config_hash"]) == 64
    assert kwargs["query_vector"][0] == 1.0


def test_empty_results_are_successful() -> None:
    service, _, _ = make_service()
    service.repository.search_exact_cosine.return_value = []

    result = service.search(
        actor_user_id=uuid4(),
        request=make_request(),
    )

    assert result.results == []
    assert result.token_usage == 11
    service.audit_service.record_best_effort.assert_called_once()


def test_provider_failure_does_not_query_database() -> None:
    def fail(_):
        raise EmbeddingProviderUnavailableError

    service, session, _ = make_service(
        provider=FakeProvider(fail)
    )

    with pytest.raises(EmbeddingProviderUnavailableError):
        service.search(
            actor_user_id=uuid4(),
            request=make_request(),
        )

    service.repository.search_exact_cosine.assert_not_called()
    service.audit_service.record_best_effort.assert_not_called()
    session.rollback.assert_not_called()


@pytest.mark.parametrize(
    "bad_result",
    [
        SimpleNamespace(vectors=[], token_usage=1),
        SimpleNamespace(
            vectors=[[0.1] * 12],
            token_usage=1,
        ),
        SimpleNamespace(
            vectors=[
                [float("nan")] * DIMENSIONS
            ],
            token_usage=1,
        ),
        SimpleNamespace(
            vectors=[
                [0.1] * DIMENSIONS
            ],
            token_usage=True,
        ),
        SimpleNamespace(token_usage=1),
    ],
)
def test_malformed_query_embedding_fails_closed(
    bad_result,
) -> None:
    service, _, _ = make_service(
        provider=FakeProvider(
            lambda _: bad_result
        )
    )

    with pytest.raises(
        InvalidEmbeddingProviderResponseError,
    ):
        service.search(
            actor_user_id=uuid4(),
            request=make_request(),
        )

    service.repository.search_exact_cosine.assert_not_called()


def test_database_failure_rolls_back_and_translates() -> None:
    service, session, _ = make_service()
    service.repository.search_exact_cosine.side_effect = OperationalError(
        "SELECT",
        {},
        Exception("database unavailable"),
    )

    with pytest.raises(PersistenceUnavailableError):
        service.search(
            actor_user_id=uuid4(),
            request=make_request(),
        )

    session.rollback.assert_called_once()
    service.audit_service.record_best_effort.assert_not_called()


def test_audit_and_runtime_log_exclude_query_and_result_content(
    monkeypatch,
) -> None:
    service, _, _ = make_service()
    row = make_row()
    service.repository.search_exact_cosine.return_value = [row]

    log_info = MagicMock()
    monkeypatch.setattr(
        "app.services.retrieval.logger.info",
        log_info,
    )

    result = service.search(
        actor_user_id=uuid4(),
        request=make_request(
            query="secret user question",
        ),
    )

    audit_metadata = (
        service.audit_service
        .record_best_effort
        .call_args.kwargs["event_metadata"]
    )
    log_extra = log_info.call_args.kwargs["extra"]

    assert set(audit_metadata) == {
        "top_k",
        "min_similarity",
        "result_count",
        "embedding_model",
        "embedding_dimensions",
        "token_usage",
    }
    assert set(log_extra) == {
        "event",
        "result_count",
        "top_k",
        "min_similarity",
        "embedding_model",
        "embedding_dimensions",
        "token_usage",
    }
    serialized = str(audit_metadata) + str(log_extra)
    assert "secret user question" not in serialized
    assert row.content not in serialized
    assert row.source_name not in serialized
    assert "api_key" not in serialized
    assert result.results[0].content == row.content


def test_similarity_is_clamped_for_float_noise() -> None:
    service, _, _ = make_service()
    service.repository.search_exact_cosine.return_value = [
        make_row(distance=-0.00000001),
        make_row(distance=2.00000001),
    ]

    result = service.search(
        actor_user_id=uuid4(),
        request=make_request(),
    )

    assert result.results[0].similarity == 1.0
    assert result.results[1].similarity == -1.0

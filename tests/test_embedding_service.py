from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.errors import (
    EmbeddingProviderNotConfiguredError,
    EmbeddingProviderUnavailableError,
    EmbeddingStateConflictError,
    InvalidEmbeddingProviderResponseError,
    KnowledgeDocumentNotFoundError,
    PersistenceUnavailableError,
)
from app.integrations.embeddings import (
    EmbeddingBatchResult,
    OpenAIEmbeddingProvider,
)
from app.repositories.embedding import PersistedChunkState
from app.services.chunking import split_into_chunks
from app.services.embedding import EmbeddingService


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
                [0.1] * DIMENSIONS
                for _ in texts
            ],
            token_usage=len(texts),
        )


def make_service(
    *,
    content="abcdefghij",
    provider=None,
    batch_size=32,
    chunk_size=1000,
    overlap=150,
):
    session = MagicMock(spec=Session)
    provider = provider or FakeProvider()
    service = EmbeddingService(
        session,
        provider,
        embedding_model="text-embedding-3-small",
        embedding_dimensions=DIMENSIONS,
        embedding_batch_size=batch_size,
        chunk_size=chunk_size,
        chunk_overlap=overlap,
    )
    document = SimpleNamespace(
        id=uuid4(),
        content=content,
    )
    service.knowledge_repository = MagicMock()
    service.knowledge_repository.get_by_id.return_value = document
    service.embedding_repository = MagicMock()
    service.audit_service = MagicMock()
    return service, session, provider, document


def complete_states(service, document):
    chunks = split_into_chunks(
        document.content,
        chunk_size=service.chunk_size,
        overlap=service.chunk_overlap,
    )
    config = service._pipeline_config()
    return [
        PersistedChunkState(
            chunk_index=chunk.index,
            content_hash=chunk.content_hash,
            embedding_provider=config.provider_name,
            embedding_model=config.embedding_model,
            embedding_dimensions=config.embedding_dimensions,
            chunking_strategy=config.chunking_strategy,
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            embedding_config_hash=config.config_hash,
        )
        for chunk in chunks
    ]


def test_missing_document_fails_before_provider_call() -> None:
    service, session, provider, _ = make_service()
    service.knowledge_repository.get_by_id.return_value = None

    with pytest.raises(
        KnowledgeDocumentNotFoundError,
    ):
        service.embed_document(
            actor_user_id=uuid4(),
            document_id=uuid4(),
        )

    assert provider.calls == []
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_missing_state_calls_provider_then_persists_and_audits() -> None:
    service, session, provider, document = make_service()
    service.embedding_repository.list_states_for_config.side_effect = [
        [],
        [],
    ]

    result = service.embed_document(
        actor_user_id=uuid4(),
        document_id=document.id,
    )

    assert result.changed is True
    assert result.chunk_count == 1
    assert result.token_usage == 1
    assert len(provider.calls) == 1
    assert provider.calls[0] == [document.content]
    service.embedding_repository.create_many.assert_called_once()
    service.audit_service.record.assert_called_once()
    assert (
        service.audit_service.record.call_args.kwargs[
            "event_metadata"
        ]["changed"]
        is True
    )
    session.rollback.assert_called_once()
    session.commit.assert_called_once()


def test_read_transaction_is_closed_before_provider_wait() -> None:
    service = None
    session = None

    def callback(texts):
        assert session.rollback.call_count == 1
        assert session.commit.call_count == 0
        return EmbeddingBatchResult(
            vectors=[
                [0.2] * DIMENSIONS
                for _ in texts
            ],
            token_usage=4,
        )

    provider = FakeProvider(callback)
    service, session, provider, document = make_service(
        provider=provider,
    )
    service.embedding_repository.list_states_for_config.side_effect = [
        [],
        [],
    ]

    service.embed_document(
        actor_user_id=uuid4(),
        document_id=document.id,
    )

    assert provider.calls


def test_complete_state_skips_provider_and_audits_changed_false() -> None:
    service, session, provider, document = make_service()
    states = complete_states(service, document)
    service.embedding_repository.list_states_for_config.return_value = states

    result = service.embed_document(
        actor_user_id=uuid4(),
        document_id=document.id,
    )

    assert result.changed is False
    assert result.token_usage == 0
    assert provider.calls == []
    service.embedding_repository.create_many.assert_not_called()
    assert (
        service.audit_service.record.call_args.kwargs[
            "event_metadata"
        ]["changed"]
        is False
    )
    session.rollback.assert_called_once()
    session.commit.assert_called_once()


def test_partial_state_fails_closed_without_provider() -> None:
    service, session, provider, document = make_service(
        content="abcdefghij",
        chunk_size=4,
        overlap=1,
    )
    states = complete_states(service, document)
    service.embedding_repository.list_states_for_config.return_value = states[:1]

    with pytest.raises(
        EmbeddingStateConflictError,
    ):
        service.embed_document(
            actor_user_id=uuid4(),
            document_id=document.id,
        )

    assert provider.calls == []
    service.embedding_repository.create_many.assert_not_called()
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_malformed_provider_vector_produces_no_db_writes() -> None:
    provider = FakeProvider(
        lambda texts: EmbeddingBatchResult(
            vectors=[
                [0.1] * 12
                for _ in texts
            ],
            token_usage=1,
        )
    )
    service, session, provider, document = make_service(
        provider=provider,
    )
    service.embedding_repository.list_states_for_config.return_value = []

    with pytest.raises(
        InvalidEmbeddingProviderResponseError,
    ):
        service.embed_document(
            actor_user_id=uuid4(),
            document_id=document.id,
        )

    service.embedding_repository.create_many.assert_not_called()
    service.audit_service.record.assert_not_called()
    session.commit.assert_not_called()
    assert session.rollback.call_count == 1


def test_provider_unavailable_produces_no_db_writes() -> None:
    def unavailable(texts):
        raise EmbeddingProviderUnavailableError

    provider = FakeProvider(unavailable)
    service, session, provider, document = make_service(
        provider=provider,
    )
    service.embedding_repository.list_states_for_config.return_value = []

    with pytest.raises(
        EmbeddingProviderUnavailableError,
    ):
        service.embed_document(
            actor_user_id=uuid4(),
            document_id=document.id,
        )

    service.embedding_repository.create_many.assert_not_called()
    service.audit_service.record.assert_not_called()
    session.commit.assert_not_called()
    assert session.rollback.call_count == 1


def test_post_provider_concurrent_complete_recheck_skips_persistence() -> None:
    service, session, provider, document = make_service()
    states = complete_states(service, document)
    service.embedding_repository.list_states_for_config.side_effect = [
        [],
        states,
    ]

    result = service.embed_document(
        actor_user_id=uuid4(),
        document_id=document.id,
    )

    assert result.changed is False
    assert result.token_usage == 1
    assert len(provider.calls) == 1
    service.embedding_repository.create_many.assert_not_called()
    service.audit_service.record.assert_called_once()
    session.commit.assert_called_once()


def test_audit_failure_rolls_back_chunk_writes() -> None:
    service, session, provider, document = make_service()
    service.embedding_repository.list_states_for_config.side_effect = [
        [],
        [],
    ]
    service.audit_service.record.side_effect = OperationalError(
        "INSERT",
        {},
        Exception("audit unavailable"),
    )

    with pytest.raises(
        PersistenceUnavailableError,
    ):
        service.embed_document(
            actor_user_id=uuid4(),
            document_id=document.id,
        )

    service.embedding_repository.create_many.assert_called_once()
    session.commit.assert_not_called()
    assert session.rollback.call_count == 2


def test_provider_batches_are_bounded_at_32() -> None:
    service, session, provider, document = make_service(
        content="x" * 65,
        chunk_size=1,
        overlap=0,
        batch_size=32,
    )
    service.embedding_repository.list_states_for_config.side_effect = [
        [],
        [],
    ]

    result = service.embed_document(
        actor_user_id=uuid4(),
        document_id=document.id,
    )

    assert result.chunk_count == 65
    assert [
        len(batch)
        for batch in provider.calls
    ] == [32, 32, 1]
    assert result.token_usage == 65


def test_non_finite_provider_vector_is_rejected_by_service() -> None:
    provider = FakeProvider(
        lambda texts: EmbeddingBatchResult(
            vectors=[
                [float("nan")] * DIMENSIONS
                for _ in texts
            ],
            token_usage=1,
        )
    )
    service, session, provider, document = make_service(
        provider=provider,
    )
    service.embedding_repository.list_states_for_config.return_value = []

    with pytest.raises(
        InvalidEmbeddingProviderResponseError,
    ):
        service.embed_document(
            actor_user_id=uuid4(),
            document_id=document.id,
        )

    service.embedding_repository.create_many.assert_not_called()
    session.commit.assert_not_called()



@pytest.mark.parametrize(
    "bad_result",
    [
        SimpleNamespace(
            vectors=None,
            token_usage=1,
        ),
        SimpleNamespace(
            vectors=[[0.1] * DIMENSIONS],
            token_usage="1",
        ),
        SimpleNamespace(
            vectors=[[0.1] * DIMENSIONS],
            token_usage=True,
        ),
        SimpleNamespace(
            token_usage=1,
        ),
    ],
)
def test_service_rejects_malformed_provider_result_shape(
    bad_result,
) -> None:
    provider = FakeProvider(
        lambda texts: bad_result
    )
    service, session, provider, document = make_service(
        provider=provider,
    )
    service.embedding_repository.list_states_for_config.return_value = []

    with pytest.raises(
        InvalidEmbeddingProviderResponseError,
    ):
        service.embed_document(
            actor_user_id=uuid4(),
            document_id=document.id,
        )

    service.embedding_repository.create_many.assert_not_called()
    service.audit_service.record.assert_not_called()
    session.commit.assert_not_called()



def test_complete_state_does_not_require_openai_api_key() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
    )
    service, session, _, document = make_service(
        provider=provider,
    )
    states = complete_states(
        service,
        document,
    )
    service.embedding_repository.list_states_for_config.return_value = states

    result = service.embed_document(
        actor_user_id=uuid4(),
        document_id=document.id,
    )

    assert result.changed is False
    assert result.token_usage == 0
    service.embedding_repository.create_many.assert_not_called()
    session.commit.assert_called_once()


def test_missing_state_requires_openai_api_key_only_at_provider_boundary() -> None:
    provider = OpenAIEmbeddingProvider(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=DIMENSIONS,
    )
    service, session, _, document = make_service(
        provider=provider,
    )
    service.embedding_repository.list_states_for_config.return_value = []

    with pytest.raises(
        EmbeddingProviderNotConfiguredError,
    ):
        service.embed_document(
            actor_user_id=uuid4(),
            document_id=document.id,
        )

    service.embedding_repository.create_many.assert_not_called()
    service.audit_service.record.assert_not_called()
    session.commit.assert_not_called()
    assert session.rollback.call_count == 1


def test_audit_and_runtime_log_exclude_content_vector_and_api_key(
    monkeypatch,
) -> None:
    service, session, provider, document = make_service(
        content="sensitive-chunk-content",
    )
    service.embedding_repository.list_states_for_config.side_effect = [
        [],
        [],
    ]

    log_info = MagicMock()
    monkeypatch.setattr(
        "app.services.embedding.logger.info",
        log_info,
    )

    result = service.embed_document(
        actor_user_id=uuid4(),
        document_id=document.id,
    )

    audit_metadata = (
        service.audit_service.record.call_args.kwargs[
            "event_metadata"
        ]
    )
    log_extra = log_info.call_args.kwargs[
        "extra"
    ]

    assert set(audit_metadata) == {
        "embedding_provider",
        "embedding_model",
        "embedding_dimensions",
        "chunk_count",
        "embedding_config_hash",
        "changed",
        "token_usage",
    }
    assert set(log_extra) == {
        "event",
        "document_id",
        "embedding_provider",
        "embedding_model",
        "embedding_dimensions",
        "chunk_count",
        "changed",
        "token_usage",
    }

    serialized = (
        str(audit_metadata)
        + str(log_extra)
    )
    assert "sensitive-chunk-content" not in serialized
    assert "embedding" not in log_extra
    assert "vector" not in log_extra
    assert "api_key" not in serialized
    assert result.changed is True

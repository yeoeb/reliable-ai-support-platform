from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.orm import Session

from app.repositories.embedding import (
    EmbeddingRepository,
    KnowledgeChunkCreateRecord,
)


def make_record():
    return KnowledgeChunkCreateRecord(
        document_id=uuid4(),
        chunk_index=0,
        content="chunk",
        content_hash="a" * 64,
        embedding=[0.1] * 1536,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        chunking_strategy="char-v1",
        chunk_size=1000,
        chunk_overlap=150,
        embedding_config_hash="b" * 64,
    )


def test_list_states_returns_metadata_only_without_commit() -> None:
    session = MagicMock(spec=Session)
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(
            chunk_index=0,
            content_hash="a" * 64,
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            chunking_strategy="char-v1",
            chunk_size=1000,
            chunk_overlap=150,
            embedding_config_hash="b" * 64,
        )
    ]
    session.execute.return_value = result
    repository = EmbeddingRepository(session)

    states = repository.list_states_for_config(
        document_id=uuid4(),
        embedding_config_hash="b" * 64,
    )

    assert len(states) == 1
    assert states[0].chunk_index == 0
    assert states[0].content_hash == "a" * 64
    session.execute.assert_called_once()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_create_many_adds_and_flushes_without_commit() -> None:
    session = MagicMock(spec=Session)
    repository = EmbeddingRepository(session)
    record = make_record()

    chunks = repository.create_many([record])

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.document_id == record.document_id
    assert chunk.content == "chunk"
    assert len(chunk.embedding) == 1536
    session.add_all.assert_called_once_with(chunks)
    session.flush.assert_called_once()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()

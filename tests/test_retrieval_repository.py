from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.repositories.retrieval import RetrievalRepository


def test_exact_cosine_search_returns_provenance_without_vector() -> None:
    session = MagicMock(spec=Session)
    result = MagicMock()
    chunk_id = uuid4()
    document_id = uuid4()
    result.all.return_value = [
        SimpleNamespace(
            chunk_id=chunk_id,
            document_id=document_id,
            document_title="Runbook",
            source_type="markdown",
            source_name="runbook.md",
            chunk_index=2,
            content="Reset the service.",
            cosine_distance=0.25,
        )
    ]
    session.execute.return_value = result

    repository = RetrievalRepository(session)
    rows = repository.search_exact_cosine(
        query_vector=[0.1] * 1536,
        embedding_config_hash="a" * 64,
        top_k=5,
        min_similarity=0.5,
    )

    row = rows[0]
    assert row.chunk_id == chunk_id
    assert row.document_id == document_id
    assert row.document_title == "Runbook"
    assert row.source_name == "runbook.md"
    assert row.content == "Reset the service."
    assert row.cosine_distance == 0.25
    assert not hasattr(row, "embedding")
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_repository_builds_exact_cosine_filter_order_and_limit() -> None:
    session = MagicMock(spec=Session)
    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result

    repository = RetrievalRepository(session)
    repository.search_exact_cosine(
        query_vector=[1.0] + [0.0] * 1535,
        embedding_config_hash="c" * 64,
        top_k=7,
        min_similarity=0.8,
    )

    statement = session.execute.call_args.args[0]
    sql = str(statement)
    assert "<=>" in sql
    assert "embedding_config_hash" in sql
    assert "knowledge_documents" in sql
    assert "ORDER BY" in sql
    assert "knowledge_chunks.id" in sql

    params = list(statement.compile().params.values())
    assert 7 in params
    float_params = [
        value
        for value in params
        if isinstance(value, float)
    ]
    assert any(
        value == pytest.approx(0.2)
        for value in float_params
    )

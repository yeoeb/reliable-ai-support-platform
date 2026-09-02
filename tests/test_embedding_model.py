from pgvector.sqlalchemy import Vector
from sqlalchemy import Index, UniqueConstraint

from app.models.knowledge_chunk import (
    EMBEDDING_VECTOR_DIMENSIONS,
    KnowledgeChunk,
)


def test_knowledge_chunk_schema_contract() -> None:
    table = KnowledgeChunk.__table__

    assert table.name == "knowledge_chunks"
    assert EMBEDDING_VECTOR_DIMENSIONS == 1536
    assert isinstance(
        table.c.embedding.type,
        Vector,
    )
    assert table.c.embedding.type.dim == 1536

    assert {
        foreign_key.target_fullname
        for foreign_key in table.c.document_id.foreign_keys
    } == {
        "knowledge_documents.id"
    }
    foreign_key = next(
        iter(
            table.c.document_id.foreign_keys
        )
    )
    assert foreign_key.ondelete == "CASCADE"

    unique_constraints = [
        constraint
        for constraint in table.constraints
        if isinstance(
            constraint,
            UniqueConstraint,
        )
    ]
    assert any(
        [
            column.name
            for column in constraint.columns
        ]
        == [
            "document_id",
            "chunk_index",
            "embedding_config_hash",
        ]
        for constraint in unique_constraints
    )

    indexes = [
        index
        for index in table.indexes
        if isinstance(index, Index)
    ]
    assert {
        index.name
        for index in indexes
    } == {
        "ix_knowledge_chunks_document_config"
    }

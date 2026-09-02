from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_chunk import KnowledgeChunk


@dataclass(frozen=True)
class PersistedChunkState:
    chunk_index: int
    content_hash: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    chunking_strategy: str
    chunk_size: int
    chunk_overlap: int
    embedding_config_hash: str


@dataclass(frozen=True)
class KnowledgeChunkCreateRecord:
    document_id: UUID
    chunk_index: int
    content: str
    content_hash: str
    embedding: list[float]
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    chunking_strategy: str
    chunk_size: int
    chunk_overlap: int
    embedding_config_hash: str


class EmbeddingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_states_for_config(
        self,
        *,
        document_id: UUID,
        embedding_config_hash: str,
    ) -> list[PersistedChunkState]:
        statement = (
            select(
                KnowledgeChunk.chunk_index,
                KnowledgeChunk.content_hash,
                KnowledgeChunk.embedding_provider,
                KnowledgeChunk.embedding_model,
                KnowledgeChunk.embedding_dimensions,
                KnowledgeChunk.chunking_strategy,
                KnowledgeChunk.chunk_size,
                KnowledgeChunk.chunk_overlap,
                KnowledgeChunk.embedding_config_hash,
            )
            .where(
                KnowledgeChunk.document_id
                == document_id,
                KnowledgeChunk.embedding_config_hash
                == embedding_config_hash,
            )
            .order_by(KnowledgeChunk.chunk_index)
        )

        rows = self.session.execute(statement).all()

        return [
            PersistedChunkState(
                chunk_index=row.chunk_index,
                content_hash=row.content_hash,
                embedding_provider=row.embedding_provider,
                embedding_model=row.embedding_model,
                embedding_dimensions=row.embedding_dimensions,
                chunking_strategy=row.chunking_strategy,
                chunk_size=row.chunk_size,
                chunk_overlap=row.chunk_overlap,
                embedding_config_hash=row.embedding_config_hash,
            )
            for row in rows
        ]

    def create_many(
        self,
        records: list[KnowledgeChunkCreateRecord],
    ) -> list[KnowledgeChunk]:
        chunks = [
            KnowledgeChunk(
                document_id=record.document_id,
                chunk_index=record.chunk_index,
                content=record.content,
                content_hash=record.content_hash,
                embedding=record.embedding,
                embedding_provider=record.embedding_provider,
                embedding_model=record.embedding_model,
                embedding_dimensions=record.embedding_dimensions,
                chunking_strategy=record.chunking_strategy,
                chunk_size=record.chunk_size,
                chunk_overlap=record.chunk_overlap,
                embedding_config_hash=record.embedding_config_hash,
            )
            for record in records
        ]

        self.session.add_all(chunks)
        self.session.flush()
        return chunks

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument


@dataclass(frozen=True)
class RetrievalRow:
    chunk_id: UUID
    document_id: UUID
    document_title: str
    source_type: str
    source_name: str
    chunk_index: int
    content: str
    cosine_distance: float


class RetrievalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def search_exact_cosine(
        self,
        *,
        query_vector: list[float],
        embedding_config_hash: str,
        top_k: int,
        min_similarity: float,
    ) -> list[RetrievalRow]:
        distance = KnowledgeChunk.embedding.cosine_distance(
            query_vector
        )

        statement = (
            select(
                KnowledgeChunk.id.label("chunk_id"),
                KnowledgeChunk.document_id,
                KnowledgeDocument.title.label(
                    "document_title"
                ),
                KnowledgeDocument.source_type,
                KnowledgeDocument.source_name,
                KnowledgeChunk.chunk_index,
                KnowledgeChunk.content,
                distance.label("cosine_distance"),
            )
            .join(
                KnowledgeDocument,
                KnowledgeDocument.id
                == KnowledgeChunk.document_id,
            )
            .where(
                KnowledgeChunk.embedding_config_hash
                == embedding_config_hash,
                distance
                <= (1.0 - min_similarity),
            )
            .order_by(
                distance.asc(),
                KnowledgeChunk.id.asc(),
            )
            .limit(top_k)
        )

        rows = self.session.execute(
            statement
        ).all()

        return [
            RetrievalRow(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                document_title=row.document_title,
                source_type=row.source_type,
                source_name=row.source_name,
                chunk_index=row.chunk_index,
                content=row.content,
                cosine_distance=float(
                    row.cosine_distance
                ),
            )
            for row in rows
        ]

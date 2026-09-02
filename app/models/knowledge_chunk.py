from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


EMBEDDING_VECTOR_DIMENSIONS = 1536


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            "embedding_config_hash",
            name=(
                "uq_knowledge_chunks_"
                "document_index_embedding_config"
            ),
        ),
        Index(
            "ix_knowledge_chunks_document_config",
            "document_id",
            "embedding_config_hash",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "knowledge_documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_VECTOR_DIMENSIONS),
        nullable=False,
    )
    embedding_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    chunking_strategy: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    chunk_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    chunk_overlap: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    embedding_config_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

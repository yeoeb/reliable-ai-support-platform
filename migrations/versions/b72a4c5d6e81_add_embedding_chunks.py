"""add embedding chunks and pgvector

Revision ID: b72a4c5d6e81
Revises: a61f9b2c3d40
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa


revision: str = "b72a4c5d6e81"
down_revision: Union[str, Sequence[str], None] = "a61f9b2c3d40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EMBEDDING_VECTOR_DIMENSIONS = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "embedding",
            Vector(EMBEDDING_VECTOR_DIMENSIONS),
            nullable=False,
        ),
        sa.Column(
            "embedding_provider",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "embedding_model",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "embedding_dimensions",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "chunking_strategy",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "chunk_size",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "chunk_overlap",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "embedding_config_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f(
                "fk_knowledge_chunks_"
                "document_id_knowledge_documents"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_knowledge_chunks"),
        ),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            "embedding_config_hash",
            name=(
                "uq_knowledge_chunks_"
                "document_index_embedding_config"
            ),
        ),
    )

    op.create_index(
        "ix_knowledge_chunks_document_config",
        "knowledge_chunks",
        ["document_id", "embedding_config_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_chunks_document_config",
        table_name="knowledge_chunks",
    )
    op.drop_table("knowledge_chunks")

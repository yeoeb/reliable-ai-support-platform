from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.repositories.retrieval import RetrievalRepository


DIMENSIONS = 1536


def vector(x: float, y: float) -> list[float]:
    return [
        x,
        y,
        *([0.0] * (DIMENSIONS - 2)),
    ]


def test_exact_pgvector_cosine_ranking_threshold_and_config_filter() -> None:
    session = SessionLocal()
    document_id = uuid4()
    current_config = "c" * 64
    historical_config = "d" * 64

    document = KnowledgeDocument(
        id=document_id,
        title="Vector Retrieval Integration Runbook",
        source_type="text",
        source_name=f"integration-{document_id}.txt",
        content="integration content",
        content_hash="e" * 64,
        created_by_user_id=uuid4(),
    )

    chunks = [
        KnowledgeChunk(
            id=uuid4(),
            document_id=document_id,
            chunk_index=0,
            content="same direction",
            content_hash="0" * 64,
            embedding=vector(1.0, 0.0),
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            chunking_strategy="char-v1",
            chunk_size=1000,
            chunk_overlap=150,
            embedding_config_hash=current_config,
        ),
        KnowledgeChunk(
            id=uuid4(),
            document_id=document_id,
            chunk_index=1,
            content="similar direction",
            content_hash="1" * 64,
            embedding=vector(0.8, 0.6),
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            chunking_strategy="char-v1",
            chunk_size=1000,
            chunk_overlap=150,
            embedding_config_hash=current_config,
        ),
        KnowledgeChunk(
            id=uuid4(),
            document_id=document_id,
            chunk_index=2,
            content="orthogonal direction",
            content_hash="2" * 64,
            embedding=vector(0.0, 1.0),
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            chunking_strategy="char-v1",
            chunk_size=1000,
            chunk_overlap=150,
            embedding_config_hash=current_config,
        ),
        KnowledgeChunk(
            id=uuid4(),
            document_id=document_id,
            chunk_index=0,
            content="historical config should be excluded",
            content_hash="3" * 64,
            embedding=vector(1.0, 0.0),
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            chunking_strategy="char-v1",
            chunk_size=900,
            chunk_overlap=100,
            embedding_config_hash=historical_config,
        ),
    ]

    try:
        session.add(document)
        session.flush()
        session.add_all(chunks)
        session.commit()

        repository = RetrievalRepository(session)

        ranked = repository.search_exact_cosine(
            query_vector=vector(1.0, 0.0),
            embedding_config_hash=current_config,
            top_k=2,
            min_similarity=0.0,
        )

        assert [
            row.content
            for row in ranked
        ] == [
            "same direction",
            "similar direction",
        ]
        assert ranked[0].cosine_distance == pytest.approx(
            0.0,
            abs=1e-6,
        )
        assert ranked[1].cosine_distance == pytest.approx(
            0.2,
            abs=1e-6,
        )
        assert all(
            "historical" not in row.content
            for row in ranked
        )

        thresholded = repository.search_exact_cosine(
            query_vector=vector(1.0, 0.0),
            embedding_config_hash=current_config,
            top_k=20,
            min_similarity=0.9,
        )

        assert [
            row.content
            for row in thresholded
        ] == ["same direction"]
        assert thresholded[0].document_title == (
            "Vector Retrieval Integration Runbook"
        )
        assert not hasattr(
            thresholded[0],
            "embedding",
        )

    finally:
        session.rollback()
        session.execute(
            delete(KnowledgeChunk).where(
                KnowledgeChunk.document_id
                == document_id
            )
        )
        session.execute(
            delete(KnowledgeDocument).where(
                KnowledgeDocument.id
                == document_id
            )
        )
        session.commit()
        session.close()


def test_knowledge_read_permission_is_granted_only_to_support_and_admin() -> None:
    session = SessionLocal()

    try:
        statement = (
            select(Role.name)
            .join(
                RolePermission,
                RolePermission.role_id
                == Role.id,
            )
            .join(
                Permission,
                Permission.id
                == RolePermission.permission_id,
            )
            .where(
                Permission.name
                == "knowledge:read"
            )
            .order_by(Role.name)
        )

        roles = list(
            session.scalars(
                statement
            )
        )

        assert roles == [
            "admin",
            "support_agent",
        ]

    finally:
        session.rollback()
        session.close()

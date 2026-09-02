from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes.knowledge import require_knowledge_manage
from app.core.errors import (
    EmbeddingProviderUnavailableError,
    EmbeddingStateConflictError,
    KnowledgeDocumentNotFoundError,
    PersistenceUnavailableError,
)
from app.db.session import get_db
from app.main import app
from app.services.embedding import (
    EmbeddingService,
    KnowledgeEmbeddingResult,
)


client = TestClient(app)


def make_user():
    return SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )


def override_knowledge_manager():
    return make_user()


def override_db():
    yield object()


def make_result(
    *,
    changed: bool,
) -> KnowledgeEmbeddingResult:
    return KnowledgeEmbeddingResult(
        document_id=uuid4(),
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        chunk_count=3,
        embedding_config_hash="a" * 64,
        changed=changed,
        token_usage=42,
    )


def post_embeddings(document_id):
    return client.post(
        f"/admin/knowledge/documents/{document_id}/embeddings"
    )


def test_embed_returns_201_metadata_only(
    monkeypatch,
) -> None:
    result = make_result(
        changed=True,
    )
    monkeypatch.setattr(
        EmbeddingService,
        "embed_document",
        lambda self, **kwargs: result,
    )

    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = post_embeddings(
            result.document_id
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["document_id"] == str(
        result.document_id
    )
    assert payload["changed"] is True
    assert payload["chunk_count"] == 3
    assert payload["token_usage"] == 42
    assert "content" not in payload
    assert "embedding" not in payload
    assert "vector" not in payload


def test_embed_idempotent_returns_200(
    monkeypatch,
) -> None:
    result = make_result(
        changed=False,
    )
    monkeypatch.setattr(
        EmbeddingService,
        "embed_document",
        lambda self, **kwargs: result,
    )

    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = post_embeddings(
            result.document_id
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["changed"] is False


def test_embed_missing_document_returns_404(
    monkeypatch,
) -> None:
    def raise_missing(self, **kwargs):
        raise KnowledgeDocumentNotFoundError

    monkeypatch.setattr(
        EmbeddingService,
        "embed_document",
        raise_missing,
    )
    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = post_embeddings(
            uuid4()
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Knowledge document not found"
    }


def test_embed_inconsistent_state_returns_409(
    monkeypatch,
) -> None:
    def raise_conflict(self, **kwargs):
        raise EmbeddingStateConflictError

    monkeypatch.setattr(
        EmbeddingService,
        "embed_document",
        raise_conflict,
    )
    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = post_embeddings(
            uuid4()
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Embedding state is inconsistent"
    }


def test_embed_provider_failure_returns_generic_503(
    monkeypatch,
) -> None:
    def raise_provider(self, **kwargs):
        raise EmbeddingProviderUnavailableError(
            "provider secret detail"
        )

    monkeypatch.setattr(
        EmbeddingService,
        "embed_document",
        raise_provider,
    )
    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = post_embeddings(
            uuid4()
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Embedding service unavailable"
    }
    assert "provider secret detail" not in response.text


def test_embed_persistence_failure_returns_generic_503(
    monkeypatch,
) -> None:
    def raise_persistence(self, **kwargs):
        raise PersistenceUnavailableError

    monkeypatch.setattr(
        EmbeddingService,
        "embed_document",
        raise_persistence,
    )
    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = post_embeddings(
            uuid4()
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Persistence service unavailable"
    }


def test_embed_requires_authentication() -> None:
    response = post_embeddings(
        uuid4()
    )

    assert response.status_code == 401


def test_embed_forbidden_user_does_not_reach_service(
    monkeypatch,
) -> None:
    def deny():
        raise HTTPException(
            status_code=403,
            detail="Forbidden",
        )

    called = False

    def should_not_run(self, **kwargs):
        nonlocal called
        called = True
        raise AssertionError(
            "Embedding service should not run"
        )

    monkeypatch.setattr(
        EmbeddingService,
        "embed_document",
        should_not_run,
    )
    app.dependency_overrides[
        require_knowledge_manage
    ] = deny
    app.dependency_overrides[get_db] = override_db

    try:
        response = post_embeddings(
            uuid4()
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert called is False

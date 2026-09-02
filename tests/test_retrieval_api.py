from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes.retrieval import require_knowledge_read
from app.core.errors import (
    EmbeddingProviderUnavailableError,
    PersistenceUnavailableError,
)
from app.db.session import get_db
from app.main import app
from app.services.retrieval import (
    KnowledgeSearchServiceResult,
    RetrievedKnowledge,
    RetrievalService,
)


client = TestClient(app)


def override_reader():
    return SimpleNamespace(id=uuid4(), is_active=True)


def override_db():
    yield object()


def make_result():
    return KnowledgeSearchServiceResult(
        results=[
            RetrievedKnowledge(
                chunk_id=uuid4(),
                document_id=uuid4(),
                document_title="Runbook",
                source_type="markdown",
                source_name="runbook.md",
                chunk_index=1,
                content="Reset the password.",
                similarity=0.91,
            )
        ],
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        token_usage=7,
    )


def valid_payload():
    return {
        "query": "reset password",
        "top_k": 5,
        "min_similarity": 0.5,
    }


def test_search_returns_provenance_without_vector(
    monkeypatch,
) -> None:
    result = make_result()
    monkeypatch.setattr(
        RetrievalService,
        "search",
        lambda self, **kwargs: result,
    )
    app.dependency_overrides[require_knowledge_read] = override_reader
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/knowledge/search",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["result_count"] == 1
    assert payload["results"][0]["content"] == "Reset the password."
    assert payload["results"][0]["source_name"] == "runbook.md"
    assert "embedding" not in payload["results"][0]
    assert "vector" not in payload["results"][0]


def test_search_no_results_returns_200(
    monkeypatch,
) -> None:
    result = KnowledgeSearchServiceResult(
        results=[],
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        token_usage=3,
    )
    monkeypatch.setattr(
        RetrievalService,
        "search",
        lambda self, **kwargs: result,
    )
    app.dependency_overrides[require_knowledge_read] = override_reader
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/knowledge/search",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert response.json()["result_count"] == 0


def test_search_provider_failure_returns_generic_503(
    monkeypatch,
) -> None:
    def fail(self, **kwargs):
        raise EmbeddingProviderUnavailableError("provider detail")

    monkeypatch.setattr(RetrievalService, "search", fail)
    app.dependency_overrides[require_knowledge_read] = override_reader
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/knowledge/search",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Embedding service unavailable"
    }
    assert "provider detail" not in response.text


def test_search_database_failure_returns_generic_503(
    monkeypatch,
) -> None:
    def fail(self, **kwargs):
        raise PersistenceUnavailableError

    monkeypatch.setattr(RetrievalService, "search", fail)
    app.dependency_overrides[require_knowledge_read] = override_reader
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/knowledge/search",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Persistence service unavailable"
    }


def test_search_requires_authentication() -> None:
    response = client.post(
        "/knowledge/search",
        json=valid_payload(),
    )
    assert response.status_code == 401


def test_search_forbidden_user_does_not_reach_service(
    monkeypatch,
) -> None:
    called = False

    def deny():
        raise HTTPException(status_code=403, detail="Forbidden")

    def should_not_run(self, **kwargs):
        nonlocal called
        called = True
        raise AssertionError

    monkeypatch.setattr(
        RetrievalService,
        "search",
        should_not_run,
    )
    app.dependency_overrides[require_knowledge_read] = deny
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/knowledge/search",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert called is False


def test_search_validation_rejects_bad_bounds() -> None:
    app.dependency_overrides[require_knowledge_read] = override_reader
    app.dependency_overrides[get_db] = override_db

    try:
        top_k_response = client.post(
            "/knowledge/search",
            json={**valid_payload(), "top_k": 21},
        )
        similarity_response = client.post(
            "/knowledge/search",
            json={**valid_payload(), "min_similarity": 1.1},
        )
        query_response = client.post(
            "/knowledge/search",
            json={**valid_payload(), "query": "   "},
        )
    finally:
        app.dependency_overrides.clear()

    assert top_k_response.status_code == 422
    assert similarity_response.status_code == 422
    assert query_response.status_code == 422

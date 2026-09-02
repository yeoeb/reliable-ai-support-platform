from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes.rag import require_knowledge_read
from app.core.errors import (
    GenerationProviderUnavailableError,
)
from app.db.session import get_db
from app.main import app
from app.services.rag import (
    RagAnswerServiceResult,
    RagCitationResult,
    RagService,
)


client = TestClient(app)


def override_reader():
    return SimpleNamespace(id=uuid4(), is_active=True)


def override_db():
    yield object()


def valid_payload():
    return {
        "question": "How do I reset a password?",
        "top_k": 5,
        "min_similarity": 0.5,
    }


def make_result():
    return RagAnswerServiceResult(
        status="grounded",
        answer="Follow the runbook.",
        citations=[
            RagCitationResult(
                source_id="S1",
                chunk_id=uuid4(),
                document_id=uuid4(),
                document_title="Runbook",
                source_type="markdown",
                source_name="runbook.md",
                chunk_index=0,
                similarity=0.9,
                content="Reset steps.",
            )
        ],
        generation_model="gpt-5.6-terra",
        input_tokens=10,
        output_tokens=4,
    )


def test_rag_answer_returns_server_provenance_without_vector(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        RagService,
        "answer",
        lambda self, **kwargs: make_result(),
    )
    app.dependency_overrides[require_knowledge_read] = override_reader
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/knowledge/answer",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "grounded"
    assert payload["citations"][0]["source_id"] == "S1"
    assert payload["citations"][0]["source_name"] == "runbook.md"
    assert "embedding" not in payload["citations"][0]
    assert "vector" not in payload["citations"][0]


def test_rag_answer_requires_authentication() -> None:
    response = client.post(
        "/knowledge/answer",
        json=valid_payload(),
    )
    assert response.status_code == 401


def test_forbidden_caller_does_not_reach_rag_service(
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
        RagService,
        "answer",
        should_not_run,
    )
    app.dependency_overrides[require_knowledge_read] = deny
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/knowledge/answer",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert called is False


def test_generation_failure_returns_generic_503(
    monkeypatch,
) -> None:
    def fail(self, **kwargs):
        raise GenerationProviderUnavailableError(
            "sensitive provider detail"
        )

    monkeypatch.setattr(
        RagService,
        "answer",
        fail,
    )
    app.dependency_overrides[require_knowledge_read] = override_reader
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/knowledge/answer",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Generation service unavailable"
    }
    assert "sensitive provider detail" not in response.text

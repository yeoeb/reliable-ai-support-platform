from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import authorization
from app.api.routes import knowledge
from app.api.routes.knowledge import require_knowledge_manage
from app.core.errors import (
    InvalidKnowledgeContentError,
    PersistenceUnavailableError,
)
from app.db.session import get_db
from app.main import app
from app.models.knowledge_document import KnowledgeDocument
from app.schemas.knowledge import MAX_KNOWLEDGE_CONTENT_CHARS
from app.services.knowledge import KnowledgeIngestResult, KnowledgeService


client = TestClient(app)


def make_user():
    return SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )


def make_document() -> KnowledgeDocument:
    return KnowledgeDocument(
        id=uuid4(),
        title="Runbook",
        source_type="markdown",
        source_name="runbook.md",
        content="safe content",
        content_hash="a" * 64,
        created_by_user_id=uuid4(),
        created_at=datetime.now(timezone.utc),
    )


def override_knowledge_manager():
    return make_user()


def override_db():
    yield object()


def valid_payload() -> dict:
    return {
        "title": "Runbook",
        "source_type": "markdown",
        "source_name": "runbook.md",
        "content": "# Operations",
    }


def test_knowledge_manage_permission_denies_without_database_permission(
    monkeypatch,
) -> None:
    user = make_user()
    repository = MagicMock()
    repository.has_permission.return_value = False

    monkeypatch.setattr(
        authorization,
        "RBACRepository",
        lambda session: repository,
    )
    monkeypatch.setattr(
        authorization.AuditService,
        "record_best_effort",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        require_knowledge_manage(
            current_user=user,
            session=object(),
        )

    assert exc_info.value.status_code == 403
    repository.has_permission.assert_called_once_with(
        user.id,
        "knowledge:manage",
    )


def test_ingest_returns_201_and_excludes_content(
    monkeypatch,
) -> None:
    document = make_document()

    monkeypatch.setattr(
        KnowledgeService,
        "ingest",
        lambda self, **kwargs: KnowledgeIngestResult(
            document=document,
            changed=True,
        ),
    )

    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/admin/knowledge/documents",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == str(document.id)
    assert payload["changed"] is True
    assert payload["content_hash"] == document.content_hash
    assert "content" not in payload


def test_duplicate_returns_200_changed_false(
    monkeypatch,
) -> None:
    document = make_document()

    monkeypatch.setattr(
        KnowledgeService,
        "ingest",
        lambda self, **kwargs: KnowledgeIngestResult(
            document=document,
            changed=False,
        ),
    )

    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/admin/knowledge/documents",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["changed"] is False


def test_route_translates_empty_normalized_content(
    monkeypatch,
) -> None:
    def raise_invalid(self, **kwargs):
        raise InvalidKnowledgeContentError

    monkeypatch.setattr(
        KnowledgeService,
        "ingest",
        raise_invalid,
    )

    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/admin/knowledge/documents",
            json={
                **valid_payload(),
                "content": "   ",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Knowledge content is empty "
            "after normalization"
        )
    }


def test_route_translates_persistence_failure(
    monkeypatch,
) -> None:
    def raise_unavailable(self, **kwargs):
        raise PersistenceUnavailableError

    monkeypatch.setattr(
        KnowledgeService,
        "ingest",
        raise_unavailable,
    )

    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/admin/knowledge/documents",
            json=valid_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Persistence service unavailable"
    }


def test_source_type_is_restricted() -> None:
    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/admin/knowledge/documents",
            json={
                **valid_payload(),
                "source_type": "pdf",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_content_length_is_bounded() -> None:
    app.dependency_overrides[
        require_knowledge_manage
    ] = override_knowledge_manager
    app.dependency_overrides[get_db] = override_db

    try:
        response = client.post(
            "/admin/knowledge/documents",
            json={
                **valid_payload(),
                "content": (
                    "x"
                    * (
                        MAX_KNOWLEDGE_CONTENT_CHARS
                        + 1
                    )
                ),
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_ingest_requires_authentication() -> None:
    response = client.post(
        "/admin/knowledge/documents",
        json=valid_payload(),
    )

    assert response.status_code == 401

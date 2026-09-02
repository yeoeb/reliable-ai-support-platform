from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.errors import (
    InvalidKnowledgeContentError,
    PersistenceUnavailableError,
)
from app.models.knowledge_document import KnowledgeDocument
from app.schemas.knowledge import KnowledgeDocumentCreate
from app.services.knowledge import (
    KnowledgeService,
    hash_knowledge_content,
    normalize_knowledge_content,
)


def make_data(
    *,
    content: str = "Line 1\r\nLine 2\r",
) -> KnowledgeDocumentCreate:
    return KnowledgeDocumentCreate(
        title="Operations Runbook",
        source_type="markdown",
        source_name="runbook.md",
        content=content,
    )


def make_document(
    *,
    content: str = "Line 1\nLine 2",
) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=uuid4(),
        title="Operations Runbook",
        source_type="markdown",
        source_name="runbook.md",
        content=content,
        content_hash=hash_knowledge_content(content),
        created_by_user_id=uuid4(),
        created_at=datetime.now(timezone.utc),
    )


def test_normalize_and_hash_are_deterministic() -> None:
    normalized = normalize_knowledge_content(
        "  A\r\nB\rC  "
    )

    assert normalized == "A\nB\nC"
    assert (
        hash_knowledge_content(normalized)
        == hash_knowledge_content("A\nB\nC")
    )


@pytest.mark.parametrize(
    "content",
    ["", "   ", "\r\n\r\n"],
)
def test_normalization_rejects_empty_content(
    content: str,
) -> None:
    with pytest.raises(
        InvalidKnowledgeContentError,
    ):
        normalize_knowledge_content(content)


def test_ingest_creates_document_audit_and_one_commit() -> None:
    session = MagicMock(spec=Session)
    service = KnowledgeService(session)
    service.repository = MagicMock()
    service.audit_service = MagicMock()
    actor_user_id = uuid4()
    document = make_document()

    service.repository.get_by_source_name_and_hash.return_value = None
    service.repository.create.return_value = document

    result = service.ingest(
        actor_user_id=actor_user_id,
        data=make_data(),
    )

    assert result.document is document
    assert result.changed is True
    service.repository.create.assert_called_once_with(
        title="Operations Runbook",
        source_type="markdown",
        source_name="runbook.md",
        content="Line 1\nLine 2",
        content_hash=document.content_hash,
        created_by_user_id=actor_user_id,
    )
    service.audit_service.record.assert_called_once_with(
        actor_user_id=actor_user_id,
        action="knowledge.document.ingest",
        target_type="knowledge_document",
        target_id=str(document.id),
        outcome="success",
        event_metadata={
            "source_type": "markdown",
            "content_hash": document.content_hash,
            "content_length": len(document.content),
            "changed": True,
        },
    )
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_duplicate_returns_existing_and_audits_changed_false() -> None:
    session = MagicMock(spec=Session)
    service = KnowledgeService(session)
    service.repository = MagicMock()
    service.audit_service = MagicMock()
    document = make_document()

    service.repository.get_by_source_name_and_hash.return_value = document

    result = service.ingest(
        actor_user_id=uuid4(),
        data=make_data(),
    )

    assert result.document is document
    assert result.changed is False
    service.repository.create.assert_not_called()
    assert (
        service.audit_service.record.call_args.kwargs[
            "event_metadata"
        ]["changed"]
        is False
    )
    session.commit.assert_called_once()


def test_unique_race_recovers_existing_document() -> None:
    session = MagicMock(spec=Session)
    service = KnowledgeService(session)
    service.repository = MagicMock()
    service.audit_service = MagicMock()
    existing = make_document()

    service.repository.get_by_source_name_and_hash.side_effect = [
        None,
        existing,
    ]
    service.repository.create.side_effect = IntegrityError(
        "INSERT",
        {},
        Exception("duplicate"),
    )

    result = service.ingest(
        actor_user_id=uuid4(),
        data=make_data(),
    )

    assert result.document is existing
    assert result.changed is False
    assert (
        service.repository
        .get_by_source_name_and_hash.call_count
        == 2
    )
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_audit_failure_rolls_back_new_document() -> None:
    session = MagicMock(spec=Session)
    service = KnowledgeService(session)
    service.repository = MagicMock()
    service.audit_service = MagicMock()
    document = make_document()

    service.repository.get_by_source_name_and_hash.return_value = None
    service.repository.create.return_value = document
    service.audit_service.record.side_effect = OperationalError(
        "INSERT",
        {},
        Exception("audit unavailable"),
    )

    with pytest.raises(
        PersistenceUnavailableError,
    ):
        service.ingest(
            actor_user_id=uuid4(),
            data=make_data(),
        )

    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_repository_failure_translates_and_rolls_back() -> None:
    session = MagicMock(spec=Session)
    service = KnowledgeService(session)
    service.repository = MagicMock()
    service.audit_service = MagicMock()

    service.repository.get_by_source_name_and_hash.side_effect = (
        OperationalError(
            "SELECT",
            {},
            Exception("database unavailable"),
        )
    )

    with pytest.raises(
        PersistenceUnavailableError,
    ):
        service.ingest(
            actor_user_id=uuid4(),
            data=make_data(),
        )

    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_runtime_log_excludes_content_title_and_source_name(
    monkeypatch,
) -> None:
    session = MagicMock(spec=Session)
    service = KnowledgeService(session)
    service.repository = MagicMock()
    service.audit_service = MagicMock()
    document = make_document()
    service.repository.get_by_source_name_and_hash.return_value = document

    log_info = MagicMock()
    monkeypatch.setattr(
        "app.services.knowledge.logger.info",
        log_info,
    )

    service.ingest(
        actor_user_id=uuid4(),
        data=make_data(
            content="highly-sensitive-document-content",
        ),
    )

    kwargs = log_info.call_args.kwargs
    extra = kwargs["extra"]
    assert set(extra) == {
        "event",
        "document_id",
        "source_type",
        "content_length",
        "changed",
    }
    serialized = str(log_info.call_args)
    assert "highly-sensitive-document-content" not in serialized
    assert "Operations Runbook" not in serialized
    assert "runbook.md" not in serialized

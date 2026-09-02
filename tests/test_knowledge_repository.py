from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeDocument
from app.repositories.knowledge import KnowledgeRepository


def test_get_by_source_name_and_hash_uses_session_scalar() -> None:
    session = Mock(spec=Session)
    expected = KnowledgeDocument(
        id=uuid4(),
        title="Runbook",
        source_type="markdown",
        source_name="runbook.md",
        content="hello",
        content_hash="a" * 64,
        created_by_user_id=uuid4(),
    )
    session.scalar.return_value = expected

    repository = KnowledgeRepository(session)
    result = repository.get_by_source_name_and_hash(
        source_name="runbook.md",
        content_hash="a" * 64,
    )

    assert result is expected
    session.scalar.assert_called_once()
    session.commit.assert_not_called()


def test_create_adds_and_flushes_without_commit() -> None:
    session = Mock(spec=Session)
    repository = KnowledgeRepository(session)
    actor_user_id = uuid4()

    document = repository.create(
        title="Runbook",
        source_type="markdown",
        source_name="runbook.md",
        content="hello",
        content_hash="b" * 64,
        created_by_user_id=actor_user_id,
    )

    assert document.title == "Runbook"
    assert document.content == "hello"
    assert document.created_by_user_id == actor_user_id
    session.add.assert_called_once_with(document)
    session.flush.assert_called_once()
    session.commit.assert_not_called()

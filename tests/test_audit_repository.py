from unittest.mock import MagicMock
from uuid import uuid4

from app.repositories.audit import AuditRepository


def test_create_adds_and_flushes_without_commit() -> None:
    session = MagicMock()
    repository = AuditRepository(session)
    actor_user_id = uuid4()

    event = repository.create(
        actor_user_id=actor_user_id,
        action="auth.login",
        target_type="user",
        target_id=str(actor_user_id),
        outcome="success",
        event_metadata={},
    )

    assert event.actor_user_id == actor_user_id
    assert event.action == "auth.login"
    session.add.assert_called_once_with(event)
    session.flush.assert_called_once()
    session.commit.assert_not_called()

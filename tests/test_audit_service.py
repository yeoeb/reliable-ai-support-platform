from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.exc import OperationalError

from app.services.audit import AuditService


def test_record_participates_in_callers_transaction() -> None:
    session = MagicMock()
    service = AuditService(session)
    service.repository.create = MagicMock()

    service.record(
        actor_user_id=uuid4(),
        action="rbac.role.assign",
        target_type="user",
        target_id="target",
        outcome="success",
        event_metadata={"role": "admin"},
    )

    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_best_effort_commits_successful_audit_event() -> None:
    session = MagicMock()
    service = AuditService(session)
    service.repository.create = MagicMock()

    service.record_best_effort(
        actor_user_id=None,
        action="auth.login",
        target_type="authentication",
        target_id=None,
        outcome="failure",
        event_metadata={"reason": "invalid_credentials"},
    )

    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_best_effort_rolls_back_persistence_failure() -> None:
    session = MagicMock()
    service = AuditService(session)
    service.repository.create = MagicMock(
        side_effect=OperationalError("insert", {}, Exception())
    )

    service.record_best_effort(
        actor_user_id=None,
        action="auth.token.invalid",
        target_type="authentication",
        target_id=None,
        outcome="failure",
        event_metadata={"reason": "invalid_token"},
    )

    session.rollback.assert_called_once()
    session.commit.assert_not_called()

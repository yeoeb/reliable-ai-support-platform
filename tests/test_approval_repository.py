from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy.orm import Session

from app.repositories.approval import ApprovalRepository


def test_create_adds_and_flushes_without_commit() -> None:
    session = MagicMock(spec=Session)
    repository = ApprovalRepository(session)
    requester = uuid4()
    expires_at = datetime.now(timezone.utc)

    approval = repository.create(
        requested_by_user_id=requester,
        tool_name="grant_support_agent_role",
        tool_arguments={
            "user_id": str(uuid4()),
        },
        expires_at=expires_at,
    )

    assert approval.status == "pending"
    assert approval.requested_by_user_id == requester
    assert approval.expires_at == expires_at
    session.add.assert_called_once_with(approval)
    session.flush.assert_called_once()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_get_for_update_uses_row_lock() -> None:
    session = MagicMock(spec=Session)
    repository = ApprovalRepository(session)
    approval_id = uuid4()

    repository.get_for_update(approval_id)

    statement = session.scalar.call_args.args[0]
    assert statement._for_update_arg is not None
    session.commit.assert_not_called()
    session.rollback.assert_not_called()

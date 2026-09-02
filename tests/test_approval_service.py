from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.errors import (
    ApprovalNotFoundError,
    ApprovalPermissionDeniedError,
    ApprovalStateConflictError,
    PersistenceUnavailableError,
    ToolPermissionDeniedError,
)
from app.services.approval import (
    APPROVAL_TTL_MINUTES,
    ApprovalService,
)
from app.tools.system import build_default_tool_registry


NOW = datetime(
    2026,
    9,
    2,
    12,
    0,
    tzinfo=timezone.utc,
)


def make_approval(
    *,
    status="pending",
    expires_at=None,
):
    return SimpleNamespace(
        id=uuid4(),
        requested_by_user_id=uuid4(),
        tool_name="grant_support_agent_role",
        tool_arguments={
            "user_id": str(uuid4()),
        },
        status=status,
        created_at=NOW,
        expires_at=(
            expires_at
            or NOW + timedelta(minutes=15)
        ),
        decided_by_user_id=None,
        decided_at=None,
        executed_at=None,
    )


def make_service(monkeypatch):
    monkeypatch.setattr(
        "app.services.approval.utc_now",
        lambda: NOW,
    )
    session = MagicMock(spec=Session)
    registry = build_default_tool_registry()
    service = ApprovalService(
        session,
        registry,
    )
    service.repository = MagicMock()
    service.audit_service = MagicMock()
    service.rbac_repository = MagicMock()

    definition = registry.get(
        "grant_support_agent_role"
    )
    executor = MagicMock(
        return_value={"status": "assigned"}
    )
    object.__setattr__(
        definition,
        "approval_executor",
        executor,
    )

    return service, session, executor


def test_request_action_persists_canonical_exact_action(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    actor = uuid4()
    target = uuid4()
    approval = make_approval()
    approval.requested_by_user_id = actor
    approval.tool_arguments = {
        "user_id": str(target),
    }

    service.rbac_repository.has_permission.return_value = True
    service.repository.create.return_value = approval

    result = service.request_action(
        actor_user_id=actor,
        tool_name="grant_support_agent_role",
        arguments={"user_id": target},
    )

    assert result.status == "pending"
    service.repository.create.assert_called_once()
    kwargs = service.repository.create.call_args.kwargs
    assert kwargs["tool_name"] == (
        "grant_support_agent_role"
    )
    assert kwargs["tool_arguments"] == {
        "user_id": str(target)
    }
    assert "role_name" not in kwargs["tool_arguments"]
    assert (
        kwargs["expires_at"] - NOW
        == timedelta(
            minutes=APPROVAL_TTL_MINUTES
        )
    )
    service.audit_service.record.assert_called_once()
    assert (
        service.audit_service.record
        .call_args.kwargs["action"]
        == "approval.requested"
    )
    executor.assert_not_called()
    session.commit.assert_called_once()


def test_request_action_rechecks_action_permission(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    service.rbac_repository.has_permission.return_value = False

    with pytest.raises(
        ToolPermissionDeniedError,
    ):
        service.request_action(
            actor_user_id=uuid4(),
            tool_name="grant_support_agent_role",
            arguments={"user_id": uuid4()},
        )

    service.repository.create.assert_not_called()
    executor.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_get_reports_effective_expired_without_mutation(
    monkeypatch,
) -> None:
    service, session, _ = make_service(
        monkeypatch
    )
    approval = make_approval(
        expires_at=NOW - timedelta(seconds=1)
    )
    service.repository.get_by_id.return_value = approval

    result = service.get(
        approval_id=approval.id,
    )

    assert result.status == "expired"
    assert approval.status == "pending"
    session.rollback.assert_called_once()


def test_approve_locks_rechecks_permissions_and_executes_once(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    approval = make_approval()
    approver = uuid4()
    service.repository.get_for_update.return_value = approval
    service.rbac_repository.has_permission.side_effect = [
        True,
        True,
    ]

    result = service.approve(
        approval_id=approval.id,
        approver_user_id=approver,
    )

    service.repository.get_for_update.assert_called_once_with(
        approval.id
    )
    assert service.rbac_repository.has_permission.call_args_list[
        0
    ].args == (
        approver,
        "approval:decide",
    )
    assert service.rbac_repository.has_permission.call_args_list[
        1
    ].args == (
        approval.requested_by_user_id,
        "rbac:manage",
    )
    executor.assert_called_once()
    assert executor.call_args.args[0] is session
    assert executor.call_args.args[1] == approver
    assert approval.status == "executed"
    assert approval.decided_by_user_id == approver
    assert approval.executed_at == NOW
    assert result.status == "executed"
    assert (
        service.audit_service.record
        .call_args.kwargs["action"]
        == "approval.executed"
    )
    session.commit.assert_called_once()


def test_revoked_requester_permission_blocks_execution(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    approval = make_approval()
    service.repository.get_for_update.return_value = approval
    service.rbac_repository.has_permission.side_effect = [
        True,
        False,
    ]

    with pytest.raises(
        ApprovalPermissionDeniedError,
    ):
        service.approve(
            approval_id=approval.id,
            approver_user_id=uuid4(),
        )

    executor.assert_not_called()
    assert approval.status == "pending"
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_approver_permission_is_rechecked(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    approval = make_approval()
    service.repository.get_for_update.return_value = approval
    service.rbac_repository.has_permission.return_value = False

    with pytest.raises(
        ApprovalPermissionDeniedError,
    ):
        service.approve(
            approval_id=approval.id,
            approver_user_id=uuid4(),
        )

    executor.assert_not_called()
    session.commit.assert_not_called()


def test_already_decided_approval_cannot_execute_again(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    approval = make_approval(
        status="executed",
    )
    service.repository.get_for_update.return_value = approval
    service.rbac_repository.has_permission.return_value = True

    with pytest.raises(
        ApprovalStateConflictError,
    ):
        service.approve(
            approval_id=approval.id,
            approver_user_id=uuid4(),
        )

    executor.assert_not_called()
    session.commit.assert_not_called()


def test_expired_approval_is_persisted_and_never_executes(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    approval = make_approval(
        expires_at=NOW - timedelta(seconds=1)
    )
    service.repository.get_for_update.return_value = approval
    service.rbac_repository.has_permission.return_value = True

    with pytest.raises(
        ApprovalStateConflictError,
    ):
        service.approve(
            approval_id=approval.id,
            approver_user_id=uuid4(),
        )

    assert approval.status == "expired"
    executor.assert_not_called()
    assert (
        service.audit_service.record
        .call_args.kwargs["action"]
        == "approval.expired"
    )
    session.commit.assert_called_once()


def test_reject_never_executes_tool(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    approval = make_approval()
    approver = uuid4()
    service.repository.get_for_update.return_value = approval
    service.rbac_repository.has_permission.return_value = True

    result = service.reject(
        approval_id=approval.id,
        approver_user_id=approver,
    )

    assert result.status == "rejected"
    assert approval.status == "rejected"
    executor.assert_not_called()
    assert (
        service.audit_service.record
        .call_args.kwargs["action"]
        == "approval.rejected"
    )
    session.commit.assert_called_once()


def test_audit_failure_rolls_back_approval_and_action_transaction(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    approval = make_approval()
    service.repository.get_for_update.return_value = approval
    service.rbac_repository.has_permission.return_value = True
    service.audit_service.record.side_effect = OperationalError(
        "INSERT",
        {},
        Exception("audit unavailable"),
    )

    with pytest.raises(
        PersistenceUnavailableError,
    ):
        service.approve(
            approval_id=approval.id,
            approver_user_id=uuid4(),
        )

    executor.assert_called_once()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_lock_database_failure_translates_to_persistence_error(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    service.repository.get_for_update.side_effect = OperationalError(
        "SELECT",
        {},
        Exception("database unavailable"),
    )

    with pytest.raises(
        PersistenceUnavailableError,
    ):
        service.approve(
            approval_id=uuid4(),
            approver_user_id=uuid4(),
        )

    executor.assert_not_called()
    session.rollback.assert_called_once()


def test_missing_approval_is_not_found(
    monkeypatch,
) -> None:
    service, session, executor = make_service(
        monkeypatch
    )
    service.repository.get_for_update.return_value = None

    with pytest.raises(
        ApprovalNotFoundError,
    ):
        service.approve(
            approval_id=uuid4(),
            approver_user_id=uuid4(),
        )

    executor.assert_not_called()
    session.rollback.assert_called_once()

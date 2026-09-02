from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.errors import (
    InvalidToolArgumentsError,
    ToolExecutionError,
    ToolPermissionDeniedError,
    UnknownToolError,
)
from app.services.tool_execution import ToolExecutionService
from app.tools.system import build_default_tool_registry


def make_service(monkeypatch, allowed=True):
    session = MagicMock(spec=Session)
    permission = MagicMock()
    permission.has_permission.return_value = allowed
    monkeypatch.setattr(
        "app.services.tool_execution.RBACRepository",
        lambda session: permission,
    )
    service = ToolExecutionService(
        session,
        build_default_tool_registry(),
    )
    service.audit_service = MagicMock()
    return service, session, permission


def test_execution_rechecks_permission_and_closes_transaction(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.tools.system.check_database_connection",
        lambda: None,
    )
    service, session, permission = make_service(
        monkeypatch,
        allowed=True,
    )
    result = service.execute(
        actor_user_id=uuid4(),
        tool_name="platform_readiness",
        arguments={},
    )
    assert result["status"] in {"ready", "unavailable"}
    permission.has_permission.assert_called_once()
    session.rollback.assert_called_once()
    metadata = (
        service.audit_service.record_best_effort
        .call_args.kwargs["event_metadata"]
    )
    assert set(metadata) == {
        "tool_name",
        "risk_level",
        "result_status",
    }


def test_revoked_permission_prevents_executor(
    monkeypatch,
) -> None:
    service, session, _ = make_service(
        monkeypatch,
        allowed=False,
    )
    definition = service.registry.get(
        "platform_readiness"
    )
    executor = MagicMock()
    object.__setattr__(definition, "executor", executor)

    with pytest.raises(ToolPermissionDeniedError):
        service.execute(
            actor_user_id=uuid4(),
            tool_name="platform_readiness",
            arguments={},
        )

    executor.assert_not_called()
    session.rollback.assert_called_once()


def test_extra_arguments_fail_before_permission_or_execution(
    monkeypatch,
) -> None:
    service, session, permission = make_service(
        monkeypatch,
        allowed=True,
    )
    with pytest.raises(InvalidToolArgumentsError):
        service.execute(
            actor_user_id=uuid4(),
            tool_name="platform_readiness",
            arguments={"command": "whoami"},
        )
    permission.has_permission.assert_not_called()
    session.rollback.assert_not_called()


def test_unknown_tool_fails_closed(monkeypatch) -> None:
    service, _, permission = make_service(
        monkeypatch,
        allowed=True,
    )
    with pytest.raises(UnknownToolError):
        service.execute(
            actor_user_id=uuid4(),
            tool_name="shell",
            arguments={},
        )
    permission.has_permission.assert_not_called()



def test_direct_executor_refuses_approval_required_tool(
    monkeypatch,
) -> None:
    service, session, permission = make_service(
        monkeypatch,
        allowed=True,
    )
    definition = service.registry.get(
        "grant_support_agent_role"
    )
    approval_executor = MagicMock()
    object.__setattr__(
        definition,
        "approval_executor",
        approval_executor,
    )

    with pytest.raises(
        ToolExecutionError,
        match="cannot execute directly",
    ):
        service.execute(
            actor_user_id=uuid4(),
            tool_name="grant_support_agent_role",
            arguments={"user_id": str(uuid4())},
        )

    permission.has_permission.assert_not_called()
    approval_executor.assert_not_called()
    session.rollback.assert_not_called()

from unittest.mock import MagicMock
from uuid import uuid4

from app.tools.rbac import (
    GrantSupportAgentRoleArguments,
    grant_support_agent_role,
)


def test_fixed_approval_tool_can_only_grant_support_agent(
    monkeypatch,
) -> None:
    service = MagicMock()
    service.assign_role_in_transaction.return_value = True
    monkeypatch.setattr(
        "app.tools.rbac.RBACService",
        lambda session: service,
    )
    session = object()
    actor = uuid4()
    target = uuid4()

    result = grant_support_agent_role(
        session,
        actor,
        GrantSupportAgentRoleArguments(
            user_id=target
        ),
    )

    service.assign_role_in_transaction.assert_called_once_with(
        actor_user_id=actor,
        user_id=target,
        role_name="support_agent",
    )
    assert result == {"status": "assigned"}


def test_fixed_approval_tool_reports_already_assigned(
    monkeypatch,
) -> None:
    service = MagicMock()
    service.assign_role_in_transaction.return_value = False
    monkeypatch.setattr(
        "app.tools.rbac.RBACService",
        lambda session: service,
    )

    result = grant_support_agent_role(
        object(),
        uuid4(),
        GrantSupportAgentRoleArguments(
            user_id=uuid4()
        ),
    )

    assert result == {
        "status": "already_assigned"
    }

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NoAuthorizedToolError
from app.integrations.llm import (
    ToolCallRequest,
    ToolChoiceResult,
    ToolFinalResult,
)
from app.services.agent import AgentService
from app.tools.system import build_default_tool_registry


def make_service(monkeypatch, permissions):
    session = MagicMock(spec=Session)
    authorization = MagicMock()
    authorization.get_effective_permissions.return_value = permissions
    monkeypatch.setattr(
        "app.services.agent.AuthorizationService",
        lambda repo: authorization,
    )
    provider = MagicMock()
    service = AgentService(
        session,
        build_default_tool_registry(),
        provider,
    )
    service.tool_execution = MagicMock()
    return service, session, provider


def test_no_authorized_tool_denies_before_provider(
    monkeypatch,
) -> None:
    service, session, provider = make_service(
        monkeypatch,
        set(),
    )
    with pytest.raises(NoAuthorizedToolError):
        service.run(
            actor_user_id=uuid4(),
            request="check",
        )
    provider.choose.assert_not_called()
    session.rollback.assert_called_once()


def test_provider_sees_only_authorized_registry_tools(
    monkeypatch,
) -> None:
    service, session, provider = make_service(
        monkeypatch,
        {"system:read"},
    )
    provider.choose.return_value = ToolChoiceResult(
        answer="No tool needed.",
        tool_call=None,
        input_tokens=2,
        output_tokens=2,
        model="gpt-5.6-terra",
    )

    result = service.run(
        actor_user_id=uuid4(),
        request="hello",
    )

    specs = provider.choose.call_args.kwargs["tools"]
    assert [item.name for item in specs] == [
        "platform_readiness"
    ]
    session.rollback.assert_called_once()
    assert result.tool_used is None


def test_agent_executes_at_most_one_tool_and_finalizes_without_loop(
    monkeypatch,
) -> None:
    service, _, provider = make_service(
        monkeypatch,
        {"system:read"},
    )
    provider.choose.return_value = ToolChoiceResult(
        answer=None,
        tool_call=ToolCallRequest(
            name="platform_readiness",
            arguments={},
        ),
        input_tokens=2,
        output_tokens=1,
        model="gpt-5.6-terra",
    )
    service.tool_execution.execute.return_value = {
        "status": "ready"
    }
    provider.finalize.return_value = ToolFinalResult(
        answer="The platform is ready.",
        input_tokens=3,
        output_tokens=2,
        model="gpt-5.6-terra",
    )

    result = service.run(
        actor_user_id=uuid4(),
        request="check readiness",
    )

    service.tool_execution.execute.assert_called_once()
    provider.choose.assert_called_once()
    provider.finalize.assert_called_once()
    assert result.tool_used == "platform_readiness"
    assert result.tool_status == "ready"
    assert result.input_tokens == 5
    assert result.output_tokens == 3



def test_approval_required_tool_creates_pending_action_without_execution(
    monkeypatch,
) -> None:
    service, session, provider = make_service(
        monkeypatch,
        {"rbac:manage"},
    )
    target = uuid4()
    approval_id = uuid4()
    provider.choose.return_value = ToolChoiceResult(
        answer=None,
        tool_call=ToolCallRequest(
            name="grant_support_agent_role",
            arguments={
                "user_id": str(target),
            },
        ),
        input_tokens=4,
        output_tokens=2,
        model="gpt-5.6-terra",
    )
    service.approval_service = MagicMock()
    service.approval_service.request_action.return_value = (
        SimpleNamespace(id=approval_id)
    )

    result = service.run(
        actor_user_id=uuid4(),
        request="Make this user support staff.",
    )

    service.approval_service.request_action.assert_called_once()
    service.tool_execution.execute.assert_not_called()
    provider.finalize.assert_not_called()

    assert result.status == "approval_required"
    assert result.approval_id == approval_id
    assert result.answer == "Human approval required."
    assert result.tool_used == "grant_support_agent_role"
    assert result.tool_status == "approval_required"
    assert result.input_tokens == 4
    assert result.output_tokens == 2


def test_read_only_tool_path_remains_completed(
    monkeypatch,
) -> None:
    service, _, provider = make_service(
        monkeypatch,
        {"system:read"},
    )
    provider.choose.return_value = ToolChoiceResult(
        answer=None,
        tool_call=ToolCallRequest(
            name="platform_readiness",
            arguments={},
        ),
        input_tokens=2,
        output_tokens=1,
        model="gpt-5.6-terra",
    )
    service.tool_execution.execute.return_value = {
        "status": "ready"
    }
    provider.finalize.return_value = ToolFinalResult(
        answer="Ready.",
        input_tokens=1,
        output_tokens=1,
        model="gpt-5.6-terra",
    )

    result = service.run(
        actor_user_id=uuid4(),
        request="Check readiness",
    )

    assert result.status == "completed"
    assert result.approval_id is None
    provider.finalize.assert_called_once()

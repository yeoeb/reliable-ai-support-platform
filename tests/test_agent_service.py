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

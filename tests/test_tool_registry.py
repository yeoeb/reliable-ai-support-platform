import pytest
from pydantic import BaseModel, ConfigDict

from app.core.errors import UnknownToolError
from app.tools.registry import ToolDefinition, ToolRegistry
from app.tools.system import (
    PlatformReadinessArguments,
    build_default_tool_registry,
)


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def noop(_: BaseModel) -> dict[str, str]:
    return {"status": "ready"}


def definition(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="test",
        required_permission="system:read",
        risk_level="read_only",
        arguments_model=EmptyArgs,
        executor=noop,
    )


def test_default_registry_exposes_only_platform_readiness() -> None:
    registry = build_default_tool_registry()

    allowed = registry.authorized_for_permissions(
        {"system:read"}
    )
    assert [item.name for item in allowed] == [
        "platform_readiness"
    ]
    spec = allowed[0].provider_spec()
    assert spec.parameters["properties"] == {}
    assert spec.parameters["required"] == []
    assert spec.parameters["additionalProperties"] is False
    assert (
        allowed[0].arguments_model
        is PlatformReadinessArguments
    )


def test_registry_filters_by_permission() -> None:
    registry = build_default_tool_registry()
    assert registry.authorized_for_permissions(set()) == []


def test_registry_rejects_duplicate_names() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        ToolRegistry(
            [
                definition("same"),
                definition("same"),
            ]
        )


def test_registry_unknown_name_fails_closed() -> None:
    registry = build_default_tool_registry()
    with pytest.raises(UnknownToolError):
        registry.get("shell")



def test_registry_exposes_fixed_approval_tool_without_role_argument() -> None:
    registry = build_default_tool_registry()

    allowed = registry.authorized_for_permissions(
        {"rbac:manage"}
    )

    assert [item.name for item in allowed] == [
        "grant_support_agent_role"
    ]
    definition = allowed[0]
    assert definition.risk_level == "approval_required"
    assert definition.executor is None
    assert definition.approval_executor is not None

    spec = definition.provider_spec()
    assert set(
        spec.parameters["properties"]
    ) == {"user_id"}
    assert "role_name" not in spec.parameters["properties"]
    assert spec.parameters["additionalProperties"] is False


def test_registry_rejects_executor_on_approval_required_tool() -> None:
    with pytest.raises(
        ValueError,
        match="approval_executor",
    ):
        ToolRegistry(
            [
                ToolDefinition(
                    name="unsafe",
                    description="unsafe",
                    required_permission="rbac:manage",
                    risk_level="approval_required",
                    arguments_model=EmptyArgs,
                    executor=noop,
                )
            ]
        )


def test_registry_rejects_approval_executor_on_read_only_tool() -> None:
    def approval_executor(session, actor, args):
        return {"status": "assigned"}

    with pytest.raises(
        ValueError,
        match="executor only",
    ):
        ToolRegistry(
            [
                ToolDefinition(
                    name="unsafe",
                    description="unsafe",
                    required_permission="system:read",
                    risk_level="read_only",
                    arguments_model=EmptyArgs,
                    approval_executor=approval_executor,
                )
            ]
        )

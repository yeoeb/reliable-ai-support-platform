from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import check_database_connection
from app.tools.rbac import (
    GrantSupportAgentRoleArguments,
    grant_support_agent_role,
)
from app.tools.registry import ToolDefinition, ToolRegistry


class PlatformReadinessArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


def platform_readiness(
    _: PlatformReadinessArguments,
) -> dict[str, str]:
    try:
        check_database_connection()
    except SQLAlchemyError:
        return {"status": "unavailable"}
    return {"status": "ready"}


def build_default_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ToolDefinition(
                name="platform_readiness",
                description=(
                    "Check whether the platform database "
                    "dependency is reachable."
                ),
                required_permission="system:read",
                risk_level="read_only",
                arguments_model=PlatformReadinessArguments,
                executor=platform_readiness,
            ),
            ToolDefinition(
                name="grant_support_agent_role",
                description=(
                    "Propose granting the fixed support_agent "
                    "role to one user. Human approval is required."
                ),
                required_permission="rbac:manage",
                risk_level="approval_required",
                arguments_model=GrantSupportAgentRoleArguments,
                approval_executor=grant_support_agent_role,
            ),
        ]
    )

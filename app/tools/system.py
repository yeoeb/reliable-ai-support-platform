from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import check_database_connection
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
            )
        ]
    )

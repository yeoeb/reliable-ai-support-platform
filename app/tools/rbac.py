from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.services.rbac import RBACService


class GrantSupportAgentRoleArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID


def grant_support_agent_role(
    session: Session,
    actor_user_id: UUID,
    arguments: BaseModel,
) -> dict[str, str]:
    validated = GrantSupportAgentRoleArguments.model_validate(
        arguments.model_dump()
    )

    created = RBACService(
        session
    ).assign_role_in_transaction(
        actor_user_id=actor_user_id,
        user_id=validated.user_id,
        role_name="support_agent",
    )

    return {
        "status": (
            "assigned"
            if created
            else "already_assigned"
        )
    }

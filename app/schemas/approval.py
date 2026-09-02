from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApprovalRead(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
    )

    id: UUID
    requested_by_user_id: UUID
    tool_name: str
    tool_arguments: dict[str, object]
    status: Literal[
        "pending",
        "rejected",
        "executed",
        "expired",
    ]
    created_at: datetime
    expires_at: datetime
    decided_by_user_id: UUID | None
    decided_at: datetime | None
    executed_at: datetime | None

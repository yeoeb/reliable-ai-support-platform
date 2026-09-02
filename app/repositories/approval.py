from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.approval_request import ApprovalRequest


class ApprovalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        requested_by_user_id: UUID,
        tool_name: str,
        tool_arguments: dict[str, Any],
        expires_at: datetime,
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            requested_by_user_id=requested_by_user_id,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            status="pending",
            expires_at=expires_at,
        )
        self.session.add(approval)
        self.session.flush()
        return approval

    def get_by_id(
        self,
        approval_id: UUID,
    ) -> ApprovalRequest | None:
        statement = select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id
        )
        return self.session.scalar(statement)

    def get_for_update(
        self,
        approval_id: UUID,
    ) -> ApprovalRequest | None:
        statement = (
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .with_for_update()
        )
        return self.session.scalar(statement)

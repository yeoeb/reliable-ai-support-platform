from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import (
    ApprovalNotFoundError,
    ApprovalPermissionDeniedError,
    ApprovalStateConflictError,
    InvalidToolArgumentsError,
    PersistenceUnavailableError,
    RoleNotFoundError,
    ToolExecutionError,
    ToolPermissionDeniedError,
    UnknownToolError,
    UserNotFoundError,
)
from app.models.approval_request import ApprovalRequest
from app.repositories.approval import ApprovalRepository
from app.repositories.rbac import RBACRepository
from app.services.audit import AuditService
from app.tools.registry import ToolDefinition, ToolRegistry


logger = logging.getLogger(__name__)

APPROVAL_TTL_MINUTES = 15


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ApprovalSnapshot:
    id: UUID
    requested_by_user_id: UUID
    tool_name: str
    tool_arguments: dict[str, Any]
    status: str
    created_at: datetime
    expires_at: datetime
    decided_by_user_id: UUID | None
    decided_at: datetime | None
    executed_at: datetime | None


class ApprovalService:
    def __init__(
        self,
        session: Session,
        registry: ToolRegistry,
    ) -> None:
        self.session = session
        self.registry = registry
        self.repository = ApprovalRepository(session)
        self.audit_service = AuditService(session)
        self.rbac_repository = RBACRepository(session)

    def _snapshot(
        self,
        approval: ApprovalRequest,
        *,
        status: str | None = None,
    ) -> ApprovalSnapshot:
        return ApprovalSnapshot(
            id=approval.id,
            requested_by_user_id=approval.requested_by_user_id,
            tool_name=approval.tool_name,
            tool_arguments=dict(approval.tool_arguments),
            status=status or approval.status,
            created_at=approval.created_at,
            expires_at=approval.expires_at,
            decided_by_user_id=approval.decided_by_user_id,
            decided_at=approval.decided_at,
            executed_at=approval.executed_at,
        )

    def _safe_metadata(
        self,
        *,
        approval: ApprovalRequest,
        definition: ToolDefinition,
        result_status: str | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "approval_id": str(approval.id),
            "tool_name": definition.name,
            "risk_level": definition.risk_level,
        }
        target_user_id = approval.tool_arguments.get(
            "user_id"
        )
        if isinstance(target_user_id, str):
            metadata["target_user_id"] = target_user_id
        if result_status is not None:
            metadata["result_status"] = result_status
        return metadata

    def _validate_pending_definition(
        self,
        approval: ApprovalRequest,
    ) -> tuple[ToolDefinition, Any]:
        try:
            definition = self.registry.get(
                approval.tool_name
            )
        except UnknownToolError as exc:
            raise ApprovalStateConflictError(
                "Pending Tool no longer exists"
            ) from exc

        if (
            definition.risk_level != "approval_required"
            or definition.approval_executor is None
        ):
            raise ApprovalStateConflictError(
                "Pending Tool is not approval-required"
            )

        try:
            validated = definition.arguments_model.model_validate(
                approval.tool_arguments
            )
        except ValidationError as exc:
            raise ApprovalStateConflictError(
                "Pending Tool arguments are invalid"
            ) from exc

        return definition, validated

    def _require_decider_permission(
        self,
        user_id: UUID,
    ) -> None:
        if not self.rbac_repository.has_permission(
            user_id,
            "approval:decide",
        ):
            raise ApprovalPermissionDeniedError

    def _require_requester_action_permission(
        self,
        *,
        approval: ApprovalRequest,
        definition: ToolDefinition,
    ) -> None:
        if not self.rbac_repository.has_permission(
            approval.requested_by_user_id,
            definition.required_permission,
        ):
            raise ApprovalPermissionDeniedError

    def request_action(
        self,
        *,
        actor_user_id: UUID,
        tool_name: str,
        arguments: dict[str, object],
    ) -> ApprovalSnapshot:
        definition = self.registry.get(tool_name)

        if (
            definition.risk_level != "approval_required"
            or definition.approval_executor is None
        ):
            raise ToolExecutionError(
                "Tool does not require approval"
            )

        try:
            validated = definition.arguments_model.model_validate(
                arguments
            )
        except ValidationError as exc:
            raise InvalidToolArgumentsError(
                "Tool arguments are invalid"
            ) from exc

        allowed = self.rbac_repository.has_permission(
            actor_user_id,
            definition.required_permission,
        )

        if not allowed:
            self.session.rollback()
            raise ToolPermissionDeniedError(
                "Tool permission denied"
            )

        canonical_arguments = validated.model_dump(
            mode="json"
        )
        now = utc_now()

        try:
            approval = self.repository.create(
                requested_by_user_id=actor_user_id,
                tool_name=definition.name,
                tool_arguments=canonical_arguments,
                expires_at=now
                + timedelta(
                    minutes=APPROVAL_TTL_MINUTES
                ),
            )
            self.audit_service.record(
                actor_user_id=actor_user_id,
                action="approval.requested",
                target_type="approval",
                target_id=str(approval.id),
                outcome="success",
                event_metadata=self._safe_metadata(
                    approval=approval,
                    definition=definition,
                ),
            )
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise PersistenceUnavailableError from exc

        logger.info(
            "Human approval requested",
            extra={
                "event": "approval.requested",
                **self._safe_metadata(
                    approval=approval,
                    definition=definition,
                ),
            },
        )
        return self._snapshot(approval)

    def get(
        self,
        *,
        approval_id: UUID,
    ) -> ApprovalSnapshot:
        approval = self.repository.get_by_id(
            approval_id
        )
        if approval is None:
            self.session.rollback()
            raise ApprovalNotFoundError

        effective_status = approval.status
        if (
            approval.status == "pending"
            and utc_now() >= approval.expires_at
        ):
            effective_status = "expired"

        snapshot = self._snapshot(
            approval,
            status=effective_status,
        )
        self.session.rollback()
        return snapshot

    def _expire_locked(
        self,
        *,
        approval: ApprovalRequest,
        actor_user_id: UUID,
        definition: ToolDefinition,
        now: datetime,
    ) -> None:
        approval.status = "expired"
        approval.decided_at = now
        self.audit_service.record(
            actor_user_id=actor_user_id,
            action="approval.expired",
            target_type="approval",
            target_id=str(approval.id),
            outcome="success",
            event_metadata=self._safe_metadata(
                approval=approval,
                definition=definition,
            ),
        )
        self.session.commit()

        logger.info(
            "Human approval expired",
            extra={
                "event": "approval.expired",
                **self._safe_metadata(
                    approval=approval,
                    definition=definition,
                ),
            },
        )

    def approve(
        self,
        *,
        approval_id: UUID,
        approver_user_id: UUID,
    ) -> ApprovalSnapshot:
        approval = self.repository.get_for_update(
            approval_id
        )
        if approval is None:
            self.session.rollback()
            raise ApprovalNotFoundError

        try:
            self._require_decider_permission(
                approver_user_id
            )

            if approval.status != "pending":
                raise ApprovalStateConflictError

            definition, validated = (
                self._validate_pending_definition(
                    approval
                )
            )
            now = utc_now()

            if now >= approval.expires_at:
                self._expire_locked(
                    approval=approval,
                    actor_user_id=approver_user_id,
                    definition=definition,
                    now=now,
                )
                raise ApprovalStateConflictError

            self._require_requester_action_permission(
                approval=approval,
                definition=definition,
            )

            executor = definition.approval_executor
            if executor is None:
                raise ApprovalStateConflictError

            try:
                result = executor(
                    self.session,
                    approver_user_id,
                    validated,
                )
            except (
                UserNotFoundError,
                RoleNotFoundError,
            ) as exc:
                raise ApprovalStateConflictError(
                    "Pending action target is no longer valid"
                ) from exc

            if (
                not isinstance(result, dict)
                or set(result) != {"status"}
                or result["status"]
                not in {
                    "assigned",
                    "already_assigned",
                }
            ):
                raise ToolExecutionError(
                    "Approval Tool returned invalid result"
                )

            approval.status = "executed"
            approval.decided_by_user_id = (
                approver_user_id
            )
            approval.decided_at = now
            approval.executed_at = now

            self.audit_service.record(
                actor_user_id=approver_user_id,
                action="approval.executed",
                target_type="approval",
                target_id=str(approval.id),
                outcome="success",
                event_metadata=self._safe_metadata(
                    approval=approval,
                    definition=definition,
                    result_status=result["status"],
                ),
            )

            self.session.commit()

        except (
            ApprovalPermissionDeniedError,
            ApprovalStateConflictError,
            ToolExecutionError,
        ):
            self.session.rollback()
            raise
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise PersistenceUnavailableError from exc

        logger.info(
            "Human approval executed",
            extra={
                "event": "approval.executed",
                **self._safe_metadata(
                    approval=approval,
                    definition=definition,
                    result_status=result["status"],
                ),
            },
        )
        return self._snapshot(approval)

    def reject(
        self,
        *,
        approval_id: UUID,
        approver_user_id: UUID,
    ) -> ApprovalSnapshot:
        approval = self.repository.get_for_update(
            approval_id
        )
        if approval is None:
            self.session.rollback()
            raise ApprovalNotFoundError

        try:
            self._require_decider_permission(
                approver_user_id
            )

            if approval.status != "pending":
                raise ApprovalStateConflictError

            definition, _ = (
                self._validate_pending_definition(
                    approval
                )
            )
            now = utc_now()

            if now >= approval.expires_at:
                self._expire_locked(
                    approval=approval,
                    actor_user_id=approver_user_id,
                    definition=definition,
                    now=now,
                )
                raise ApprovalStateConflictError

            approval.status = "rejected"
            approval.decided_by_user_id = (
                approver_user_id
            )
            approval.decided_at = now

            self.audit_service.record(
                actor_user_id=approver_user_id,
                action="approval.rejected",
                target_type="approval",
                target_id=str(approval.id),
                outcome="success",
                event_metadata=self._safe_metadata(
                    approval=approval,
                    definition=definition,
                ),
            )
            self.session.commit()

        except (
            ApprovalPermissionDeniedError,
            ApprovalStateConflictError,
        ):
            self.session.rollback()
            raise
        except SQLAlchemyError as exc:
            self.session.rollback()
            raise PersistenceUnavailableError from exc

        logger.info(
            "Human approval rejected",
            extra={
                "event": "approval.rejected",
                **self._safe_metadata(
                    approval=approval,
                    definition=definition,
                ),
            },
        )
        return self._snapshot(approval)

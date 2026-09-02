from __future__ import annotations

import logging
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import (
    InvalidToolArgumentsError,
    ToolExecutionError,
    ToolPermissionDeniedError,
)
from app.repositories.rbac import RBACRepository
from app.services.audit import AuditService
from app.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)


class ToolExecutionService:
    def __init__(
        self,
        session: Session,
        registry: ToolRegistry,
    ) -> None:
        self.session = session
        self.registry = registry
        self.audit_service = AuditService(session)

    def execute(
        self,
        *,
        actor_user_id: UUID,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, str]:
        definition = self.registry.get(tool_name)

        if (
            definition.risk_level != "read_only"
            or definition.executor is None
        ):
            raise ToolExecutionError(
                "Approval-required Tool cannot execute directly"
            )

        try:
            validated = definition.arguments_model.model_validate(
                arguments
            )
        except ValidationError as exc:
            raise InvalidToolArgumentsError(
                "Tool arguments are invalid"
            ) from exc

        repository = RBACRepository(self.session)
        allowed = repository.has_permission(
            actor_user_id,
            definition.required_permission,
        )
        self.session.rollback()

        if not allowed:
            raise ToolPermissionDeniedError(
                "Tool permission denied"
            )

        try:
            result = definition.executor(validated)
        except Exception as exc:
            raise ToolExecutionError(
                "Tool execution failed"
            ) from exc

        if (
            not isinstance(result, dict)
            or set(result) != {"status"}
            or not isinstance(result["status"], str)
            or result["status"]
            not in {"ready", "unavailable"}
        ):
            raise ToolExecutionError(
                "Tool returned invalid result"
            )

        metadata = {
            "tool_name": definition.name,
            "risk_level": definition.risk_level,
            "result_status": result["status"],
        }
        self.audit_service.record_best_effort(
            actor_user_id=actor_user_id,
            action="tool.execute",
            target_type="tool",
            target_id=definition.name,
            outcome="success",
            event_metadata=metadata,
        )
        logger.info(
            "Read-only tool executed",
            extra={
                "event": "tool.execute.completed",
                **metadata,
            },
        )
        return result

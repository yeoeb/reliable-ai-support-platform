import logging
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.repositories.audit import AuditRepository


logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AuditRepository(session)

    def record(
        self,
        *,
        actor_user_id: UUID | None,
        action: str,
        target_type: str,
        target_id: str | None,
        outcome: str,
        event_metadata: dict[str, Any],
    ) -> AuditEvent:
        return self.repository.create(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            event_metadata=event_metadata,
        )

    def record_best_effort(self, **kwargs: Any) -> None:
        try:
            self.record(**kwargs)
            self.session.commit()
        except SQLAlchemyError:
            self.session.rollback()
            logger.error(
                "event=audit.persistence_failure action=%s",
                kwargs.get("action"),
            )

import logging
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import (
    PersistenceUnavailableError,
    RoleNotFoundError,
    UserNotFoundError,
)
from app.repositories.rbac import RBACRepository
from app.repositories.user import UserRepository
from app.services.audit import AuditService


logger = logging.getLogger(__name__)


class RBACService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.rbac_repository = RBACRepository(session)
        self.user_repository = UserRepository(session)
        self.audit_service = AuditService(session)

    def assign_role_in_transaction(
        self,
        *,
        actor_user_id: UUID,
        user_id: UUID,
        role_name: str,
    ) -> bool:
        user = self.user_repository.get_by_id(user_id)

        if user is None:
            raise UserNotFoundError

        role = self.rbac_repository.get_role_by_name(
            role_name
        )

        if role is None:
            raise RoleNotFoundError

        created = self.rbac_repository.assign_role(
            user_id=user.id,
            role_id=role.id,
        )

        self.audit_service.record(
            actor_user_id=actor_user_id,
            action="rbac.role.assign",
            target_type="user",
            target_id=str(user.id),
            outcome="success",
            event_metadata={
                "role": role.name,
                "changed": created,
            },
        )

        return created

    def assign_role(
        self,
        *,
        actor_user_id: UUID,
        user_id: UUID,
        role_name: str,
    ) -> None:
        try:
            created = self.assign_role_in_transaction(
                actor_user_id=actor_user_id,
                user_id=user_id,
                role_name=role_name,
            )

            self.session.commit()

            logger.info(
                "RBAC role assigned",
                extra={
                    "event": "rbac.role.assigned",
                    "user_id": str(user_id),
                    "role": role_name,
                    "changed": created,
                },
            )

        except (
            UserNotFoundError,
            RoleNotFoundError,
        ):
            self.session.rollback()
            raise

        except SQLAlchemyError as exc:
            self.session.rollback()

            logger.error(
                "RBAC role assignment persistence failed",
                extra={
                    "event": "rbac.role.assign.persistence_failure",
                    "user_id": str(user_id),
                    "role": role_name,
                },
            )

            raise PersistenceUnavailableError from exc

    def remove_role(
        self,
        *,
        actor_user_id: UUID,
        user_id: UUID,
        role_name: str,
    ) -> None:
        try:
            user = self.user_repository.get_by_id(user_id)

            if user is None:
                raise UserNotFoundError

            role = self.rbac_repository.get_role_by_name(
                role_name
            )

            if role is None:
                raise RoleNotFoundError

            removed = self.rbac_repository.remove_role(
                user_id=user.id,
                role_id=role.id,
            )

            self.audit_service.record(
                actor_user_id=actor_user_id,
                action="rbac.role.remove",
                target_type="user",
                target_id=str(user.id),
                outcome="success",
                event_metadata={
                    "role": role.name,
                    "changed": removed,
                },
            )

            self.session.commit()

            logger.info(
                "RBAC role removed",
                extra={
                    "event": "rbac.role.removed",
                    "user_id": str(user.id),
                    "role": role.name,
                    "changed": removed,
                },
            )

        except (
            UserNotFoundError,
            RoleNotFoundError,
        ):
            self.session.rollback()
            raise

        except SQLAlchemyError as exc:
            self.session.rollback()

            logger.error(
                "RBAC role removal persistence failed",
                extra={
                    "event": "rbac.role.remove.persistence_failure",
                    "user_id": str(user_id),
                    "role": role_name,
                },
            )

            raise PersistenceUnavailableError from exc

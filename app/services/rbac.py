import logging
from uuid import UUID

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.errors import (
    PersistenceUnavailableError,
    RoleNotFoundError,
    UserNotFoundError,
)
from app.repositories.rbac import RBACRepository
from app.repositories.user import UserRepository


logger = logging.getLogger(__name__)


class RBACService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.rbac_repository = RBACRepository(session)
        self.user_repository = UserRepository(session)

    def assign_role(
        self,
        *,
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

            created = self.rbac_repository.assign_role(
                user_id=user.id,
                role_id=role.id,
            )

            self.session.commit()

            logger.info(
                "event=rbac.role.assigned "
                "user_id=%s role=%s changed=%s",
                user.id,
                role.name,
                created,
            )

        except (
            UserNotFoundError,
            RoleNotFoundError,
        ):
            self.session.rollback()
            raise

        except OperationalError as exc:
            self.session.rollback()

            logger.error(
                "event=rbac.role.assign.persistence_failure "
                "user_id=%s role=%s",
                user_id,
                role_name,
            )

            raise PersistenceUnavailableError from exc

    def remove_role(
        self,
        *,
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

            self.session.commit()

            logger.info(
                "event=rbac.role.removed "
                "user_id=%s role=%s changed=%s",
                user.id,
                role.name,
                removed,
            )

        except (
            UserNotFoundError,
            RoleNotFoundError,
        ):
            self.session.rollback()
            raise

        except OperationalError as exc:
            self.session.rollback()

            logger.error(
                "event=rbac.role.remove.persistence_failure "
                "user_id=%s role=%s",
                user_id,
                role_name,
            )

            raise PersistenceUnavailableError from exc
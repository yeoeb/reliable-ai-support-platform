import logging

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.errors import (
    DefaultRoleNotConfiguredError,
    PersistenceUnavailableError,
    UserAlreadyExistsError,
)
from app.core.security import hash_password
from app.models.user import User
from app.repositories.rbac import RBACRepository
from app.repositories.user import UserRepository
from app.repositories.user_credential import UserCredentialRepository
from app.schemas.user import UserCreate


logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = UserRepository(session)
        self.credential_repository = UserCredentialRepository(session)
        self.rbac_repository = RBACRepository(session)
    
    def create_user(self, data: UserCreate) -> User:
        try:
            password_hash = hash_password(data.password)

            try:
                user = self.repository.create(
                    email=str(data.email),
                    display_name=data.display_name,
                )
            except IntegrityError as exc:
                logger.warning("event=user.create.conflict")
                raise UserAlreadyExistsError from exc

            self.credential_repository.create(
                user_id=user.id,
                password_hash=password_hash,
            )

            default_role = self.rbac_repository.get_role_by_name("user")

            if default_role is None:
                raise DefaultRoleNotConfiguredError(
                    "Default role 'user' is not configured"
                )

            self.rbac_repository.assign_role(
                user_id=user.id,
                role_id=default_role.id,
            )

            self.session.commit()
            self.session.refresh(user)

            logger.info(
                "event=user.create.succeeded user_id=%s",
                user.id,
            )

            return user

        except UserAlreadyExistsError:
            self.session.rollback()
            raise

        except DefaultRoleNotConfiguredError:
            self.session.rollback()

            logger.error(
                "event=user.create.default_role_missing"
            )

            raise

        except OperationalError as exc:
            self.session.rollback()

            logger.error(
                "event=user.create.persistence_failure"
            )

            raise PersistenceUnavailableError from exc

        except IntegrityError:
            self.session.rollback()

            logger.error(
                "event=user.create.role_assignment_failed"
            )

            raise

    def list_users(self) -> list[User]:
        try:
            return self.repository.list_all()

        except OperationalError as exc:
            logger.error(
                "event=user.list.persistence_failure"
            )

            raise PersistenceUnavailableError from exc
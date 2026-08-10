from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.errors import (
    PersistenceUnavailableError,
    UserAlreadyExistsError,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate

import logging


logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = UserRepository(session)

    def create_user(self, data: UserCreate) -> User:
        try:
            user = self.repository.create(
                email=str(data.email),
                display_name=data.display_name,
            )

            self.session.commit()
            self.session.refresh(user)

            logger.info(
                "event=user.create.succeeded user_id=%s",
                user.id,
            )

            return user

        except IntegrityError as exc:
            self.session.rollback()

            logger.warning(
                "event=user.create.conflict"
            )

            raise UserAlreadyExistsError from exc

        except OperationalError as exc:
            self.session.rollback()

            logger.error(
                "event=user.create.persistence_failure"
            )

            raise PersistenceUnavailableError from exc


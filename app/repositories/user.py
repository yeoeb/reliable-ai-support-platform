from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(
        self,
        email: str,
    ) -> User | None:
        statement = select(User).where(
            User.email == email
        )

        return self.session.scalar(statement)

    def get_by_id(
        self,
        user_id: UUID,
    ) -> User | None:
        return self.session.get(
            User,
            user_id,
        )

    def create(
        self,
        *,
        email: str,
        display_name: str,
    ) -> User:
        user = User(
            email=email,
            display_name=display_name,
        )

        self.session.add(user)
        self.session.flush()

        return user
    def list_all(self) -> list[User]:
        statement = select(User).order_by(
            User.created_at,
            User.id,
        )

        return list(
            self.session.scalars(statement).all()
        )
    


def get_by_email(
    session: Session,
    email: str,
) -> User | None:
    repository = UserRepository(session)

    return repository.get_by_email(email)


def get_by_id(
    session: Session,
    user_id: UUID,
) -> User | None:
    repository = UserRepository(session)

    return repository.get_by_id(user_id)
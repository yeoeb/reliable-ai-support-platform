from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)

        return self.session.scalar(statement)

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
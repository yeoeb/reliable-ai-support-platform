from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_credential import UserCredential


class UserCredentialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        user_id: UUID,
        password_hash: str,
    ) -> UserCredential:
        credential = UserCredential(
            user_id=user_id,
            password_hash=password_hash,
        )

        self.session.add(credential)
        self.session.flush()

        return credential

    def get_by_user_id(
        self,
        user_id: UUID,
    ) -> UserCredential | None:
        statement = select(UserCredential).where(
            UserCredential.user_id == user_id
        )

        return self.session.scalar(statement)


def create_user_credential(
    session: Session,
    *,
    user_id: UUID,
    password_hash: str,
) -> UserCredential:
    repository = UserCredentialRepository(session)

    return repository.create(
        user_id=user_id,
        password_hash=password_hash,
    )


def get_user_credential_by_user_id(
    session: Session,
    user_id: UUID,
) -> UserCredential | None:
    repository = UserCredentialRepository(session)

    return repository.get_by_user_id(user_id)
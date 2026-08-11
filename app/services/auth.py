from sqlalchemy.orm import Session

from app.core.errors import InvalidCredentialsError
from app.core.security import verify_password
from app.repositories.user import UserRepository
from app.repositories.user_credential import (
    get_user_credential_by_user_id,
)


def authenticate_user(
    session: Session,
    *,
    email: str,
    password: str,
):
    user_repository = UserRepository(session)

    user = user_repository.get_by_email(email)

    if user is None:
        raise InvalidCredentialsError

    credential = get_user_credential_by_user_id(
        session,
        user.id,
    )

    if credential is None:
        raise InvalidCredentialsError

    if not verify_password(
        password,
        credential.password_hash,
    ):
        raise InvalidCredentialsError

    if not user.is_active:
        raise InvalidCredentialsError

    return user
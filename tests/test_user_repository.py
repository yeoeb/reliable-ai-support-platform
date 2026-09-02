from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user import UserRepository


def test_create_adds_and_flushes_user():
    session = MagicMock(spec=Session)
    repository = UserRepository(session)

    user = repository.create(
        email="alice@example.com",
        display_name="Alice",
    )

    assert isinstance(user, User)
    assert user.email == "alice@example.com"
    assert user.display_name == "Alice"

    session.add.assert_called_once_with(user)
    session.flush.assert_called_once()


def test_create_does_not_commit():
    session = MagicMock(spec=Session)
    repository = UserRepository(session)

    repository.create(
        email="alice@example.com",
        display_name="Alice",
    )

    session.commit.assert_not_called()

def test_get_by_email_returns_session_scalar_result():
    session = MagicMock(spec=Session)

    expected_user = User(
        email="alice@example.com",
        display_name="Alice",
    )

    session.scalar.return_value = expected_user

    repository = UserRepository(session)

    result = repository.get_by_email("alice@example.com")

    assert result is expected_user
    session.scalar.assert_called_once()

def test_get_by_email_returns_none_when_user_does_not_exist():
    session = MagicMock(spec=Session)
    session.scalar.return_value = None

    repository = UserRepository(session)

    result = repository.get_by_email("missing@example.com")

    assert result is None

def test_list_all_returns_users() -> None:
    session = MagicMock()

    alice = object()
    bob = object()

    session.scalars.return_value.all.return_value = [
        alice,
        bob,
    ]

    repository = UserRepository(session)

    result = repository.list_all()

    assert result == [
        alice,
        bob,
    ]

    session.scalars.assert_called_once()
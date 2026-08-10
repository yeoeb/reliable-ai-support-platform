from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.errors import (
    PersistenceUnavailableError,
    UserAlreadyExistsError,
)
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.user import UserService

def test_create_user_commits_and_returns_user():
    session = MagicMock(spec=Session)
    service = UserService(session)

    expected_user = User(
        email="alice@example.com",
        display_name="Alice",
    )

    service.repository.create = MagicMock(
        return_value=expected_user
    )

    data = UserCreate(
        email="alice@example.com",
        display_name="Alice",
    )

    result = service.create_user(data)

    assert result is expected_user

    service.repository.create.assert_called_once_with(
        email="alice@example.com",
        display_name="Alice",
    )

    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(expected_user)
    session.rollback.assert_not_called()

def test_create_user_rolls_back_on_integrity_error():
    session = MagicMock(spec=Session)
    service = UserService(session)

    service.repository.create = MagicMock(
        side_effect=IntegrityError(
            statement=None,
            params=None,
            orig=Exception("duplicate email"),
        )
    )

    data = UserCreate(
        email="alice@example.com",
        display_name="Alice",
    )

    with pytest.raises(UserAlreadyExistsError):
        service.create_user(data)

    session.rollback.assert_called_once()
    session.commit.assert_not_called()

def test_create_user_rolls_back_on_operational_error():
    session = MagicMock(spec=Session)
    service = UserService(session)

    service.repository.create = MagicMock(
        side_effect=OperationalError(
            statement=None,
            params=None,
            orig=Exception("database unavailable"),
        )
    )

    data = UserCreate(
        email="alice@example.com",
        display_name="Alice",
    )

    with pytest.raises(PersistenceUnavailableError):
        service.create_user(data)

    session.rollback.assert_called_once()
    session.commit.assert_not_called()

def test_create_user_rolls_back_when_commit_fails():
    session = MagicMock(spec=Session)
    service = UserService(session)

    user = User(
        email="alice@example.com",
        display_name="Alice",
    )

    service.repository.create = MagicMock(
        return_value=user
    )

    session.commit.side_effect = OperationalError(
        statement=None,
        params=None,
        orig=Exception("connection lost"),
    )

    data = UserCreate(
        email="alice@example.com",
        display_name="Alice",
    )

    with pytest.raises(PersistenceUnavailableError):
        service.create_user(data)

    session.rollback.assert_called_once()

def test_create_user_logs_success(caplog):
    session = MagicMock(spec=Session)
    service = UserService(session)

    user = User(
        email="alice@example.com",
        display_name="Alice",
    )

    service.repository.create = MagicMock(
        return_value=user
    )

    data = UserCreate(
        email="alice@example.com",
        display_name="Alice",
    )

    with caplog.at_level("INFO"):
        service.create_user(data)

    assert "event=user.create.succeeded" in caplog.text

def test_create_user_logs_conflict(caplog):
    session = MagicMock(spec=Session)
    service = UserService(session)

    service.repository.create = MagicMock(
        side_effect=IntegrityError(
            statement=None,
            params=None,
            orig=Exception("duplicate"),
        )
    )

    data = UserCreate(
        email="alice@example.com",
        display_name="Alice",
    )

    with caplog.at_level("WARNING"):
        with pytest.raises(UserAlreadyExistsError):
            service.create_user(data)

    assert "event=user.create.conflict" in caplog.text

def test_create_user_logs_persistence_failure(caplog):
    session = MagicMock(spec=Session)
    service = UserService(session)

    service.repository.create = MagicMock(
        side_effect=OperationalError(
            statement=None,
            params=None,
            orig=Exception("database unavailable"),
        )
    )

    data = UserCreate(
        email="alice@example.com",
        display_name="Alice",
    )

    with caplog.at_level("ERROR"):
        with pytest.raises(PersistenceUnavailableError):
            service.create_user(data)

    assert (
        "event=user.create.persistence_failure"
        in caplog.text
    )
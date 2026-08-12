from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import DefaultRoleNotConfiguredError
from app.models.role import Role
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.user import UserService


def make_user() -> User:
    return User(
        id=uuid4(),
        email="alice@example.com",
        display_name="Alice",
    )


def make_role() -> Role:
    return Role(
        id=uuid4(),
        name="user",
        description="Default authenticated user",
    )


def make_user_create() -> UserCreate:
    return UserCreate(
        email="alice@example.com",
        display_name="Alice",
        password="very-secure-password",
    )


def test_create_user_assigns_default_role_and_commits() -> None:
    session = Mock(spec=Session)

    user_repository = Mock()
    credential_repository = Mock()
    rbac_repository = Mock()

    user = make_user()
    role = make_role()

    user_repository.create.return_value = user
    rbac_repository.get_role_by_name.return_value = role

    service = UserService(session)
    service.repository = user_repository
    service.credential_repository = credential_repository
    service.rbac_repository = rbac_repository

    result = service.create_user(make_user_create())

    assert result is user

    user_repository.create.assert_called_once_with(
        email="alice@example.com",
        display_name="Alice",
    )

    credential_repository.create.assert_called_once()

    rbac_repository.get_role_by_name.assert_called_once_with(
        "user"
    )

    rbac_repository.assign_role.assert_called_once_with(
        user_id=user.id,
        role_id=role.id,
    )

    session.commit.assert_called_once()
    session.refresh.assert_called_once_with(user)
    session.rollback.assert_not_called()


def test_create_user_rolls_back_when_role_assignment_fails() -> None:
    session = Mock(spec=Session)

    user_repository = Mock()
    credential_repository = Mock()
    rbac_repository = Mock()

    user = make_user()
    role = make_role()

    user_repository.create.return_value = user
    rbac_repository.get_role_by_name.return_value = role

    rbac_repository.assign_role.side_effect = IntegrityError(
        statement="INSERT INTO user_roles",
        params={},
        orig=Exception("role assignment failed"),
    )

    service = UserService(session)
    service.repository = user_repository
    service.credential_repository = credential_repository
    service.rbac_repository = rbac_repository

    with pytest.raises(IntegrityError):
        service.create_user(make_user_create())

    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_create_user_rolls_back_when_default_role_missing() -> None:
    session = Mock(spec=Session)

    user_repository = Mock()
    credential_repository = Mock()
    rbac_repository = Mock()

    user_repository.create.return_value = make_user()
    rbac_repository.get_role_by_name.return_value = None

    service = UserService(session)
    service.repository = user_repository
    service.credential_repository = credential_repository
    service.rbac_repository = rbac_repository

    with pytest.raises(DefaultRoleNotConfiguredError):
        service.create_user(make_user_create())

    rbac_repository.assign_role.assert_not_called()

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
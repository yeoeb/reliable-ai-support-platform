from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.errors import (
    RoleNotFoundError,
    UserNotFoundError,
)
from app.services.rbac import RBACService


def test_assign_role_commits_when_role_is_assigned() -> None:
    session = MagicMock()
    service = RBACService(session)

    user = SimpleNamespace(id=uuid4())
    role = SimpleNamespace(
        id=uuid4(),
        name="support_agent",
    )

    service.user_repository.get_by_id = MagicMock(
        return_value=user
    )
    service.rbac_repository.get_role_by_name = MagicMock(
        return_value=role
    )
    service.rbac_repository.assign_role = MagicMock(
        return_value=True
    )

    service.assign_role(
        actor_user_id=uuid4(),
        user_id=user.id,
        role_name="support_agent",
    )

    service.rbac_repository.assign_role.assert_called_once_with(
        user_id=user.id,
        role_id=role.id,
    )

    session.commit.assert_called_once()
    session.rollback.assert_not_called()

def test_assign_role_still_succeeds_when_already_assigned() -> None:
    session = MagicMock()
    service = RBACService(session)

    user = SimpleNamespace(id=uuid4())
    role = SimpleNamespace(
        id=uuid4(),
        name="support_agent",
    )

    service.user_repository.get_by_id = MagicMock(
        return_value=user
    )
    service.rbac_repository.get_role_by_name = MagicMock(
        return_value=role
    )
    service.rbac_repository.assign_role = MagicMock(
        return_value=False
    )

    service.assign_role(
        actor_user_id=uuid4(),
        user_id=user.id,
        role_name="support_agent",
    )

    session.commit.assert_called_once()
    session.rollback.assert_not_called()

def test_remove_role_still_succeeds_when_role_not_assigned() -> None:
    session = MagicMock()
    service = RBACService(session)

    user = SimpleNamespace(id=uuid4())
    role = SimpleNamespace(
        id=uuid4(),
        name="admin",
    )

    service.user_repository.get_by_id = MagicMock(
        return_value=user
    )
    service.rbac_repository.get_role_by_name = MagicMock(
        return_value=role
    )
    service.rbac_repository.remove_role = MagicMock(
        return_value=False
    )

    service.remove_role(
        actor_user_id=uuid4(),
        user_id=user.id,
        role_name="admin",
    )

    session.commit.assert_called_once()
    session.rollback.assert_not_called()

def test_assign_role_rolls_back_when_user_missing() -> None:
    session = MagicMock()
    service = RBACService(session)

    user_id = uuid4()

    service.user_repository.get_by_id = MagicMock(
        return_value=None
    )

    with pytest.raises(UserNotFoundError):
        service.assign_role(
            actor_user_id=uuid4(),
            user_id=user_id,
            role_name="admin",
        )

    session.commit.assert_not_called()
    session.rollback.assert_called_once()

def test_assign_role_rolls_back_when_role_missing() -> None:
    session = MagicMock()
    service = RBACService(session)

    user = SimpleNamespace(id=uuid4())

    service.user_repository.get_by_id = MagicMock(
        return_value=user
    )
    service.rbac_repository.get_role_by_name = MagicMock(
        return_value=None
    )

    with pytest.raises(RoleNotFoundError):
        service.assign_role(
            actor_user_id=uuid4(),
            user_id=user.id,
            role_name="super_admin",
        )

    session.commit.assert_not_called()
    session.rollback.assert_called_once()

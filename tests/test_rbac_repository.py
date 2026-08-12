from unittest.mock import MagicMock
from uuid import uuid4

from app.repositories.rbac import RBACRepository


def test_get_permission_names_for_user_returns_unique_permissions() -> None:
    session = MagicMock()

    session.scalars.return_value.all.return_value = [
        "users:read",
        "rbac:manage",
        "users:read",
    ]

    repository = RBACRepository(session)

    user_id = uuid4()

    permissions = repository.get_permission_names_for_user(user_id)

    assert permissions == {
        "users:read",
        "rbac:manage",
    }

    session.scalars.assert_called_once()
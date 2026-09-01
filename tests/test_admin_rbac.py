from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.routes.admin import require_rbac_manage
from app.main import app
from app.services.rbac import RBACService

from app.core.errors import (
    RoleNotFoundError,
    UserNotFoundError,
)

client = TestClient(app)


def override_rbac_manager():
    return SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )


def test_assign_role_returns_204(monkeypatch) -> None:
    user_id = uuid4()

    def fake_assign_role(
        self,
        *,
        actor_user_id,
        user_id,
        role_name,
    ):
        return None

    monkeypatch.setattr(
        RBACService,
        "assign_role",
        fake_assign_role,
    )

    app.dependency_overrides[
        require_rbac_manage
    ] = override_rbac_manager

    try:
        response = client.put(
            f"/admin/users/{user_id}/roles/support_agent"
        )

        assert response.status_code == 204
        assert response.content == b""

    finally:
        app.dependency_overrides.clear()

def test_remove_role_returns_204(monkeypatch) -> None:
    user_id = uuid4()

    def fake_remove_role(
        self,
        *,
        actor_user_id,
        user_id,
        role_name,
    ):
        return None

    monkeypatch.setattr(
        RBACService,
        "remove_role",
        fake_remove_role,
    )

    app.dependency_overrides[
        require_rbac_manage
    ] = override_rbac_manager

    try:
        response = client.delete(
            f"/admin/users/{user_id}/roles/support_agent"
        )

        assert response.status_code == 204
        assert response.content == b""

    finally:
        app.dependency_overrides.clear()

def test_assign_role_returns_404_when_user_missing(
    monkeypatch,
) -> None:
    user_id = uuid4()

    def fake_assign_role(
        self,
        *,
        actor_user_id,
        user_id,
        role_name,
    ):
        raise UserNotFoundError

    monkeypatch.setattr(
        RBACService,
        "assign_role",
        fake_assign_role,
    )

    app.dependency_overrides[
        require_rbac_manage
    ] = override_rbac_manager

    try:
        response = client.put(
            f"/admin/users/{user_id}/roles/admin"
        )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "User not found"
        }

    finally:
        app.dependency_overrides.clear()

def test_assign_role_returns_404_when_role_missing(
    monkeypatch,
) -> None:
    user_id = uuid4()

    def fake_assign_role(
        self,
        *,
        actor_user_id,
        user_id,
        role_name,
    ):
        raise RoleNotFoundError

    monkeypatch.setattr(
        RBACService,
        "assign_role",
        fake_assign_role,
    )

    app.dependency_overrides[
        require_rbac_manage
    ] = override_rbac_manager

    try:
        response = client.put(
            f"/admin/users/{user_id}/roles/super_admin"
        )

        assert response.status_code == 404
        assert response.json() == {
            "detail": "Role not found"
        }

    finally:
        app.dependency_overrides.clear()

def test_assign_role_returns_401_without_token() -> None:
    user_id = uuid4()

    response = client.put(
        f"/admin/users/{user_id}/roles/admin"
    )

    assert response.status_code == 401

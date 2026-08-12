from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import auth, authorization
from app.db.session import get_db
from app.main import app


client = TestClient(app)


def test_jwt_admin_claim_cannot_bypass_database_authorization(
    monkeypatch,
) -> None:
    user_id = uuid4()

    user = SimpleNamespace(
        id=user_id,
        is_active=True,
    )

    fake_repository = MagicMock()
    fake_repository.has_permission.return_value = False

    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda token: {
            "sub": str(user_id),
            "role": "admin",
            "permissions": [
                "users:read",
                "rbac:manage",
            ],
        },
    )

    monkeypatch.setattr(
        auth,
        "get_by_id",
        lambda session, queried_user_id: user,
    )

    monkeypatch.setattr(
        authorization,
        "RBACRepository",
        lambda session: fake_repository,
    )

    def override_db():
        yield object()

    app.dependency_overrides[get_db] = override_db

    try:
        response = client.get(
            "/users",
            headers={
                "Authorization": "Bearer attacker-token",
            },
        )

        assert response.status_code == 403

        fake_repository.has_permission.assert_called_once_with(
            user_id,
            "users:read",
        )

    finally:
        app.dependency_overrides.clear()

def test_jwt_rbac_manage_claim_cannot_access_admin_api(
    monkeypatch,
) -> None:
    user_id = uuid4()
    target_user_id = uuid4()

    user = SimpleNamespace(
        id=user_id,
        is_active=True,
    )

    fake_repository = MagicMock()
    fake_repository.has_permission.return_value = False

    monkeypatch.setattr(
        auth,
        "decode_access_token",
        lambda token: {
            "sub": str(user_id),
            "role": "admin",
            "permissions": [
                "rbac:manage",
            ],
        },
    )

    monkeypatch.setattr(
        auth,
        "get_by_id",
        lambda session, queried_user_id: user,
    )

    monkeypatch.setattr(
        authorization,
        "RBACRepository",
        lambda session: fake_repository,
    )

    def override_db():
        yield object()

    app.dependency_overrides[get_db] = override_db

    try:
        response = client.put(
            (
                f"/admin/users/{target_user_id}"
                "/roles/admin"
            ),
            headers={
                "Authorization": "Bearer attacker-token",
            },
        )

        assert response.status_code == 403

        fake_repository.has_permission.assert_called_once_with(
            user_id,
            "rbac:manage",
        )

    finally:
        app.dependency_overrides.clear()

def test_registration_rejects_role_escalation_fields() -> None:
    response = client.post(
        "/users",
        json={
            "email": "attacker-role@example.com",
            "display_name": "Attacker",
            "password": "VerySecurePassword123!",
            "role": "admin",
        },
    )

    assert response.status_code == 422

def test_registration_rejects_is_admin_field() -> None:
    response = client.post(
        "/users",
        json={
            "email": "attacker-admin@example.com",
            "display_name": "Attacker",
            "password": "VerySecurePassword123!",
            "is_admin": True,
        },
    )

    assert response.status_code == 422

def test_registration_rejects_permissions_field() -> None:
    response = client.post(
        "/users",
        json={
            "email": "attacker-permissions@example.com",
            "display_name": "Attacker",
            "password": "VerySecurePassword123!",
            "permissions": [
                "rbac:manage",
            ],
        },
    )

    assert response.status_code == 422                
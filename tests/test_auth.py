from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.errors import InvalidCredentialsError
from app.main import app

from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.dependencies.auth import get_current_user
from app.services.audit import AuditService

client = TestClient(app)


class FakeUser:
    def __init__(self) -> None:
        self.id = uuid4()
        self.is_active = True


def test_login_returns_access_token(monkeypatch) -> None:
    fake_user = FakeUser()

    def fake_authenticate_user(*args, **kwargs):
        return fake_user

    monkeypatch.setattr(
        "app.api.routes.auth.authenticate_user",
        fake_authenticate_user,
    )
    monkeypatch.setattr(AuditService, "record_best_effort", lambda *args, **kwargs: None)

    response = client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
            "password": "very-secure-password",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert "access_token" in body
    assert isinstance(body["access_token"], str)
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_login_returns_401_for_invalid_credentials(
    monkeypatch,
) -> None:
    def fake_authenticate_user(*args, **kwargs):
        raise InvalidCredentialsError

    monkeypatch.setattr(
        "app.api.routes.auth.authenticate_user",
        fake_authenticate_user,
    )
    monkeypatch.setattr(AuditService, "record_best_effort", lambda *args, **kwargs: None)

    response = client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
            "password": "wrong-password-value",
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid credentials",
    }

    assert response.headers["www-authenticate"] == "Bearer"


def test_login_does_not_leak_internal_details(
    monkeypatch,
) -> None:
    def fake_authenticate_user(*args, **kwargs):
        raise InvalidCredentialsError

    monkeypatch.setattr(
        "app.api.routes.auth.authenticate_user",
        fake_authenticate_user,
    )
    monkeypatch.setattr(AuditService, "record_best_effort", lambda *args, **kwargs: None)

    response = client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
            "password": "wrong-password-value",
        },
    )

    body = response.text.lower()

    assert response.status_code == 401
    assert "password_hash" not in body
    assert "sqlalchemy" not in body
    assert "traceback" not in body
    assert "jwt_secret" not in body


def test_login_rejects_invalid_email() -> None:
    response = client.post(
        "/auth/login",
        json={
            "email": "not-an-email",
            "password": "very-secure-password",
        },
    )

    assert response.status_code == 422


def test_login_rejects_short_password() -> None:
    response = client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422


def test_login_rejects_missing_password() -> None:
    response = client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
        },
    )

    assert response.status_code == 422

def make_user():
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        id=uuid4(),
        email="alice@example.com",
        display_name="Alice",
        is_active=True,
        created_at=now,
        updated_at=now,
    )

def test_get_me_returns_current_user():
    user = make_user()

    app.dependency_overrides[get_current_user] = (
        lambda: user
    )

    try:
        response = client.get("/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == str(user.id)
    assert body["email"] == user.email
    assert body["display_name"] == user.display_name
    assert body["is_active"] is True

def test_get_me_without_token_returns_401():
    response = client.get("/auth/me")

    assert response.status_code == 401

def test_get_me_with_invalid_token_returns_401():
    response = client.get(
        "/auth/me",
        headers={
            "Authorization": "Bearer invalid-token"
        },
    )

    assert response.status_code == 401

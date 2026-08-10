from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.errors import (
    PersistenceUnavailableError,
    UserAlreadyExistsError,
)
from app.main import app
from app.services.user import UserService


client = TestClient(app)

def test_create_user_returns_201(monkeypatch):
    user_id = uuid4()
    now = datetime.now(UTC)

    class FakeUser:
        id = user_id
        email = "alice@example.com"
        display_name = "Alice"
        is_active = True
        created_at = now
        updated_at = now

    def fake_create_user(self, data):
        return FakeUser()

    monkeypatch.setattr(
        UserService,
        "create_user",
        fake_create_user,
    )

    response = client.post(
        "/users",
        json={
            "email": "alice@example.com",
            "display_name": "Alice",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["id"] == str(user_id)
    assert body["email"] == "alice@example.com"
    assert body["display_name"] == "Alice"
    assert body["is_active"] is True

def test_create_user_returns_409_when_user_exists(monkeypatch):
    def fake_create_user(self, data):
        raise UserAlreadyExistsError

    monkeypatch.setattr(
        UserService,
        "create_user",
        fake_create_user,
    )

    response = client.post(
        "/users",
        json={
            "email": "alice@example.com",
            "display_name": "Alice",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "User already exists"
    }

def test_create_user_returns_503_when_persistence_unavailable(
    monkeypatch,
):
    def fake_create_user(self, data):
        raise PersistenceUnavailableError

    monkeypatch.setattr(
        UserService,
        "create_user",
        fake_create_user,
    )

    response = client.post(
        "/users",
        json={
            "email": "alice@example.com",
            "display_name": "Alice",
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Persistence service unavailable"
    }

def test_create_user_returns_422_for_invalid_email():
    response = client.post(
        "/users",
        json={
            "email": "not-an-email",
            "display_name": "Alice",
        },
    )

    assert response.status_code == 422

def test_create_user_rejects_server_owned_fields():
    response = client.post(
        "/users",
        json={
            "email": "alice@example.com",
            "display_name": "Alice",
            "is_active": False,
        },
    )

    assert response.status_code == 422

def test_create_user_rejects_server_owned_fields():
    response = client.post(
        "/users",
        json={
            "email": "alice@example.com",
            "display_name": "Alice",
            "is_active": False,
        },
    )

    assert response.status_code == 422
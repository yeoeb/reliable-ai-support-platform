from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.main import app


client = TestClient(app)


def test_health_ready_returns_200_when_database_is_available(monkeypatch):
    def fake_check_database_connection():
        return None

    monkeypatch.setattr(
        "app.api.routes.health.check_database_connection",
        fake_check_database_connection,
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_health_ready_returns_503_when_database_is_unavailable(monkeypatch):
    def fake_check_database_connection():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(
        "app.api.routes.health.check_database_connection",
        fake_check_database_connection,
    )

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Database unavailable"
    }
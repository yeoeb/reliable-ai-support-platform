from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_liveness_check() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["content-type"] == "application/json"


def test_readiness_check() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["content-type"] == "application/json"
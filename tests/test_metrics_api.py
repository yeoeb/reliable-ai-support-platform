from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST

from app.main import app


client = TestClient(app)


def test_metrics_endpoint_is_public_prometheus_and_hidden_from_openapi() -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]

    output = response.text
    assert "reliable_ai_http_requests" in output
    assert "reliable_ai_http_request_duration_seconds" in output
    assert "reliable_ai_operations" in output
    assert "reliable_ai_llm_tokens" in output
    assert "python_gc_" not in output
    assert "process_" not in output


def test_metrics_endpoint_does_not_expose_known_sensitive_values(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SYNTHETIC_SECRET_019",
        "metrics-secret-value-019",
    )

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "metrics-secret-value-019" not in response.text
    assert "authorization" not in response.text.lower()

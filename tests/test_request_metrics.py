from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware.request_logging import (
    RequestLoggingMiddleware,
)
from app.core.metrics import ApplicationMetrics


def make_app(metrics) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        RequestLoggingMiddleware,
        metrics=metrics,
    )

    @app.get("/items/{item_id}")
    async def item(item_id: str):
        return {"item_id": item_id}

    @app.post("/submit")
    async def submit():
        return {"ok": True}

    @app.get("/metrics")
    async def scrape():
        return {"ok": True}

    return app


def exposition(metrics: ApplicationMetrics) -> str:
    return metrics.exposition().decode("utf-8")


def test_route_templates_collapse_ids_and_exclude_sensitive_inputs() -> None:
    metrics = ApplicationMetrics()
    client = TestClient(make_app(metrics))

    first = client.get(
        "/items/private-id-1?token=query-secret",
        headers={
            "Authorization": "Bearer auth-secret",
            "Cookie": "session=cookie-secret",
        },
    )
    second = client.get("/items/private-id-2")
    submitted = client.post(
        "/submit",
        json={"password": "body-secret"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert submitted.status_code == 200
    assert first.headers["x-request-id"]

    output = exposition(metrics)

    assert 'route="/items/{item_id}"' in output
    assert 'route="/submit"' in output
    assert 'status_class="2xx"' in output
    for secret in (
        "private-id-1",
        "private-id-2",
        "query-secret",
        "auth-secret",
        "cookie-secret",
        "body-secret",
        first.headers["x-request-id"],
    ):
        assert secret not in output


def test_unmatched_route_collapses_and_metrics_scrape_is_excluded() -> None:
    metrics = ApplicationMetrics()
    client = TestClient(make_app(metrics))

    missing = client.get("/private-raw-path-123")
    scrape = client.get("/metrics")

    assert missing.status_code == 404
    assert scrape.status_code == 200

    output = exposition(metrics)
    assert 'route="<unmatched>"' in output
    assert "private-raw-path-123" not in output
    assert 'route="/metrics"' not in output


def test_metrics_failure_does_not_change_successful_response() -> None:
    class BrokenMetrics:
        def record_http(self, **kwargs):
            del kwargs
            raise RuntimeError("metrics unavailable")

    client = TestClient(make_app(BrokenMetrics()))
    response = client.get("/items/1")

    assert response.status_code == 200
    assert response.json() == {"item_id": "1"}
    assert response.headers["x-request-id"]

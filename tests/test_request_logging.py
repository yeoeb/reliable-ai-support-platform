import io
import json
import logging
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware.request_logging import (
    RequestLoggingMiddleware,
    unhandled_exception_response,
)
from app.core.logging import JsonFormatter
from app.core.request_context import get_request_id


def make_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(
        Exception,
        unhandled_exception_response,
    )

    route_logger = logging.getLogger("app.test.route")

    @app.get("/items/{item_id}")
    async def get_item(item_id: str):
        route_logger.info(
            "Route handled",
            extra={
                "event": "test.route",
                "item_id": item_id,
            },
        )
        return {"item_id": item_id}

    @app.post("/submit")
    async def submit():
        return {"ok": True}

    @app.get("/failure")
    async def failure():
        raise RuntimeError("sensitive exception detail")

    return app


class LogCapture:
    def __init__(self) -> None:
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(
            self.stream
        )
        self.handler.setFormatter(JsonFormatter())
        self.logger = logging.getLogger("app")
        self.original_handlers = list(
            self.logger.handlers
        )
        self.original_level = self.logger.level
        self.original_propagate = self.logger.propagate

    def __enter__(self):
        self.logger.handlers = [self.handler]
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        return self

    def __exit__(self, *args):
        self.logger.handlers = self.original_handlers
        self.logger.setLevel(self.original_level)
        self.logger.propagate = self.original_propagate

    def records(self) -> list[dict]:
        lines = [
            line
            for line in self.stream.getvalue().splitlines()
            if line
        ]
        return [json.loads(line) for line in lines]


def find_event(
    records: list[dict],
    event: str,
) -> dict:
    matches = [
        record
        for record in records
        if record.get("event") == event
    ]
    assert len(matches) == 1
    return matches[0]


def test_response_request_id_matches_request_scoped_logs() -> None:
    client = TestClient(make_test_app())

    with LogCapture() as capture:
        response = client.get("/items/123")

    assert response.status_code == 200
    request_id = response.headers["x-request-id"]
    UUID(request_id)

    records = capture.records()
    route_record = find_event(
        records,
        "test.route",
    )
    completion = find_event(
        records,
        "http.request.completed",
    )

    assert route_record["request_id"] == request_id
    assert completion["request_id"] == request_id
    assert completion["http_method"] == "GET"
    assert completion["route"] == "/items/{item_id}"
    assert completion["status_code"] == 200
    assert completion["duration_ms"] >= 0
    assert get_request_id() is None


def test_separate_requests_receive_separate_request_ids() -> None:
    client = TestClient(make_test_app())

    first = client.get("/items/1")
    second = client.get("/items/2")

    assert first.headers["x-request-id"]
    assert second.headers["x-request-id"]
    assert (
        first.headers["x-request-id"]
        != second.headers["x-request-id"]
    )
    assert get_request_id() is None


def test_client_request_id_is_not_trusted() -> None:
    client = TestClient(make_test_app())

    response = client.get(
        "/items/1",
        headers={
            "X-Request-ID": "client-controlled-id"
        },
    )

    UUID(response.headers["x-request-id"])
    assert (
        response.headers["x-request-id"]
        != "client-controlled-id"
    )


def test_unmatched_route_does_not_log_raw_path_or_query() -> None:
    client = TestClient(make_test_app())
    raw_path_secret = "private-customer-123"
    raw_query_secret = "query-access-token"

    with LogCapture() as capture:
        response = client.get(
            f"/{raw_path_secret}?token={raw_query_secret}"
        )

    assert response.status_code == 404
    completion = find_event(
        capture.records(),
        "http.request.completed",
    )
    assert completion["route"] == "<unmatched>"

    output = capture.stream.getvalue()
    assert raw_path_secret not in output
    assert raw_query_secret not in output


def test_lifecycle_log_excludes_sensitive_http_inputs() -> None:
    client = TestClient(make_test_app())

    secrets = {
        "authorization": "Bearer raw-access-token",
        "cookie": "session=private-cookie",
        "query": "password=query-password",
        "body": "body-secret-password",
    }

    with LogCapture() as capture:
        response = client.post(
            f"/submit?{secrets['query']}",
            headers={
                "Authorization": secrets["authorization"],
                "Cookie": secrets["cookie"],
            },
            json={
                "password": secrets["body"],
            },
        )

    assert response.status_code == 200
    completion = find_event(
        capture.records(),
        "http.request.completed",
    )
    assert completion["route"] == "/submit"

    output = capture.stream.getvalue()
    for secret in (
        "raw-access-token",
        "private-cookie",
        "query-password",
        "body-secret-password",
    ):
        assert secret not in output


def test_failure_log_exposes_exception_type_not_message() -> None:
    client = TestClient(
        make_test_app(),
        raise_server_exceptions=False,
    )

    with LogCapture() as capture:
        response = client.get("/failure")

    assert response.status_code == 500
    UUID(response.headers["x-request-id"])
    failed = find_event(
        capture.records(),
        "http.request.failed",
    )

    assert failed["route"] == "/failure"
    assert failed["exception_type"] == "RuntimeError"
    assert (
        failed["request_id"]
        == response.headers["x-request-id"]
    )
    assert (
        "sensitive exception detail"
        not in capture.stream.getvalue()
    )
    assert get_request_id() is None

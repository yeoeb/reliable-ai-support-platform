import io
import json
import logging
from uuid import uuid4

from app.core.logging import JsonFormatter, configure_logging
from app.core.request_context import (
    get_request_id,
    reset_request_id,
    set_request_id,
)


def format_record(
    *,
    message: str = "Test message",
    event: str = "test.event",
    extra: dict | None = None,
) -> dict:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.event = event

    for key, value in (extra or {}).items():
        setattr(record, key, value)

    return json.loads(JsonFormatter().format(record))


def test_json_formatter_emits_stable_base_fields() -> None:
    payload = format_record(
        extra={
            "user_id": uuid4(),
            "changed": True,
        }
    )

    assert payload["timestamp"].endswith("Z")
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "Test message"
    assert payload["event"] == "test.event"
    assert payload["request_id"] is None
    assert isinstance(payload["user_id"], str)
    assert payload["changed"] is True


def test_json_formatter_uses_request_context() -> None:
    token = set_request_id("request-123")
    try:
        assert get_request_id() == "request-123"
        payload = format_record()
    finally:
        reset_request_id(token)

    assert payload["request_id"] == "request-123"
    assert get_request_id() is None


def test_json_formatter_redacts_sensitive_structured_fields() -> None:
    payload = format_record(
        extra={
            "password": "plain-password",
            "access_token": "raw-token",
            "Authorization": "Bearer raw-token",
            "safe_value": "visible",
            "nested": {
                "api_key": "secret-api-key",
                "permission": "users:read",
            },
        }
    )

    assert payload["password"] == "[REDACTED]"
    assert payload["access_token"] == "[REDACTED]"
    assert payload["Authorization"] == "[REDACTED]"
    assert payload["safe_value"] == "visible"
    assert payload["nested"]["api_key"] == "[REDACTED]"
    assert payload["nested"]["permission"] == "users:read"

    serialized = json.dumps(payload)
    for secret in (
        "plain-password",
        "raw-token",
        "secret-api-key",
    ):
        assert secret not in serialized


def test_json_formatter_preserves_token_usage_field() -> None:
    payload = format_record(
        extra={"token_usage": 42},
    )

    assert payload["token_usage"] == 42


def test_configure_logging_is_idempotent() -> None:
    logger = logging.getLogger("app")
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate

    try:
        logger.handlers = []

        configure_logging("INFO")
        configure_logging("DEBUG")

        owned = [
            handler
            for handler in logger.handlers
            if getattr(
                handler,
                "_reliable_ai_json_handler",
                False,
            )
        ]

        assert len(owned) == 1
        assert logger.level == logging.DEBUG
        assert owned[0].level == logging.DEBUG
        assert logger.propagate is False
        assert isinstance(
            owned[0].formatter,
            JsonFormatter,
        )
    finally:
        logger.handlers = original_handlers
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def test_json_formatter_writes_one_line_json() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger("app.test.one_line")
    original_handlers = list(logger.handlers)
    original_propagate = logger.propagate
    original_level = logger.level

    try:
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)

        logger.info(
            "One line",
            extra={"event": "test.one_line"},
        )
    finally:
        logger.handlers = original_handlers
        logger.propagate = original_propagate
        logger.setLevel(original_level)

    output = stream.getvalue()
    assert output.count("\n") == 1
    payload = json.loads(output)
    assert payload["event"] == "test.one_line"

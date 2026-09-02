from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.core.request_context import get_request_id


_REDACTED = "[REDACTED]"
_HANDLER_MARKER = "_reliable_ai_json_handler"

_STANDARD_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "taskName",
    "thread",
    "threadName",
}

_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "token",
    "access_token",
    "authorization",
    "authorization_header",
    "cookie",
    "set_cookie",
    "secret",
    "jwt_secret",
    "jwt_secret_key",
    "api_key",
    "database_url",
    "connection_string",
    "postgres_password",
}


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalize_key(key)

    if normalized in _SENSITIVE_KEYS:
        return True

    return normalized.endswith(
        (
            "_password",
            "_password_hash",
            "_access_token",
            "_authorization",
            "_cookie",
            "_api_key",
            "_secret",
        )
    )


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                _REDACTED
                if _is_sensitive_key(str(key))
                else _sanitize_value(item)
            )
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item) for item in value]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "event": getattr(record, "event", None),
            "request_id": getattr(
                record,
                "request_id",
                get_request_id(),
            ),
        }

        for key, value in record.__dict__.items():
            if (
                key in _STANDARD_LOG_RECORD_FIELDS
                or key in payload
                or key.startswith("_")
            ):
                continue

            payload[key] = (
                _REDACTED
                if _is_sensitive_key(key)
                else _sanitize_value(value)
            )

        if record.exc_info:
            exception_type = record.exc_info[0]
            payload["exception_type"] = (
                exception_type.__name__
                if exception_type is not None
                else None
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )


def configure_logging(log_level: str = "INFO") -> None:
    logger = logging.getLogger("app")
    logger.setLevel(log_level)
    logger.propagate = False

    owned_handlers = [
        handler
        for handler in logger.handlers
        if getattr(handler, _HANDLER_MARKER, False)
    ]

    if owned_handlers:
        for handler in owned_handlers:
            handler.setLevel(log_level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(JsonFormatter())
    setattr(handler, _HANDLER_MARKER, True)
    logger.addHandler(handler)

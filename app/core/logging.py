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

_SENSITIVE_KEY_CANONICALS = {
    "password",
    "passwordhash",
    "token",
    "accesstoken",
    "authorization",
    "authorizationheader",
    "cookie",
    "setcookie",
    "secret",
    "jwtsecret",
    "jwtsecretkey",
    "apikey",
    "databaseurl",
    "connectionstring",
    "postgrespassword",
}


def _canonical_key(key: str) -> str:
    return "".join(
        character
        for character in key.strip().lower()
        if character.isalnum()
    )


def _is_sensitive_key(key: str) -> bool:
    canonical = _canonical_key(key)

    if canonical in _SENSITIVE_KEY_CANONICALS:
        return True

    return canonical.endswith(
        (
            "password",
            "passwordhash",
            "accesstoken",
            "authorization",
            "cookie",
            "apikey",
            "secret",
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
        context_request_id = get_request_id()
        record_request_id = getattr(
            record,
            "request_id",
            None,
        )

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "event": getattr(record, "event", None),
            "request_id": (
                context_request_id
                if context_request_id is not None
                else record_request_id
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

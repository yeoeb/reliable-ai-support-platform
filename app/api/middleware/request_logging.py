from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.metrics import ApplicationMetrics, application_metrics
from app.core.request_context import reset_request_id, set_request_id


logger = logging.getLogger(__name__)

_UNMATCHED_ROUTE = "<unmatched>"
_REQUEST_ID_HEADER = b"x-request-id"
_REQUEST_ID_HEADER_NAME = "X-Request-ID"


def _resolved_route(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)

    if isinstance(path, str) and path:
        return path

    return _UNMATCHED_ROUTE


class RequestLoggingMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        metrics: ApplicationMetrics = application_metrics,
    ) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        token = set_request_id(request_id)
        started_at = time.perf_counter()
        status_code: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != _REQUEST_ID_HEADER
                ]
                headers.append(
                    (
                        _REQUEST_ID_HEADER,
                        request_id.encode("ascii"),
                    )
                )
                message["headers"] = headers

            await send(message)

        try:
            await self.app(
                scope,
                receive,
                send_wrapper,
            )
        except Exception as exc:
            duration_ms = max(
                0.0,
                (time.perf_counter() - started_at) * 1000,
            )
            route = _resolved_route(scope)
            logger.error(
                "HTTP request failed",
                extra={
                    "event": "http.request.failed",
                    "http_method": scope.get("method"),
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                    "exception_type": type(exc).__name__,
                },
            )
            self.metrics.record_http(
                method=scope.get("method"),
                route=route,
                status_code=status_code,
                duration_seconds=duration_ms / 1000.0,
            )
            raise
        else:
            duration_ms = max(
                0.0,
                (time.perf_counter() - started_at) * 1000,
            )
            route = _resolved_route(scope)
            logger.info(
                "HTTP request completed",
                extra={
                    "event": "http.request.completed",
                    "http_method": scope.get("method"),
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            self.metrics.record_http(
                method=scope.get("method"),
                route=route,
                status_code=status_code,
                duration_seconds=duration_ms / 1000.0,
            )
        finally:
            reset_request_id(token)



async def unhandled_exception_response(
    request: Request,
    exc: Exception,
) -> PlainTextResponse:
    del exc

    request_id = getattr(
        request.state,
        "request_id",
        None,
    )
    headers = (
        {_REQUEST_ID_HEADER_NAME: request_id}
        if request_id
        else {}
    )

    return PlainTextResponse(
        "Internal Server Error",
        status_code=500,
        headers=headers,
    )

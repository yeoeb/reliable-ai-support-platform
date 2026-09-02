from __future__ import annotations

import logging
from typing import Final

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)


logger = logging.getLogger(__name__)

_UNMATCHED_ROUTE: Final = "<unmatched>"
_METRICS_ROUTE: Final = "/metrics"
_ALLOWED_METHODS: Final = frozenset(
    {
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
        "HEAD",
        "TRACE",
    }
)
_ALLOWED_OPERATION_OUTCOMES: Final = {
    "rag_answer": frozenset(
        {
            "grounded",
            "insufficient_evidence",
            "provider_failure",
        }
    ),
    "agent_run": frozenset(
        {
            "completed",
            "approval_required",
        }
    ),
}
_ALLOWED_TOKEN_OPERATIONS: Final = frozenset(
    {"rag_answer", "agent_run"}
)
_ALLOWED_TOKEN_DIRECTIONS: Final = frozenset(
    {"input", "output"}
)
_HTTP_DURATION_BUCKETS: Final = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def _normalized_method(method: object) -> str:
    if isinstance(method, str):
        normalized = method.strip().upper()
        if normalized in _ALLOWED_METHODS:
            return normalized
    return "OTHER"


def _normalized_route(route: object) -> str:
    if isinstance(route, str) and route:
        return route
    return _UNMATCHED_ROUTE


def _status_class(status_code: object) -> str:
    if (
        isinstance(status_code, int)
        and not isinstance(status_code, bool)
        and 100 <= status_code <= 599
    ):
        return f"{status_code // 100}xx"
    return "unknown"


class ApplicationMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry(
            auto_describe=True
        )
        self.http_requests = Counter(
            "reliable_ai_http_requests_total",
            "HTTP requests handled by the application.",
            labelnames=(
                "method",
                "route",
                "status_class",
            ),
            registry=self.registry,
        )
        self.http_duration = Histogram(
            "reliable_ai_http_request_duration_seconds",
            "HTTP request duration in seconds.",
            labelnames=("method", "route"),
            buckets=_HTTP_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.ai_operations = Counter(
            "reliable_ai_operations_total",
            "Bounded AI operation outcomes.",
            labelnames=("operation", "outcome"),
            registry=self.registry,
        )
        self.llm_tokens = Counter(
            "reliable_ai_llm_tokens_total",
            "Aggregate LLM token usage.",
            labelnames=("operation", "direction"),
            registry=self.registry,
        )

    @staticmethod
    def _warn(category: str) -> None:
        logger.warning(
            "Operational metrics recording failed",
            extra={
                "event": "metrics.record.failed",
                "metric_category": category,
            },
        )

    def record_http(
        self,
        *,
        method: object,
        route: object,
        status_code: object,
        duration_seconds: object,
    ) -> None:
        normalized_route = _normalized_route(route)
        if normalized_route == _METRICS_ROUTE:
            return

        normalized_method = _normalized_method(method)
        normalized_status = _status_class(status_code)

        if (
            not isinstance(duration_seconds, (int, float))
            or isinstance(duration_seconds, bool)
        ):
            duration = 0.0
        else:
            duration = max(0.0, float(duration_seconds))

        try:
            self.http_requests.labels(
                method=normalized_method,
                route=normalized_route,
                status_class=normalized_status,
            ).inc()
            self.http_duration.labels(
                method=normalized_method,
                route=normalized_route,
            ).observe(duration)
        except Exception:
            self._warn("http")

    def record_ai_operation(
        self,
        *,
        operation: str,
        outcome: str,
    ) -> None:
        allowed_outcomes = _ALLOWED_OPERATION_OUTCOMES.get(
            operation
        )
        if (
            allowed_outcomes is None
            or outcome not in allowed_outcomes
        ):
            return

        try:
            self.ai_operations.labels(
                operation=operation,
                outcome=outcome,
            ).inc()
        except Exception:
            self._warn("ai_operation")

    def record_llm_tokens(
        self,
        *,
        operation: str,
        input_tokens: object,
        output_tokens: object,
    ) -> None:
        if operation not in _ALLOWED_TOKEN_OPERATIONS:
            return
        if (
            not isinstance(input_tokens, int)
            or isinstance(input_tokens, bool)
            or input_tokens < 0
            or not isinstance(output_tokens, int)
            or isinstance(output_tokens, bool)
            or output_tokens < 0
        ):
            return

        try:
            if input_tokens:
                self.llm_tokens.labels(
                    operation=operation,
                    direction="input",
                ).inc(input_tokens)
            if output_tokens:
                self.llm_tokens.labels(
                    operation=operation,
                    direction="output",
                ).inc(output_tokens)
        except Exception:
            self._warn("llm_tokens")

    def exposition(self) -> bytes:
        return generate_latest(self.registry)


application_metrics = ApplicationMetrics()

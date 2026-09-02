from prometheus_client import generate_latest

from app.core.metrics import ApplicationMetrics


def exposition(metrics: ApplicationMetrics) -> str:
    return generate_latest(
        metrics.registry
    ).decode("utf-8")


def test_custom_registry_exposes_reviewed_metrics_only() -> None:
    metrics = ApplicationMetrics()
    metrics.record_http(
        method="GET",
        route="/health/live",
        status_code=200,
        duration_seconds=0.01,
    )
    metrics.record_ai_operation(
        operation="rag_answer",
        outcome="grounded",
    )
    metrics.record_llm_tokens(
        operation="rag_answer",
        input_tokens=3,
        output_tokens=2,
    )

    output = exposition(metrics)

    assert "reliable_ai_http_requests_total" in output
    assert "reliable_ai_http_request_duration_seconds" in output
    assert "reliable_ai_operations_total" in output
    assert "reliable_ai_llm_tokens_total" in output
    assert "python_gc_" not in output
    assert "process_" not in output


def test_method_status_and_invalid_internal_labels_are_bounded() -> None:
    metrics = ApplicationMetrics()
    metrics.record_http(
        method="BREW",
        route="/items/{item_id}",
        status_code=418,
        duration_seconds=0.1,
    )
    metrics.record_http(
        method="GET",
        route=None,
        status_code=None,
        duration_seconds=-1,
    )
    metrics.record_ai_operation(
        operation="rag_answer",
        outcome="user-controlled-value",
    )
    metrics.record_ai_operation(
        operation="attacker-operation",
        outcome="grounded",
    )
    metrics.record_llm_tokens(
        operation="attacker-operation",
        input_tokens=9,
        output_tokens=9,
    )
    metrics.record_llm_tokens(
        operation="rag_answer",
        input_tokens=-1,
        output_tokens=1,
    )

    output = exposition(metrics)

    assert 'method="OTHER"' in output
    assert 'status_class="4xx"' in output
    assert 'route="<unmatched>"' in output
    assert 'status_class="unknown"' in output
    assert "user-controlled-value" not in output
    assert "attacker-operation" not in output


def test_metrics_self_scrape_is_not_recorded() -> None:
    metrics = ApplicationMetrics()
    metrics.record_http(
        method="GET",
        route="/metrics",
        status_code=200,
        duration_seconds=0.01,
    )

    output = exposition(metrics)

    assert 'route="/metrics"' not in output


def test_prometheus_recording_failure_is_best_effort(
    monkeypatch,
) -> None:
    metrics = ApplicationMetrics()

    class BrokenCounter:
        def labels(self, **kwargs):
            del kwargs
            raise RuntimeError("sensitive metrics failure detail")

    monkeypatch.setattr(
        metrics,
        "http_requests",
        BrokenCounter(),
    )

    metrics.record_http(
        method="GET",
        route="/health/live",
        status_code=200,
        duration_seconds=0.01,
    )

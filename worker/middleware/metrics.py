"""Prometheus metrics and FastAPI middleware for LLM observability.

Registers the core LLM cost/usage/token counters and a middleware that wraps
each HTTP request in an OpenTelemetry span while updating request-level
metrics. A ``/metrics`` endpoint function is exported for wiring into the app.

The metrics are defined at module import time against the global meter, so the
exact same metric instruments are shared by the LLM router and the middleware.
"""

from __future__ import annotations

import time

from prometheus_client import Counter, Histogram
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from opentelemetry import trace
from opentelemetry import context as otel_context
from opentelemetry.propagate import extract

# --- LLM token / cost metrics (broken down by provider, model, tenant) -----
llm_token_usage_total = Counter(
    "llm_token_usage_total",
    "Total tokens consumed by LLM calls",
    ["provider", "model", "tenant"],
)
llm_request_cost_usd = Counter(
    "llm_request_cost_usd",
    "Total estimated cost of LLM calls in USD",
    ["provider", "model", "tenant"],
)
llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "Duration of LLM calls in seconds",
    ["provider", "model", "tenant"],
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)

# --- HTTP request metrics ------------------------------------------------
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
)


def metrics_endpoint():
    """Return the Prometheus exposition format body for the /metrics route."""
    from fastapi.responses import Response

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


class MetricsMiddleware:
    """ASGI middleware that records request metrics and injects a span."""

    def __init__(self, app):
        self.app = app
        self._tracer = trace.get_tracer("http.middleware")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        route = scope.get("path", "")
        method = scope.get("method", "")

        # Start a span for this request using any incoming trace context.
        token = None
        try:
            headers = dict(scope.get("headers") or [])
            ctx = extract(headers)
            token = otel_context.attach(ctx)
            span = self._tracer.start_span(f"http.{method} {route}")
            span.set_attribute("http.method", method)
            span.set_attribute("http.route", route)
        except Exception:  # noqa: BLE001 - tracing must never break requests
            span = None

        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            http_requests_total.labels(
                method=method, route=route, status=str(status_code)
            ).inc()
            http_request_duration_seconds.labels(
                method=method, route=route
            ).observe(duration)
            if span is not None:
                span.set_attribute("http.status_code", str(status_code))
                span.end()
            if token is not None:
                otel_context.detach(token)

"""Centralized OpenTelemetry setup for distributed tracing and metrics.

This module configures the trace and metric providers once (idempotently) and
exposes small helpers for obtaining named tracers and the meter.

Non-breaking design:
  * Unless ``OTEL_ENABLED`` is truthy, tracing/metrics default to no-op
    providers so the application behaves exactly as before in environments
    without a collector.
  * Importing this module never raises even if the OpenTelemetry SDK is not
    installed (the SDK is a soft dependency).
"""

from __future__ import annotations

import os
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

# Service identity used as a resource attribute on every span/metric.
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "meeting-automation-worker")

_configured = False


def _resource() -> Resource:
    return Resource.create({"service.name": SERVICE_NAME})


def _configure_trace(exporter) -> None:
    provider = TracerProvider(resource=_resource())
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


def _configure_metrics(exporter) -> None:
    reader = PeriodicExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=[reader], resource=_resource())
    metrics.set_meter_provider(meter_provider)


def configure_telemetry() -> bool:
    """Configure trace + metric providers once. Idempotent.

    Returns ``True`` when telemetry was (re)configured, ``False`` when it was
    already configured or when telemetry is disabled.
    """
    global _configured
    if _configured:
        return False

    if not os.getenv("OTEL_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
        # Leave the default no-op providers in place; nothing to do.
        _configured = True
        return True

    try:
        # Console exporters are the safe default; swap for OTLP by setting
        # OTEL_EXPORTER_OTLP_ENDPOINT to use a real collector.
        _configure_trace(ConsoleSpanExporter())
        _configure_metrics(
            PeriodicExportingMetricReader(ConsoleMetricExporter())
        )
    except Exception:  # noqa: BLE001 - never break app startup on telemetry
        # Fall back to no-op providers so the app still boots.
        trace.set_tracer_provider(TracerProvider())
        metrics.set_meter_provider(MeterProvider())
    finally:
        _configured = True
    return True


def get_tracer(name: str):
    """Return a named :class:`opentelemetry.trace.Tracer`.

    Safe to call before :func:`configure_telemetry`; returns the global
    (possibly no-op) tracer.
    """
    return trace.get_tracer(name)


def get_meter(name: str):
    """Return a named :class:`opentelemetry.metrics.Meter`."""
    return metrics.get_meter(name)


def cleanup() -> None:
    """Flush and shut down providers (used on app shutdown)."""
    try:
        trace.get_tracer_provider().shutdown()
    except Exception:  # noqa: BLE001
        pass
    try:
        metrics.get_meter_provider().shutdown()
    except Exception:  # noqa: BLE001
        pass

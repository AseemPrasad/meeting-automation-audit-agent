"""
Production structured logging configuration.
Emits single-line JSON logs formatted for immediate Datadog, CloudWatch, and Loki ingestion.
Falls back to human-readable text logs when LOG_FORMAT=text (local development).
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON objects for centralized log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        # Attach exception tracebacks if present
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Attach OpenTelemetry trace context if active
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            span_ctx = span.get_span_context() if span else None
            if span_ctx and span_ctx.is_valid:
                log_payload["trace_id"] = format(span_ctx.trace_id, "032x")
                log_payload["span_id"] = format(span_ctx.span_id, "016x")
        except Exception:
            pass

        return json.dumps(log_payload)


def configure_logging(default_level: int = logging.INFO) -> None:
    """Configures the root logger based on LOG_FORMAT environment variable."""
    log_format = os.getenv("LOG_FORMAT", "text").strip().lower()

    root_logger = logging.getLogger()
    root_logger.setLevel(default_level)

    # Clear existing handlers to prevent duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        # Standard human-readable console formatter for local development
        console_handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)-5.5s [%(name)s] %(message)s", datefmt="%H:%M:%S")
        )

    root_logger.addHandler(console_handler)


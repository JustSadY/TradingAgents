"""Optional OpenTelemetry and Langfuse observability helpers.

Product WebSocket/event streams stay unchanged. Infrastructure tracing can use
standard OTLP OpenTelemetry, while LLM/agent tracing can use Langfuse. They are
kept opt-in so deployments do not gain mandatory external telemetry services.
"""

from __future__ import annotations

import logging
import os
from typing import Any

_logger = logging.getLogger(__name__)
_CONFIGURED = False
_LANGFUSE_CALLBACK: Any | None = None
_LANGFUSE_INITIALIZED = False


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def configure_optional_opentelemetry() -> bool:
    """Configure OTLP tracing when ``OTEL_ENABLED`` is set."""
    global _CONFIGURED
    if _CONFIGURED:
        return True
    if not _enabled("OTEL_ENABLED"):
        return False

    os.environ.setdefault("OTEL_SERVICE_NAME", "tradingagents-backend")
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        _logger.warning("OTEL_ENABLED=true but OpenTelemetry instrumentation packages are not installed")
        return False

    service_name = os.getenv("OTEL_SERVICE_NAME", "tradingagents-backend")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    try:
        from backend.core.database import engine

        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except Exception:
        _logger.exception("Could not instrument SQLAlchemy; continuing with HTTP tracing")
    _CONFIGURED = True
    return True


def get_langfuse_callback() -> Any | None:
    """Return one process-wide Langfuse LangChain callback when enabled.

    Langfuse v4 is OpenTelemetry-based. Running its SDK beside an independently
    configured global OTLP provider can create competing TracerProviders, so the
    two exporters are intentionally mutually exclusive in-process. Deployments
    that want both should send OTLP to an OpenTelemetry Collector and fan out
    there instead.
    """
    global _LANGFUSE_CALLBACK, _LANGFUSE_INITIALIZED
    if _LANGFUSE_INITIALIZED:
        return _LANGFUSE_CALLBACK
    _LANGFUSE_INITIALIZED = True

    if not _enabled("LANGFUSE_ENABLED"):
        return None
    if _enabled("OTEL_ENABLED"):
        _logger.warning(
            "LANGFUSE_ENABLED and OTEL_ENABLED are both true; disabling the in-process Langfuse callback. "
            "Use an OpenTelemetry Collector to fan out traces instead."
        )
        return None

    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        _logger.warning("LANGFUSE_ENABLED=true but the langfuse package is not installed")
        return None

    try:
        _LANGFUSE_CALLBACK = CallbackHandler()
    except Exception:
        _logger.exception("Could not initialize Langfuse callback; continuing without Langfuse tracing")
        _LANGFUSE_CALLBACK = None
    return _LANGFUSE_CALLBACK

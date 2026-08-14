"""Optional OpenTelemetry bootstrap.

Product WebSocket/event streams stay unchanged. When the OpenTelemetry distro
is installed, this enables technical request/client/DB tracing through standard
OTEL environment-variable configuration.
"""

from __future__ import annotations

import logging
import os

_logger = logging.getLogger(__name__)
_CONFIGURED = False


def configure_optional_opentelemetry() -> bool:
    global _CONFIGURED
    if _CONFIGURED:
        return True
    enabled = os.getenv("OTEL_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
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

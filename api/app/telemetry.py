"""Application Insights wiring (Azure Monitor OpenTelemetry distro).

Never raises: telemetry must not stop the API from starting. Request/response
bodies and cookies are not captured by the FastAPI instrumentation (headers are
only recorded when explicitly configured, which we do not do).
"""

from __future__ import annotations

import os

from .config import Settings
from .core.logging import logger

ROLE_NAME = "assess-api"


def configure_telemetry(settings: Settings) -> bool:
    """Initialise Azure Monitor if a connection string exists. Returns True if enabled."""
    if not settings.APPLICATIONINSIGHTS_CONNECTION_STRING:
        logger.info("telemetry disabled (no connection string)")
        return False
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.sdk.resources import Resource

        os.environ.setdefault("OTEL_SERVICE_NAME", ROLE_NAME)
        configure_azure_monitor(
            connection_string=settings.APPLICATIONINSIGHTS_CONNECTION_STRING,
            resource=Resource.create({"service.name": ROLE_NAME, "service.version": settings.GIT_SHA}),
            sampling_ratio=settings.APPINSIGHTS_SAMPLING_PERCENT / 100.0,
        )
        logger.info("telemetry enabled", role=ROLE_NAME, sampling=settings.APPINSIGHTS_SAMPLING_PERCENT)
        return True
    except Exception as exc:
        logger.warn("telemetry init failed; continuing without it", error_type=type(exc).__name__)
        return False

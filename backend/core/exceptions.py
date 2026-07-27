"""Centralized HTTP exception handling.

Routers delegate to services and let exceptions propagate; these handlers map
service-layer errors to consistent HTTP responses in one place, instead of each
router repeating ``try/except ValueError -> 400`` / ``Exception -> 500``.

``get_db`` already rolls back the session on any exception, so a propagating
error never leaves a partial commit.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_logger = logging.getLogger(__name__)


class ServiceError(Exception):
    """Base exception for all service-layer errors."""

    status_code: int = 500
    detail: str = "Service error"

    def __init__(self, detail: str | None = None, status_code: int | None = None) -> None:
        if detail is not None:
            self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.detail)


class NotFoundError(ServiceError):
    status_code: int = 404
    detail: str = "Resource not found"


class ValidationError(ServiceError, ValueError):
    status_code: int = 400
    detail: str = "Validation error"


class ExternalServiceError(ServiceError):
    status_code: int = 502
    detail: str = "External service error"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ValueError)
    async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ServiceError)
    async def _service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
        _logger.warning("Service error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        _logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

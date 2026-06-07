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


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ValueError)
    async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        # Services raise ValueError for invalid input / business-rule violations.
        # (Explicit HTTPException raises in routers still win — they never reach here.)
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback server-side; return a generic message so internal
        # details aren't leaked. HTTPException/RequestValidationError/RateLimitExceeded
        # have their own (more specific) handlers and never reach this one.
        _logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

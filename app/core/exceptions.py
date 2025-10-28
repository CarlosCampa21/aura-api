"""
Global exception handlers for consistent API errors.
"""
import logging
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def _req_id(request: Request) -> str | None:
    return getattr(getattr(request, "state", object()), "request_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    log = logging.getLogger("aura.errors")

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc_handler(request: Request, exc: StarletteHTTPException):
        body: Dict[str, Any] = {"message": exc.detail or "HTTP error"}
        rid = _req_id(request)
        if rid:
            body["request_id"] = rid
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        body: Dict[str, Any] = {"message": "Validation error", "errors": exc.errors()}
        rid = _req_id(request)
        if rid:
            body["request_id"] = rid
        return JSONResponse(status_code=422, content=body)

    @app.exception_handler(Exception)
    async def _generic_handler(request: Request, exc: Exception):
        rid = _req_id(request)
        log.exception("Unhandled error request_id=%s", rid)
        body: Dict[str, Any] = {"message": "Internal server error"}
        if rid:
            body["request_id"] = rid
        return JSONResponse(status_code=500, content=body)


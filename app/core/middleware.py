"""
Application middlewares: request id and request logging, plus CORS.
"""
import logging
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)
        self.log = logging.getLogger("aura.request")

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
            return response
        finally:
            dt_ms = int((time.perf_counter() - start) * 1000)
            rid = getattr(request.state, "request_id", None)
            path = request.url.path
            method = request.method
            status = getattr(getattr(locals().get("response", None), "status_code", None), "__int__", lambda: None)()
            # Fallback if response not available
            if status is None:
                status = 0
            self.log.info("method=%s path=%s status=%s latency_ms=%s request_id=%s", method, path, status, dt_ms, rid)


def add_middlewares(app: FastAPI) -> None:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"],)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(LoggingMiddleware)


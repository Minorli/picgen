from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .errors import APIError
from .logging_config import (
    get_logger,
    log_event,
    reset_request_id,
    set_request_id,
)

logger = get_logger("picgen.middleware")

RequestHandler = Callable[[Request], Awaitable[Response]]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign a stable request id, expose it on response headers and logs."""

    header_name = "x-request-id"

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        incoming = request.headers.get(self.header_name, "").strip()
        request_id = incoming if 8 <= len(incoming) <= 64 else uuid.uuid4().hex[:12]
        token = set_request_id(request_id)
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers[self.header_name] = request_id
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
            log_event(
                logger,
                logging.INFO,
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                elapsed_ms=elapsed_ms,
                client=request.client.host if request.client else None,
            )
            return response
        finally:
            reset_request_id(token)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Send conservative defaults for HTML / API responses."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds the configured maximum."""

    def __init__(self, app: Any, *, max_bytes: int) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        if request.method.upper() in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > self.max_bytes:
                        return _error_response(
                            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                            f"请求体超过最大允许大小 {self.max_bytes} 字节",
                            code="payload_too_large",
                        )
                except ValueError:
                    return _error_response(
                        HTTPStatus.BAD_REQUEST,
                        "无效的 Content-Length",
                        code="bad_request",
                    )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-client rate limiter (in-memory)."""

    def __init__(
        self,
        app: Any,
        *,
        per_minute: int,
        burst: int,
        scope_prefix: str = "/api/",
        trust_forwarded_for: bool = False,
    ) -> None:
        super().__init__(app)
        self.per_minute = per_minute
        self.burst = burst
        self.scope_prefix = scope_prefix
        self.trust_forwarded_for = trust_forwarded_for
        self._lock = asyncio.Lock()
        self._minute_buckets: dict[str, deque[float]] = {}
        self._burst_buckets: dict[str, deque[float]] = {}

    @staticmethod
    def _evict(bucket: deque[float], cutoff: float) -> None:
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def _client_key(self, request: Request) -> str:
        if self.trust_forwarded_for:
            forwarded = request.headers.get("x-forwarded-for", "").split(",")
            if forwarded and forwarded[0].strip():
                return forwarded[0].strip()
        return request.client.host if request.client else "anon"

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        if self.per_minute <= 0 or not request.url.path.startswith(self.scope_prefix):
            return await call_next(request)
        if request.url.path in {"/api/health", "/api/ready", "/api/config"}:
            return await call_next(request)
        client_key = self._client_key(request)
        now = time.monotonic()
        async with self._lock:
            minute_bucket = self._minute_buckets.setdefault(client_key, deque())
            burst_bucket = self._burst_buckets.setdefault(client_key, deque())
            self._evict(minute_bucket, now - 60.0)
            self._evict(burst_bucket, now - 5.0)
            if len(minute_bucket) >= self.per_minute or (self.burst > 0 and len(burst_bucket) >= self.burst):
                retry_after = 5
                log_event(
                    logger,
                    logging.WARNING,
                    "rate_limited",
                    client=client_key,
                    path=request.url.path,
                    minute_count=len(minute_bucket),
                    burst_count=len(burst_bucket),
                )
                return _error_response(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    "请求过于频繁，请稍后再试",
                    code="rate_limited",
                    extra_headers={"Retry-After": str(retry_after)},
                )
            minute_bucket.append(now)
            burst_bucket.append(now)
        return await call_next(request)


class ProxyAuthMiddleware(BaseHTTPMiddleware):
    """Optionally require a bearer token for all /api/* endpoints."""

    def __init__(self, app: Any, *, token: str, allow_paths: tuple[str, ...] = ("/api/health", "/api/ready")) -> None:
        super().__init__(app)
        self.token = token
        self.allow_paths = allow_paths

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        if not self.token or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.url.path in self.allow_paths:
            return await call_next(request)
        provided = request.headers.get("x-proxy-token", "").strip()
        if not provided:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                provided = auth.split(None, 1)[1].strip()
        if provided != self.token:
            log_event(
                logger,
                logging.WARNING,
                "proxy_auth_failed",
                path=request.url.path,
                client=request.client.host if request.client else None,
            )
            return _error_response(
                HTTPStatus.UNAUTHORIZED,
                "缺少或无效的代理凭证",
                code="unauthorized",
            )
        return await call_next(request)


def _error_response(
    status: int,
    message: str,
    *,
    code: str,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    from .logging_config import get_request_id

    payload = {
        "error": message,
        "details": None,
        "code": code,
        "request_id": get_request_id(),
    }
    headers = {"X-Request-ID": get_request_id()}
    if extra_headers:
        headers.update(extra_headers)
    return JSONResponse(status_code=status, content=payload, headers=headers)


def api_error_response(exc: APIError) -> JSONResponse:
    from .logging_config import get_request_id

    return JSONResponse(
        status_code=exc.status,
        content={
            "error": exc.message,
            "details": exc.details,
            "code": exc.code,
            "request_id": get_request_id(),
        },
        headers={"X-Request-ID": get_request_id()},
    )

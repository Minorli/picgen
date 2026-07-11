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
from .redaction import redact_sensitive_text

logger = get_logger("picgen.middleware")

RequestHandler = Callable[[Request], Awaitable[Response]]


def _single_message_receive(
    message: dict[str, Any],
    fallback: Callable[[], Awaitable[dict[str, Any]]] | None = None,
) -> Callable[[], Awaitable[dict[str, Any]]]:
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if not delivered:
            delivered = True
            return message
        if message.get("type") == "http.disconnect":
            # ASGI 语义：断线后的每次 receive 都应继续返回 disconnect；
            # 换成合成空请求体会让下游的断线监视误以为客户端还连着。
            return message
        if fallback is not None:
            # After the replayed body, defer to the real receive so downstream
            # disconnect-watchers still observe ``http.disconnect``; returning
            # synthetic empty messages forever would make a cancelled request
            # look connected until the upstream call finishes.
            return await fallback()
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign a stable request id, expose it on response headers and logs."""

    header_name = "x-request-id"

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        incoming = request.headers.get(self.header_name, "").strip()
        request_id = incoming if 8 <= len(incoming) <= 64 else uuid.uuid4().hex[:12]
        request.scope["picgen_request_id"] = request_id
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
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "connect-src 'self'; "
                "font-src 'self' data:; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "frame-ancestors 'none'"
            ),
        )
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


class BodySizeLimitMiddleware:
    """Reject oversized requests before route parsing.

    When a valid ``Content-Length`` is present and within the cap we stream
    straight through: the server reads at most ``Content-Length`` body bytes, so
    the limit is already enforced and there is no need to buffer. Only requests
    without ``Content-Length`` (e.g. chunked transfer) are read up to the limit
    and replayed downstream, bounded by ``max_bytes``.
    """

    def __init__(self, app: Any, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or str(scope.get("method", "")).upper() not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                response = _error_response(
                    HTTPStatus.BAD_REQUEST,
                    "无效的 Content-Length",
                    code="bad_request",
                )
                await response(scope, receive, send)
                return
            if declared > self.max_bytes:
                response = _error_response(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    f"请求体超过最大允许大小 {self.max_bytes} 字节",
                    code="payload_too_large",
                )
                await response(scope, receive, send)
                return
            # Within the cap and the framing is known — no need to buffer/replay.
            await self.app(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message.get("type") == "http.disconnect":
                await self.app(scope, _single_message_receive(message), send)
                return
            if message.get("type") != "http.request":
                continue

            chunk = message.get("body", b"")
            if chunk:
                body.extend(chunk)
            if len(body) > self.max_bytes:
                response = _error_response(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    f"请求体超过最大允许大小 {self.max_bytes} 字节",
                    code="payload_too_large",
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        await self.app(scope, _single_message_receive({
            "type": "http.request",
            "body": bytes(body),
            "more_body": False,
        }, fallback=receive), send)


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
        self._last_sweep = 0.0

    @staticmethod
    def _evict(bucket: deque[float], cutoff: float) -> None:
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def _sweep_idle(self, now: float) -> None:
        """Drop client keys whose windows are fully expired.

        Without this the per-client dicts grow without bound — every distinct
        source IP (or spoofed ``X-Forwarded-For`` value) would leave a permanent
        empty deque behind. Called at most once per minute under the lock.
        """

        for buckets, window in ((self._minute_buckets, 60.0), (self._burst_buckets, 5.0)):
            cutoff = now - window
            for key in list(buckets):
                self._evict(buckets[key], cutoff)
                if not buckets[key]:
                    del buckets[key]

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
        uses_burst_limit = request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
        now = time.monotonic()
        async with self._lock:
            if now - self._last_sweep >= 60.0:
                self._sweep_idle(now)
                self._last_sweep = now
            minute_bucket = self._minute_buckets.setdefault(client_key, deque())
            burst_bucket = self._burst_buckets.setdefault(client_key, deque())
            self._evict(minute_bucket, now - 60.0)
            self._evict(burst_bucket, now - 5.0)
            if len(minute_bucket) >= self.per_minute or (
                uses_burst_limit and self.burst > 0 and len(burst_bucket) >= self.burst
            ):
                retry_after = 5
                if len(minute_bucket) >= self.per_minute and minute_bucket:
                    # The minute window is what's exhausted — tell the client
                    # when a slot actually frees up instead of a flat 5s that
                    # guarantees repeat 429s.
                    retry_after = max(1, int(60.0 - (now - minute_bucket[0])) + 1)
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
            if uses_burst_limit:
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
                # "Bearer " with nothing after it splits to a single element;
                # a blind [1] would 500 on that malformed-but-common header.
                parts = auth.split(None, 1)
                provided = parts[1].strip() if len(parts) == 2 else ""
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
    return api_error_response_with(
        status=exc.status,
        message=exc.message,
        details=exc.details,
        code=exc.code,
    )


def api_error_response_with(
    *,
    status: int,
    message: str,
    details: str | None,
    code: str,
    request_id: str | None = None,
) -> JSONResponse:
    from .logging_config import get_request_id

    resolved_request_id = request_id or get_request_id()
    return JSONResponse(
        status_code=status,
        content={
            "error": redact_sensitive_text(message, limit=1000),
            "details": redact_sensitive_text(details, limit=4000) or None,
            "code": code,
            "request_id": resolved_request_id,
        },
        headers={"X-Request-ID": resolved_request_id},
    )

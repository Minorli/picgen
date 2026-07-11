from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import anyio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from . import __version__
from .auth import AuthStore
from .config import Settings
from .errors import APIError
from .logging_config import configure_logging, get_logger, get_request_id, log_event
from .middleware import (
    BodySizeLimitMiddleware,
    ProxyAuthMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    api_error_response,
    api_error_response_with,
)
from .notifications import (
    ErrorAlert,
    error_alert_notifications_enabled,
    send_error_alert_notification,
)
from .redaction import redact_sensitive_text
from .routes import create_router, drain_notification_tasks
from .storage import prune_old_outputs
from .upstream import HttpxAsyncClient

logger = get_logger("picgen.app")
_auth_store: AuthStore | None = None

# How often the background task re-checks for day-folders past the retention window.
_RETENTION_SWEEP_SECONDS = 6 * 60 * 60
_ALERTABLE_ERROR_CODES = frozenset(
    {
        "internal_error",
        "upstream_error",
        "upstream_timeout",
        "upstream_network_error",
        "upstream_invalid_response",
        "upstream_no_image",
        "upstream_rate_limited",
        "upstream_blocked",
    }
)


async def _retention_loop(settings: Settings) -> None:
    """Periodically prune outputs older than the configured retention window.

    Runs only when ``storage_retention_days > 0``; pruning itself is blocking
    filesystem I/O, so it is dispatched to a worker thread.
    """

    if settings.storage_retention_days <= 0 and not settings.auth_enabled:
        return
    while True:
        try:
            removed = 0
            if settings.storage_retention_days > 0:
                removed = await anyio.to_thread.run_sync(
                    prune_old_outputs, settings.outputs_dir, settings.storage_retention_days
                )
            if removed:
                log_event(
                    logger,
                    logging.INFO,
                    "storage_retention_sweep",
                    removed=removed,
                    retention_days=settings.storage_retention_days,
                )
            auth_store = get_auth_store()
            if settings.auth_enabled and auth_store is not None:
                expired_sessions = await anyio.to_thread.run_sync(auth_store.prune_expired_sessions)
                if expired_sessions:
                    log_event(
                        logger,
                        logging.INFO,
                        "auth_session_retention_sweep",
                        removed=expired_sessions,
                    )
        except Exception as exc:  # pragma: no cover - defensive; never kill the loop
            log_event(logger, logging.WARNING, "storage_retention_error", error=str(exc))
        await asyncio.sleep(_RETENTION_SWEEP_SECONDS)


def get_auth_store() -> AuthStore | None:
    return _auth_store


async def _initialize_auth_store(settings: Settings, auth_store: AuthStore) -> None:
    if not settings.auth_enabled:
        return
    await anyio.to_thread.run_sync(auth_store.initialize)
    if settings.admin_password:
        admin = await anyio.to_thread.run_sync(
            lambda: auth_store.ensure_admin_user(settings.admin_username, settings.admin_password)
        )
        log_event(
            logger,
            logging.INFO,
            "auth_admin_bootstrap_ok",
            username=admin.username,
            user_id=admin.id,
        )
        return
    user_count = await anyio.to_thread.run_sync(auth_store.user_count)
    if user_count == 0:
        log_event(
            logger,
            logging.WARNING,
            "auth_admin_password_missing",
            message="PICGEN_ADMIN_PASSWORD is required before users can log in.",
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    global _auth_store
    resolved_settings = settings or Settings.from_env()
    configure_logging(resolved_settings.log_level, resolved_settings.log_format)
    auth_store = AuthStore(resolved_settings.resolved_auth_db_path)
    _auth_store = auth_store

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings.outputs_dir.mkdir(parents=True, exist_ok=True)
        await _initialize_auth_store(resolved_settings, auth_store)
        client = HttpxAsyncClient(
            total_timeout=resolved_settings.upstream_timeout_seconds,
            connect_timeout=resolved_settings.upstream_connect_timeout_seconds,
            max_connections=resolved_settings.upstream_max_connections,
            max_keepalive=resolved_settings.upstream_max_keepalive,
            max_retries=resolved_settings.upstream_max_retries,
            retry_backoff=resolved_settings.upstream_retry_backoff,
            max_image_bytes=resolved_settings.max_image_bytes,
        )
        app.state.upstream_client = client
        prune_task = asyncio.create_task(_retention_loop(resolved_settings))
        try:
            yield
        finally:
            prune_task.cancel()
            with suppress(asyncio.CancelledError):
                await prune_task
            await drain_notification_tasks()
            await client.aclose()

    app = FastAPI(
        title="PicGen Console",
        version=__version__,
        description="Enterprise-grade local proxy for OpenAI image generation APIs.",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = resolved_settings
    app.state.auth_store = auth_store

    # add_middleware() prepends, so the LAST addition runs OUTERMOST. Runtime
    # order (outer → inner): CORS → RequestId → SecurityHeaders → RateLimit →
    # ProxyAuth → BodySize.
    # - CORS must be outermost or browser preflights (which cannot carry auth
    #   headers) get 401'd by ProxyAuth before CORS can answer them.
    # - BodySize innermost so chunked uploads are not buffered into memory for
    #   requests that rate-limiting or proxy auth would reject anyway.
    # - RateLimit stays outside ProxyAuth so token guessing burns rate budget.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=resolved_settings.max_request_body_bytes)

    if resolved_settings.proxy_auth_token:
        app.add_middleware(ProxyAuthMiddleware, token=resolved_settings.proxy_auth_token)

    app.add_middleware(
        RateLimitMiddleware,
        per_minute=resolved_settings.rate_limit_per_minute,
        burst=resolved_settings.rate_limit_burst,
        trust_forwarded_for=resolved_settings.trust_forwarded_for,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    if resolved_settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved_settings.cors_allow_origins,
            allow_credentials=resolved_settings.cors_allow_credentials,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> Any:
        if not _should_use_operational_response(exc):
            return api_error_response(exc)
        should_alert = _should_alert_api_error(exc)
        alert_enabled = error_alert_notifications_enabled(resolved_settings)
        request_id = _request_id_from_scope(request)
        response = api_error_response_with(
            status=exc.status,
            message=_public_operational_error_message(exc, alert_enabled=alert_enabled and should_alert),
            details=_public_operational_error_details(exc),
            code=exc.code,
            request_id=request_id,
        )
        if alert_enabled and should_alert:
            response.background = BackgroundTask(
                _send_error_alert,
                settings=resolved_settings,
                alert=_build_error_alert(
                    request=request,
                    status=exc.status,
                    code=exc.code,
                    public_message=_public_operational_error_message(exc, alert_enabled=True),
                    technical_message=exc.message,
                    details=exc.details,
                    request_id=request_id,
                ),
            )
        return response

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> Any:
        request_id = _request_id_from_scope(request)
        log_event(
            logger,
            logging.ERROR,
            "unhandled_exception",
            method=request.method,
            path=request.url.path,
            error=type(exc).__name__,
            request_id=request_id,
        )
        alert_enabled = error_alert_notifications_enabled(resolved_settings)
        public_message = (
            "系统暂时遇到问题，后台已收到告警。请稍后再试。"
            if alert_enabled
            else "系统暂时遇到问题，请稍后再试。若问题持续，请联系管理员并提供 request_id。"
        )
        details = f"{type(exc).__name__}: {exc}"
        response = api_error_response_with(
            status=500,
            message=public_message,
            details=details,
            code="internal_error",
            request_id=request_id,
        )
        if alert_enabled:
            response.background = BackgroundTask(
                _send_error_alert,
                settings=resolved_settings,
                alert=_build_error_alert(
                    request=request,
                    status=500,
                    code="internal_error",
                    public_message=public_message,
                    technical_message=f"{type(exc).__name__}: {exc}",
                    details=details,
                    request_id=request_id,
                ),
            )
        return response

    app.include_router(create_router())

    if resolved_settings.static_dir.exists():
        app.mount(
            "/",
            StaticFiles(directory=resolved_settings.static_dir, html=True),
            name="static",
        )

    return app


app = create_app()


def _should_alert_api_error(exc: APIError) -> bool:
    if _is_content_policy_error(exc):
        return False
    if exc.code in _ALERTABLE_ERROR_CODES:
        return not (exc.code == "upstream_error" and exc.status < 500)
    return exc.status >= 500


def _should_use_operational_response(exc: APIError) -> bool:
    return exc.status >= 500 or exc.code.startswith("upstream_")


def _public_operational_error_message(exc: APIError, *, alert_enabled: bool) -> str:
    base = _base_operational_message(exc).rstrip("。")
    if _is_content_policy_error(exc):
        return f"{base}。"
    if exc.code == "upstream_content_policy":
        return f"{base}。"
    if alert_enabled:
        return f"{base}，后台已收到告警。请稍后再试。"
    return f"{base}。若问题持续，请联系管理员并提供 request_id。"


def _base_operational_message(exc: APIError) -> str:
    if _is_content_policy_error(exc) or exc.code == "upstream_content_policy":
        return "这次提示词没有通过上游内容审核，请调整描述后重试。"
    if exc.code == "upstream_rate_limited":
        return "图片生成服务当前请求较多，请稍后再试。"
    if exc.code == "upstream_timeout":
        return "图片生成服务响应超时，请稍后再试。"
    if exc.code == "upstream_network_error":
        return "暂时无法连接图片生成服务，请稍后再试。"
    if exc.code == "upstream_invalid_response":
        return "图片生成服务返回了无法解析的响应，请稍后再试。"
    if exc.code == "upstream_image_too_large":
        return "上游返回的图片超过了大小限制，请降低尺寸或质量后重试。"
    if exc.code == "upstream_no_image":
        return "路线图 AI 底图这次没有生成成功，请稍后再试。"
    if exc.code == "upstream_blocked":
        return "图片生成服务被上游临时拦截，请稍后再试或联系管理员。"
    if exc.code == "upstream_error":
        return "图片生成服务暂时不可用，请稍后再试。"
    if exc.status >= 500:
        return "系统暂时遇到问题，请稍后再试。"
    return redact_sensitive_text(exc.message, limit=500) or "系统暂时遇到问题，请稍后再试。"


def _is_content_policy_error(exc: APIError) -> bool:
    if exc.code == "upstream_content_policy":
        return True
    if exc.code.startswith("upstream_"):
        return False
    haystack = f"{exc.message}\n{exc.details or ''}".lower()
    return any(
        needle in haystack
        for needle in (
            "content policy",
            "not allowed",
            "disallowed",
            "policy violation",
        )
    )


def _public_operational_error_details(exc: APIError) -> str | None:
    details = redact_sensitive_text(exc.details or exc.message, limit=3600)
    if not details:
        return None
    return details


def _build_error_alert(
    *,
    request: Request,
    status: int,
    code: str,
    public_message: str,
    technical_message: str,
    details: str | None,
    request_id: str | None = None,
) -> ErrorAlert:
    return ErrorAlert(
        request_id=request_id or get_request_id(),
        method=request.method,
        path=request.url.path,
        status=status,
        code=code,
        client=request.client.host if request.client else "",
        public_message=public_message,
        technical_message=technical_message,
        details=details,
    )


async def _send_error_alert(*, settings: Settings, alert: ErrorAlert) -> None:
    result = await send_error_alert_notification(settings=settings, alert=alert)
    if not result.sent:
        log_event(
            logger,
            logging.WARNING,
            "error_alert_notification_failed",
            status=result.status,
            error=redact_sensitive_text(result.error, limit=300),
            request_id=alert.request_id,
        )


def _request_id_from_scope(request: Request) -> str:
    request_id = str(request.scope.get("picgen_request_id") or "").strip()
    return request_id or get_request_id()

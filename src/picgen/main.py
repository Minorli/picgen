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

from . import __version__
from .auth import AuthStore
from .config import Settings
from .errors import APIError
from .logging_config import configure_logging, get_logger, log_event
from .middleware import (
    BodySizeLimitMiddleware,
    ProxyAuthMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    api_error_response,
)
from .routes import create_router
from .storage import prune_old_outputs
from .upstream import HttpxAsyncClient

logger = get_logger("picgen.app")

# How often the background task re-checks for day-folders past the retention window.
_RETENTION_SWEEP_SECONDS = 6 * 60 * 60


async def _retention_loop(settings: Settings) -> None:
    """Periodically prune outputs older than the configured retention window.

    Runs only when ``storage_retention_days > 0``; pruning itself is blocking
    filesystem I/O, so it is dispatched to a worker thread.
    """

    if settings.storage_retention_days <= 0:
        return
    while True:
        try:
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
        except Exception as exc:  # pragma: no cover - defensive; never kill the loop
            log_event(logger, logging.WARNING, "storage_retention_error", error=str(exc))
        await asyncio.sleep(_RETENTION_SWEEP_SECONDS)


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
    resolved_settings = settings or Settings.from_env()
    configure_logging(resolved_settings.log_level, resolved_settings.log_format)
    auth_store = AuthStore(resolved_settings.resolved_auth_db_path)

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

    if resolved_settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved_settings.cors_allow_origins,
            allow_credentials=resolved_settings.cors_allow_credentials,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"],
        )

    if resolved_settings.proxy_auth_token:
        app.add_middleware(ProxyAuthMiddleware, token=resolved_settings.proxy_auth_token)

    app.add_middleware(
        RateLimitMiddleware,
        per_minute=resolved_settings.rate_limit_per_minute,
        burst=resolved_settings.rate_limit_burst,
        trust_forwarded_for=resolved_settings.trust_forwarded_for,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=resolved_settings.max_request_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError) -> Any:
        return api_error_response(exc)

    app.include_router(create_router())

    if resolved_settings.static_dir.exists():
        app.mount(
            "/",
            StaticFiles(directory=resolved_settings.static_dir, html=True),
            name="static",
        )

    return app


app = create_app()

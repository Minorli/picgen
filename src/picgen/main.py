from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import Settings
from .errors import APIError
from .logging_config import configure_logging, get_logger
from .middleware import (
    BodySizeLimitMiddleware,
    ProxyAuthMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    api_error_response,
)
from .routes import create_router
from .upstream import HttpxAsyncClient

logger = get_logger("picgen.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    configure_logging(resolved_settings.log_level, resolved_settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings.outputs_dir.mkdir(parents=True, exist_ok=True)
        client = HttpxAsyncClient(
            total_timeout=resolved_settings.upstream_timeout_seconds,
            connect_timeout=resolved_settings.upstream_connect_timeout_seconds,
            max_connections=resolved_settings.upstream_max_connections,
            max_keepalive=resolved_settings.upstream_max_keepalive,
            max_retries=resolved_settings.upstream_max_retries,
            retry_backoff=resolved_settings.upstream_retry_backoff,
        )
        app.state.upstream_client = client
        try:
            yield
        finally:
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

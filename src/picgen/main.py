from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .errors import APIError
from .routes import create_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    app = FastAPI(title="PicGen Console")
    app.state.settings = resolved_settings

    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={
                "error": exc.message,
                "details": exc.details,
            },
        )

    app.include_router(create_router())

    if resolved_settings.static_dir.exists():
        app.mount("/", StaticFiles(directory=resolved_settings.static_dir, html=True), name="static")

    return app


app = create_app()

from __future__ import annotations

import base64
import logging
import time
from http import HTTPStatus
from typing import Any

import anyio
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import FileResponse, JSONResponse

from . import __version__
from .config import Settings
from .errors import APIError
from .logging_config import get_logger, log_event
from .schemas import (
    ConfigResponse,
    EditRequest,
    FilePayload,
    GenerateRequest,
    HealthResponse,
    ImageResultResponse,
    ReadinessResponse,
    ResponsesImageRequest,
)
from .storage import detect_image_mime, resolve_storage_path, sanitize_filename
from .upstream import (
    openai_image_options,
    prepare_image_payload,
    request_metadata,
    sibling_endpoint_url,
    validate_url,
)
from .upstream.client import UpstreamClient

logger = get_logger("picgen.routes")

JSON_BODY = Body(...)

def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_client(request: Request) -> UpstreamClient:
    return request.app.state.upstream_client


def _validate_image_size(part: FilePayload, max_image_bytes: int) -> dict[str, Any]:
    data = part.decoded_bytes()
    if len(data) > max_image_bytes:
        raise APIError(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            f"图片过大，最大允许 {max_image_bytes // 1024} KB",
            code="payload_too_large",
        )
    file_name = sanitize_filename(part.name or "image.png")
    content_type = part.type.strip() or detect_image_mime(data)
    return {
        "field_name": "image",
        "filename": file_name,
        "content_type": content_type,
        "data": data,
    }


def _prepare_mask(part: FilePayload, max_image_bytes: int) -> dict[str, Any]:
    file_info = _validate_image_size(part, max_image_bytes)
    file_info["field_name"] = "mask"
    return file_info


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/config", response_model=ConfigResponse)
    async def config(request: Request) -> ConfigResponse:
        settings = get_settings(request)
        return ConfigResponse(
            generate_url=settings.default_generate_url,
            edit_url=settings.default_edit_url,
            responses_url=settings.default_responses_url,
            default_model=settings.default_model,
            default_responses_model=settings.default_responses_model,
            default_size=settings.default_size,
            has_default_api_key=bool(settings.default_api_key),
            storage_dir=str(settings.outputs_dir),
            max_image_bytes=settings.max_image_bytes,
            max_request_body_bytes=settings.max_request_body_bytes,
            rate_limit_per_minute=settings.rate_limit_per_minute,
            upstream_timeout_seconds=settings.upstream_timeout_seconds,
        )

    @router.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(ok=True)

    @router.get("/api/ready", response_model=ReadinessResponse)
    async def ready(
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
    ) -> ReadinessResponse:
        storage_ok = True
        try:
            settings.outputs_dir.mkdir(parents=True, exist_ok=True)
            probe = settings.outputs_dir / ".ready"
            probe.write_text("ok")
            probe.unlink(missing_ok=True)
        except Exception:
            storage_ok = False
        return ReadinessResponse(
            ok=storage_ok and client is not None,
            storage_writable=storage_ok,
            upstream_client_ready=client is not None,
            version=__version__,
        )

    @router.get("/files/{relative_path:path}")
    async def files(relative_path: str, request: Request) -> FileResponse:
        settings = get_settings(request)
        target_path = resolve_storage_path(settings.data_dir, relative_path)
        if not target_path.is_file():
            raise APIError(HTTPStatus.NOT_FOUND, "文件不存在", code="not_found")
        return FileResponse(
            target_path,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @router.post("/api/generate")
    async def generate(
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
    ) -> JSONResponse:
        return JSONResponse(
            await _with_timing("/api/generate", handle_generate, body, settings, client)
        )

    @router.post("/api/edit")
    async def edit(
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
    ) -> JSONResponse:
        return JSONResponse(
            await _with_timing("/api/edit", handle_edit, body, settings, client)
        )

    @router.post("/api/responses-image")
    async def responses_image(
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
    ) -> JSONResponse:
        return JSONResponse(
            await _with_timing("/api/responses-image", handle_responses_image, body, settings, client)
        )

    return router


async def _with_timing(
    path: str,
    handler: Any,
    body: Any,
    settings: Settings,
    client: UpstreamClient,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    log_event(logger, logging.INFO, "local_post_start", path=path)
    try:
        result = await handler(body, settings, client)
    except APIError as exc:
        log_event(
            logger,
            logging.WARNING,
            "local_post_api_error",
            path=path,
            status=exc.status,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            message=exc.message,
            code=exc.code,
        )
        raise
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "local_post_unhandled",
            path=path,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            error=type(exc).__name__,
        )
        raise APIError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "本地服务发生未预期错误",
            f"{type(exc).__name__}: {exc}",
            code="internal_error",
        ) from exc
    log_event(
        logger,
        logging.INFO,
        "local_post_ok",
        path=path,
        elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
    )
    return result


async def handle_generate(
    body: Any, settings: Settings, client: UpstreamClient
) -> dict[str, Any]:
    payload = _ensure_dict(body)
    parsed = _validate_request(GenerateRequest, payload)

    endpoint_url = validate_url(
        parsed.endpoint_url or settings.default_generate_url,
        "生成接口 URL",
    )
    model = (parsed.model or settings.default_model).strip() or settings.default_model
    size = (parsed.size or settings.default_size).strip() or settings.default_size
    api_key = (parsed.api_key or settings.default_api_key).strip()
    image_options = openai_image_options(payload)

    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key", code="bad_request")

    upstream_payload: dict[str, Any] = {
        "model": model,
        "prompt": parsed.prompt,
        **image_options,
    }
    if size and size != "auto":
        upstream_payload["size"] = size

    upstream_response = await client.run_json(
        endpoint_url, api_key, upstream_payload, settings.upstream_user_agent
    )
    metadata = request_metadata({**payload, **image_options}, size=size)

    return await _finalize_image_response(
        upstream_response=upstream_response,
        settings=settings,
        client=client,
        save_context={
            "mode": "generate",
            "prompt": parsed.prompt,
            "model": model,
            "endpoint_url": endpoint_url,
            "transport": "images-generate",
            **metadata,
        },
        extra={
            "mode": "generate",
            "prompt": parsed.prompt,
            "model": model,
            **metadata,
            "endpoint_url": endpoint_url,
        },
    )


async def handle_edit(
    body: Any, settings: Settings, client: UpstreamClient
) -> dict[str, Any]:
    payload = _ensure_dict(body)
    if not payload.get("image"):
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 image 文件", code="bad_request")
    parsed = _validate_request(EditRequest, payload)

    endpoint_url = validate_url(
        parsed.endpoint_url or settings.default_edit_url,
        "编辑接口 URL",
    )
    model = (parsed.model or settings.default_model).strip() or settings.default_model
    api_key = (parsed.api_key or settings.default_api_key).strip()
    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key", code="bad_request")

    image_part = _validate_image_size(parsed.image, settings.max_image_bytes)
    mask_part = _prepare_mask(parsed.mask, settings.max_image_bytes) if parsed.mask else None

    files_for_multipart = [part for part in (image_part, mask_part) if part is not None]
    size = (parsed.size or "").strip()
    image_options = openai_image_options(payload)
    fields: dict[str, Any] = {
        "model": model,
        "prompt": parsed.prompt,
        **image_options,
    }
    if size and size != "auto":
        fields["size"] = size

    upstream_response = await client.run_multipart(
        endpoint_url, api_key, fields, files_for_multipart, settings.upstream_user_agent
    )
    metadata = request_metadata({**payload, **image_options}, size=size or None)
    mode = (parsed.mode or "edit").strip() or "edit"

    return await _finalize_image_response(
        upstream_response=upstream_response,
        settings=settings,
        client=client,
        save_context={
            "mode": mode,
            "prompt": parsed.prompt,
            "model": model,
            "endpoint_url": endpoint_url,
            "source_image_name": image_part["filename"],
            "mask_image_name": mask_part["filename"] if mask_part else None,
            "transport": "images-edit",
            **metadata,
        },
        extra={
            "mode": mode,
            "prompt": parsed.prompt,
            "model": model,
            **metadata,
            "endpoint_url": endpoint_url,
            "source_image_name": image_part["filename"],
            "mask_image_name": mask_part["filename"] if mask_part else None,
        },
    )


def _responses_input_content(prompt: str, image_file_id: str | None) -> list[dict[str, str]]:
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
    if image_file_id is not None:
        content.append({"type": "input_image", "file_id": image_file_id})
    return content


def _responses_inline_input_content(
    prompt: str, image_part: dict[str, Any] | None
) -> list[dict[str, str]]:
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
    if image_part is not None:
        image_b64 = base64.b64encode(image_part["data"]).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{image_part['content_type']};base64,{image_b64}",
            }
        )
    return content


async def handle_responses_image(
    body: Any, settings: Settings, client: UpstreamClient
) -> dict[str, Any]:
    payload = _ensure_dict(body)
    parsed = _validate_request(ResponsesImageRequest, payload)

    endpoint_url = validate_url(
        parsed.endpoint_url or settings.default_responses_url,
        "Responses 图像接口 URL",
    )
    model = (parsed.model or settings.default_responses_model).strip() or settings.default_responses_model
    api_key = (parsed.api_key or settings.default_api_key).strip()
    size = (parsed.size or settings.default_size).strip() or settings.default_size
    image_options = openai_image_options(payload)

    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key", code="bad_request")

    image_part: dict[str, Any] | None = None
    if parsed.image is not None and parsed.image.data_url:
        image_part = _validate_image_size(parsed.image, settings.max_image_bytes)

    image_file_id: str | None = None
    files_endpoint_url: str | None = None
    upload_error: APIError | None = None
    if image_part is not None:
        files_endpoint_url = sibling_endpoint_url(endpoint_url, "files")
        try:
            upload_response = await client.run_file_upload(
                files_endpoint_url,
                api_key,
                image_part,
                settings.upstream_user_agent,
            )
            image_file_id = str(upload_response.get("id") or "").strip()
        except APIError as exc:
            upload_error = exc
            if not parsed.allow_inline_fallback:
                raise
            log_event(
                logger,
                logging.WARNING,
                "responses_image_file_upload_fallback",
                endpoint_url=endpoint_url,
                files_endpoint_url=files_endpoint_url,
                filename=image_part["filename"],
                file_bytes=len(image_part["data"]),
                upload_error=exc.message,
            )

    tool: dict[str, Any] = {"type": "image_generation"}
    if size and size != "auto":
        tool["size"] = size
    for key in ("quality", "background", "output_format", "output_compression", "moderation"):
        if key in image_options:
            tool[key] = image_options[key]

    upstream_payload = {
        "model": model,
        "stream": True,
        "input": [
            {
                "role": "user",
                "content": (
                    _responses_input_content(parsed.prompt, image_file_id)
                    if upload_error is None
                    else _responses_inline_input_content(parsed.prompt, image_part)
                ),
            }
        ],
        "tools": [tool],
    }

    upstream_response = await client.run_responses(
        endpoint_url, api_key, upstream_payload, settings.upstream_user_agent
    )
    metadata = request_metadata({**payload, **image_options}, size=size)
    mode = (parsed.mode or ("reference" if image_part else "responses")).strip() or "responses"

    return await _finalize_image_response(
        upstream_response=upstream_response,
        settings=settings,
        client=client,
        save_context={
            "mode": mode,
            "prompt": parsed.prompt,
            "model": model,
            "endpoint_url": endpoint_url,
            "files_endpoint_url": files_endpoint_url,
            "source_image_name": image_part["filename"] if image_part else None,
            "source_file_id": image_file_id,
            "file_upload_fallback": bool(upload_error),
            "file_upload_error": upload_error.message if upload_error else None,
            "transport": "responses-image",
            **metadata,
        },
        extra={
            "mode": mode,
            "prompt": parsed.prompt,
            "model": model,
            **metadata,
            "endpoint_url": endpoint_url,
            "files_endpoint_url": files_endpoint_url,
            "source_image_name": image_part["filename"] if image_part else None,
            "source_file_id": image_file_id,
            "file_upload_fallback": bool(upload_error),
        },
    )


async def _finalize_image_response(
    *,
    upstream_response: dict[str, Any],
    settings: Settings,
    client: UpstreamClient,
    save_context: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    fetch_remote_sync = _make_remote_fetcher(client)
    saved = await anyio.to_thread.run_sync(
        lambda: prepare_image_payload(
            upstream_response,
            data_dir=settings.data_dir,
            outputs_dir=settings.outputs_dir,
            user_agent=settings.upstream_user_agent,
            save_context=save_context,
            fetch_remote=fetch_remote_sync,
        )
    )
    return {**extra, **saved}


def _make_remote_fetcher(client: UpstreamClient) -> Any:
    """Bridge async image download into the sync prepare_image_payload helper.

    `prepare_image_payload` runs in a worker thread; this fetcher schedules the
    async download back onto the main event loop without blocking it.
    """

    def fetcher(url: str, user_agent: str) -> tuple[bytes, str]:
        return anyio.from_thread.run(client.fetch_image, url, user_agent)

    return fetcher


def _ensure_dict(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise APIError(HTTPStatus.BAD_REQUEST, "请求体必须是 JSON 对象", code="bad_request")
    return payload


def _validate_request(model_cls: Any, payload: dict[str, Any]) -> Any:
    try:
        return model_cls.model_validate(payload)
    except Exception as exc:
        message = _first_error_message(exc) or "请求参数无效"
        raise APIError(HTTPStatus.BAD_REQUEST, message, str(exc), code="validation_error") from exc


def _first_error_message(exc: Exception) -> str | None:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            issues = errors()
            if issues:
                first = issues[0]
                msg = first.get("msg") or first.get("message") or ""
                if isinstance(msg, str):
                    cleaned = msg.removeprefix("Value error,").strip()
                    return cleaned or None
        except Exception:
            return None
    return None


__all__ = [
    "ImageResultResponse",
    "create_router",
    "handle_edit",
    "handle_generate",
    "handle_responses_image",
]

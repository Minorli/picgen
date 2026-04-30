from __future__ import annotations

import time
import uuid
from http import HTTPStatus
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse

from .config import Settings
from .errors import APIError
from .storage import detect_image_mime, resolve_storage_path, sanitize_filename
from .upstream import (
    debug_log,
    decode_base64_blob,
    openai_image_options,
    prepare_image_payload,
    request_metadata,
    run_upstream_json,
    run_upstream_multipart,
    validate_url,
)

JSON_BODY = Body(...)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def ensure_json_object(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise APIError(HTTPStatus.BAD_REQUEST, "请求体必须是 JSON 对象")
    return payload


def parse_file_payload(payload: dict[str, Any] | None, field_name: str, required: bool) -> dict[str, Any] | None:
    if not payload:
        if required:
            raise APIError(HTTPStatus.BAD_REQUEST, f"缺少 {field_name} 文件")
        return None

    raw_bytes = decode_base64_blob(str(payload.get("data_url", "")))
    file_name = sanitize_filename(str(payload.get("name", "")) or f"{field_name}.png")
    content_type = str(payload.get("type", "")).strip() or detect_image_mime(raw_bytes)

    return {
        "field_name": field_name,
        "filename": file_name,
        "content_type": content_type,
        "data": raw_bytes,
    }


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/config")
    def config(request: Request) -> dict[str, object]:
        settings = get_settings(request)
        return {
            "generate_url": settings.default_generate_url,
            "edit_url": settings.default_edit_url,
            "default_model": settings.default_model,
            "default_size": settings.default_size,
            "has_default_api_key": bool(settings.default_api_key),
            "storage_dir": str(settings.outputs_dir),
        }

    @router.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/files/{relative_path:path}")
    def files(relative_path: str, request: Request) -> FileResponse:
        settings = get_settings(request)
        target_path = resolve_storage_path(settings.data_dir, relative_path)
        if not target_path.is_file():
            raise APIError(HTTPStatus.NOT_FOUND, "文件不存在")
        return FileResponse(target_path, headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @router.post("/api/generate")
    def generate(request: Request, body: Any = JSON_BODY) -> dict[str, Any]:
        settings = get_settings(request)
        payload = ensure_json_object(body)
        request_id = uuid.uuid4().hex[:8]
        started_at = time.perf_counter()
        debug_log("local_post_start", request_id=request_id, path="/api/generate")
        try:
            response_payload = handle_generate(payload, settings)
        except APIError as exc:
            debug_log(
                "local_post_api_error",
                request_id=request_id,
                path="/api/generate",
                status=exc.status,
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                message=exc.message,
            )
            raise
        debug_log(
            "local_post_ok",
            request_id=request_id,
            path="/api/generate",
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
        )
        return response_payload

    @router.post("/api/edit")
    def edit(request: Request, body: Any = JSON_BODY) -> dict[str, Any]:
        settings = get_settings(request)
        payload = ensure_json_object(body)
        request_id = uuid.uuid4().hex[:8]
        started_at = time.perf_counter()
        debug_log("local_post_start", request_id=request_id, path="/api/edit")
        try:
            response_payload = handle_edit(payload, settings)
        except APIError as exc:
            debug_log(
                "local_post_api_error",
                request_id=request_id,
                path="/api/edit",
                status=exc.status,
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                message=exc.message,
            )
            raise
        debug_log(
            "local_post_ok",
            request_id=request_id,
            path="/api/edit",
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
        )
        return response_payload

    return router


def handle_generate(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    prompt = str(payload.get("prompt", ""))
    if not prompt.strip():
        raise APIError(HTTPStatus.BAD_REQUEST, "生成提示词不能为空")

    endpoint_url = validate_url(
        str(payload.get("endpoint_url") or settings.default_generate_url),
        "生成接口 URL",
    )
    model = str(payload.get("model") or settings.default_model).strip() or settings.default_model
    size = str(payload.get("size") or settings.default_size).strip() or settings.default_size
    api_key = str(payload.get("api_key") or settings.default_api_key).strip()
    image_options = openai_image_options(payload)

    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key")

    upstream_payload = {
        "model": model,
        "prompt": prompt,
        **image_options,
    }
    if size and size != "auto":
        upstream_payload["size"] = size

    upstream_response = run_upstream_json(endpoint_url, api_key, upstream_payload, settings.upstream_user_agent)
    metadata = request_metadata({**payload, **image_options}, size=size)

    return {
        "mode": "generate",
        "prompt": prompt,
        "model": model,
        **metadata,
        "endpoint_url": endpoint_url,
        **prepare_image_payload(
            upstream_response,
            data_dir=settings.data_dir,
            outputs_dir=settings.outputs_dir,
            user_agent=settings.upstream_user_agent,
            save_context={
                "mode": "generate",
                "prompt": prompt,
                "model": model,
                "endpoint_url": endpoint_url,
                **metadata,
            },
        ),
    }


def handle_edit(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    prompt = str(payload.get("prompt", ""))
    if not prompt.strip():
        raise APIError(HTTPStatus.BAD_REQUEST, "编辑指令不能为空")

    endpoint_url = validate_url(
        str(payload.get("endpoint_url") or settings.default_edit_url),
        "编辑接口 URL",
    )
    model = str(payload.get("model") or settings.default_model).strip() or settings.default_model
    api_key = str(payload.get("api_key") or settings.default_api_key).strip()

    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key")

    image_part = parse_file_payload(payload.get("image"), "image[]", required=True)
    mask_part = parse_file_payload(payload.get("mask"), "mask", required=False)

    files = [part for part in [image_part, mask_part] if part is not None]
    size = str(payload.get("size") or "").strip()
    image_options = openai_image_options(payload)
    fields: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        **image_options,
    }
    if size and size != "auto":
        fields["size"] = size

    upstream_response = run_upstream_multipart(
        endpoint_url,
        api_key,
        fields=fields,
        files=files,
        user_agent=settings.upstream_user_agent,
    )
    metadata = request_metadata({**payload, **image_options}, size=size or None)

    return {
        "mode": "edit",
        "prompt": prompt,
        "model": model,
        **metadata,
        "endpoint_url": endpoint_url,
        "source_image_name": image_part["filename"] if image_part else None,
        "mask_image_name": mask_part["filename"] if mask_part else None,
        **prepare_image_payload(
            upstream_response,
            data_dir=settings.data_dir,
            outputs_dir=settings.outputs_dir,
            user_agent=settings.upstream_user_agent,
            save_context={
                "mode": "edit",
                "prompt": prompt,
                "model": model,
                "endpoint_url": endpoint_url,
                "source_image_name": image_part["filename"] if image_part else None,
                "mask_image_name": mask_part["filename"] if mask_part else None,
                **metadata,
            },
        ),
    }

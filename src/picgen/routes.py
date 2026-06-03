from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections.abc import Awaitable, Callable
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
    CopyrightRiskRequest,
    EditRequest,
    FilePayload,
    GenerateRequest,
    HealthResponse,
    ImageResultResponse,
    ReadinessResponse,
    ResponsesImageRequest,
)
from .storage import (
    detect_image_mime,
    resolve_storage_path,
    sanitize_filename,
)
from .upstream import (
    compact_raw_response,
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


def _request_image_parts(
    *,
    image: FilePayload | None,
    images: list[FilePayload],
    max_image_bytes: int,
) -> list[dict[str, Any]]:
    source_images = images or ([image] if image is not None else [])
    image_parts: list[dict[str, Any]] = []
    for index, source_image in enumerate(source_images):
        part = _validate_image_size(source_image, max_image_bytes)
        part["field_name"] = "image"
        part["role"] = source_image.role or ("style_template" if index == 0 and len(source_images) > 1 else "material")
        part["index"] = index
        image_parts.append(part)
    return image_parts


def _image_reference_metadata(image_parts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "source_image_names": [str(part["filename"]) for part in image_parts],
        "source_image_roles": [str(part.get("role") or "") for part in image_parts],
        "source_image_count": len(image_parts),
        "source_image_name": str(image_parts[0]["filename"]) if image_parts else None,
    }


def _candidate_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _extend_candidate_items(target: dict[str, Any], source: dict[str, Any], limit: int) -> None:
    target_data = target.setdefault("data", [])
    if not isinstance(target_data, list):
        target_data = []
        target["data"] = target_data
    for item in _candidate_items(source):
        if len(target_data) >= limit:
            break
        target_data.append(item)


def _error_mentions_sample_count(exc: APIError) -> bool:
    haystack = f"{exc.message}\n{exc.details or ''}".lower()
    # Be specific: a bare " n" substring matches ordinary prose ("is not
    # allowed", "no credit") and would wrongly strip `n` on, e.g., a content
    # moderation 400. Only react to errors that actually name the sample-count
    # parameter.
    needles = (
        '"n"',
        "'n'",
        "parameter n",
        "param n",
        "value of n",
        "n must",
        "sample",
        "best_of",
        "num_images",
        "n_images",
    )
    return any(needle in haystack for needle in needles)


def _should_retry_without_sample_count(exc: APIError, sample_count: int) -> bool:
    if sample_count <= 1:
        return False
    if exc.status == HTTPStatus.BAD_REQUEST:
        return _error_mentions_sample_count(exc)
    return exc.status in {
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }


async def _fill_candidates(
    *,
    initial: dict[str, Any],
    call_without_sample_count: Callable[[], Awaitable[dict[str, Any]]],
    sample_count: int,
) -> dict[str, Any]:
    """Top ``initial`` up to ``sample_count`` candidates.

    When the upstream ignores ``n`` and returns a single image per call, the
    missing images are fetched concurrently — each upstream call can take
    minutes, so issuing them serially would multiply end-to-end latency.
    Individual failures are tolerated: we return whatever candidates we managed
    to collect rather than discarding a successful first image.
    """

    deficit = sample_count - len(_candidate_items(initial))
    if deficit <= 0:
        return initial
    results = await asyncio.gather(
        *(call_without_sample_count() for _ in range(deficit)),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, dict):
            _extend_candidate_items(initial, result, sample_count)
    return initial


async def _run_multipart_candidates(
    *,
    client: UpstreamClient,
    endpoint_url: str,
    api_key: str,
    fields: dict[str, Any],
    files: list[dict[str, Any]],
    user_agent: str,
    sample_count: int,
) -> dict[str, Any]:
    fallback_fields = {key: value for key, value in fields.items() if key != "n"}

    async def _call_without_n() -> dict[str, Any]:
        return await client.run_multipart(endpoint_url, api_key, fallback_fields, files, user_agent)

    try:
        response = await client.run_multipart(endpoint_url, api_key, fields, files, user_agent)
    except APIError as exc:
        if not _should_retry_without_sample_count(exc, sample_count):
            raise
        log_event(
            logger,
            logging.WARNING,
            "images_edit_sample_count_fallback",
            endpoint_url=endpoint_url,
            sample_count=sample_count,
            status=exc.status,
            message=exc.message,
        )
        response = await _call_without_n()

    return await _fill_candidates(
        initial=response,
        call_without_sample_count=_call_without_n,
        sample_count=sample_count,
    )


async def _run_json_candidates(
    *,
    client: UpstreamClient,
    endpoint_url: str,
    api_key: str,
    payload: dict[str, Any],
    user_agent: str,
    sample_count: int,
) -> dict[str, Any]:
    fallback_payload = {key: value for key, value in payload.items() if key != "n"}

    async def _call_without_n() -> dict[str, Any]:
        return await client.run_json(endpoint_url, api_key, fallback_payload, user_agent)

    try:
        response = await client.run_json(endpoint_url, api_key, payload, user_agent)
    except APIError as exc:
        if not _should_retry_without_sample_count(exc, sample_count):
            raise
        log_event(
            logger,
            logging.WARNING,
            "images_generate_sample_count_fallback",
            endpoint_url=endpoint_url,
            sample_count=sample_count,
            status=exc.status,
            message=exc.message,
        )
        response = await _call_without_n()

    return await _fill_candidates(
        initial=response,
        call_without_sample_count=_call_without_n,
        sample_count=sample_count,
    )


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

    @router.post("/api/copyright-risk")
    async def copyright_risk(
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
    ) -> JSONResponse:
        return JSONResponse(
            await _with_timing("/api/copyright-risk", handle_copyright_risk, body, settings, client)
        )

    return router


def _copyright_risk_prompt(parsed: CopyrightRiskRequest) -> str:
    context = parsed.context.strip()
    prompt = parsed.prompt.strip()
    return (
        "你是图片版权与商标风险审查助手。请基于用户提供的最终生成图和上下文，"
        "用中文给出简短、务实、非法律意见的风险提醒。\n"
        "重点查看：商标/Logo、赛事或活动标识、奥运/冬奥等受保护元素、名人肖像、"
        "第三方品牌、IP角色、受版权保护的艺术风格或包装版式、可识别摄影作品。\n"
        "已知前提：图片素材通常来自用户自己，用户声称有授权，所以总体风险可能不高；"
        "但仍需指出画面元素本身可能触发复核的地方。\n"
        "输出格式：\n"
        "风险等级：低/中/高\n"
        "可能风险点：用 1-4 条短句\n"
        "建议：用 1-3 条短句\n"
        "如果没有明显风险，说明“未见明显第三方侵权元素”，但提醒商用前确认授权链。\n\n"
        f"用户提示词：{prompt or '未提供'}\n"
        f"生成上下文：{context or '未提供'}"
    )


def _extract_text_output(payload: dict[str, Any]) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    output = payload.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_text = block.get("text")
                    if isinstance(block_text, str) and block_text.strip():
                        chunks.append(block_text.strip())
            item_text = item.get("text")
            if isinstance(item_text, str) and item_text.strip():
                chunks.append(item_text.strip())
        if chunks:
            return "\n".join(chunks)

    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                maybe_text = item.get("text") or item.get("content")
                if isinstance(maybe_text, str) and maybe_text.strip():
                    return maybe_text.strip()
    return ""


async def handle_copyright_risk(
    body: Any, settings: Settings, client: UpstreamClient
) -> dict[str, Any]:
    payload = _ensure_dict(body)
    parsed = _validate_request(CopyrightRiskRequest, payload)

    endpoint_url = validate_url(
        parsed.endpoint_url or settings.default_responses_url,
        "Responses 图像接口 URL",
    )
    model = (parsed.model or settings.default_responses_model).strip() or settings.default_responses_model
    api_key = (parsed.api_key or settings.default_api_key).strip()
    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key", code="bad_request")

    image_parts = _request_image_parts(
        image=None,
        images=parsed.images,
        max_image_bytes=settings.max_image_bytes,
    )
    content = _responses_inline_input_content(_copyright_risk_prompt(parsed), image_parts)
    upstream_payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": content,
            }
        ],
    }
    upstream_response = await client.run_responses(
        endpoint_url, api_key, upstream_payload, settings.upstream_user_agent
    )
    return {
        "model": model,
        "risk_text": _extract_text_output(upstream_response) or "未能解析风险提醒文本。",
        "raw_response": compact_raw_response(upstream_response),
    }


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
    if parsed.sample_count > 1:
        upstream_payload["n"] = parsed.sample_count

    upstream_response = await _run_json_candidates(
        client=client,
        endpoint_url=endpoint_url,
        api_key=api_key,
        payload=upstream_payload,
        user_agent=settings.upstream_user_agent,
        sample_count=parsed.sample_count,
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
            "sample_count": parsed.sample_count,
            "logo_requested": parsed.logo_requested,
            **metadata,
        },
        extra={
            "mode": "generate",
            "prompt": parsed.prompt,
            "model": model,
            "logo_requested": parsed.logo_requested,
            "sample_count": parsed.sample_count,
            **metadata,
            "endpoint_url": endpoint_url,
        },
    )


async def handle_edit(
    body: Any, settings: Settings, client: UpstreamClient
) -> dict[str, Any]:
    payload = _ensure_dict(body)
    if not payload.get("image") and not payload.get("images"):
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

    image_parts = _request_image_parts(
        image=parsed.image,
        images=parsed.images,
        max_image_bytes=settings.max_image_bytes,
    )
    if not image_parts:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 image 文件", code="bad_request")
    mask_part = _prepare_mask(parsed.mask, settings.max_image_bytes) if parsed.mask else None

    files_for_multipart = [*image_parts, *([mask_part] if mask_part else [])]
    size = (parsed.size or "").strip()
    image_options = openai_image_options(payload)
    fields: dict[str, Any] = {
        "model": model,
        "prompt": parsed.prompt,
        **image_options,
    }
    if size and size != "auto":
        fields["size"] = size
    if parsed.sample_count > 1:
        fields["n"] = parsed.sample_count

    upstream_response = await _run_multipart_candidates(
        client=client,
        endpoint_url=endpoint_url,
        api_key=api_key,
        fields=fields,
        files=files_for_multipart,
        user_agent=settings.upstream_user_agent,
        sample_count=parsed.sample_count,
    )
    metadata = request_metadata({**payload, **image_options}, size=size or None)
    mode = (parsed.mode or "edit").strip() or "edit"
    image_metadata = _image_reference_metadata(image_parts)

    return await _finalize_image_response(
        upstream_response=upstream_response,
        settings=settings,
        client=client,
        save_context={
            "mode": mode,
            "prompt": parsed.prompt,
            "model": model,
            "endpoint_url": endpoint_url,
            **image_metadata,
            "mask_image_name": mask_part["filename"] if mask_part else None,
            "transport": "images-edit",
            "sample_count": parsed.sample_count,
            "logo_requested": parsed.logo_requested,
            **metadata,
        },
        extra={
            "mode": mode,
            "prompt": parsed.prompt,
            "model": model,
            "logo_requested": parsed.logo_requested,
            **metadata,
            "endpoint_url": endpoint_url,
            **image_metadata,
            "mask_image_name": mask_part["filename"] if mask_part else None,
            "sample_count": parsed.sample_count,
        },
    )


def _responses_input_content(prompt: str, image_file_ids: list[str]) -> list[dict[str, str]]:
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
    for image_file_id in image_file_ids:
        content.append({"type": "input_image", "file_id": image_file_id})
    return content


def _responses_inline_input_content(
    prompt: str, image_parts: list[dict[str, Any]]
) -> list[dict[str, str]]:
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
    for image_part in image_parts:
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

    image_parts = _request_image_parts(
        image=parsed.image,
        images=parsed.images,
        max_image_bytes=settings.max_image_bytes,
    )
    image_parts = [part for part in image_parts if part.get("data")]

    image_file_ids: list[str] = []
    files_endpoint_url: str | None = None
    upload_error: APIError | None = None
    if image_parts:
        files_endpoint_url = sibling_endpoint_url(endpoint_url, "files")
        for image_part in image_parts:
            try:
                upload_response = await client.run_file_upload(
                    files_endpoint_url,
                    api_key,
                    image_part,
                    settings.upstream_user_agent,
                )
                image_file_id = str(upload_response.get("id") or "").strip()
                if image_file_id:
                    image_file_ids.append(image_file_id)
            except APIError as exc:
                upload_error = exc
                image_file_ids = []
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
                break

    tool: dict[str, Any] = {"type": "image_generation"}
    if size and size != "auto":
        tool["size"] = size
    if parsed.sample_count > 1:
        tool["n"] = parsed.sample_count
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
                    _responses_input_content(parsed.prompt, image_file_ids)
                    if upload_error is None
                    else _responses_inline_input_content(parsed.prompt, image_parts)
                ),
            }
        ],
        "tools": [tool],
    }

    upstream_response = await client.run_responses(
        endpoint_url, api_key, upstream_payload, settings.upstream_user_agent
    )
    metadata = request_metadata({**payload, **image_options}, size=size)
    mode = (parsed.mode or ("reference" if image_parts else "responses")).strip() or "responses"
    image_metadata = _image_reference_metadata(image_parts)

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
            **image_metadata,
            "source_file_id": image_file_ids[0] if image_file_ids else None,
            "source_file_ids": image_file_ids,
            "file_upload_fallback": bool(upload_error),
            "file_upload_error": upload_error.message if upload_error else None,
            "transport": "responses-image",
            "sample_count": parsed.sample_count,
            "logo_requested": parsed.logo_requested,
            **metadata,
        },
        extra={
            "mode": mode,
            "prompt": parsed.prompt,
            "model": model,
            "logo_requested": parsed.logo_requested,
            **metadata,
            "endpoint_url": endpoint_url,
            "files_endpoint_url": files_endpoint_url,
            **image_metadata,
            "source_file_id": image_file_ids[0] if image_file_ids else None,
            "source_file_ids": image_file_ids,
            "file_upload_fallback": bool(upload_error),
            "sample_count": parsed.sample_count,
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

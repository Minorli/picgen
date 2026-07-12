from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib import parse

from ..errors import APIError
from ..logging_config import get_logger, log_event
from ..storage import (
    detect_image_dimensions,
    detect_image_mime,
    is_decodable_image,
    resize_image_to_exact_size,
    save_output_image,
)

logger = get_logger("picgen.upstream.payload")

ImageTransform = Callable[[bytes, str, int], tuple[bytes, str, dict[str, object]]]

_IMAGE_OPTION_KEYS = ("quality", "background", "output_format", "output_compression", "moderation")
_RAW_IMAGE_KEYS = frozenset({"b64_json", "result", "partial_image_b64", "image_b64"})
_RAW_IMAGE_URL_KEYS = frozenset({"url", "image_url"})


def decode_base64_blob(blob: str) -> bytes:
    data = blob.strip()
    if not data:
        raise APIError(HTTPStatus.BAD_REQUEST, "图片内容为空", code="bad_request")
    if data.startswith("data:") and ";base64," in data:
        data = data.split(";base64,", 1)[1]
    try:
        return base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "图片内容不是有效的 Base64 数据",
            code="invalid_image",
        ) from exc


def validate_url(url: str, field_name: str) -> str:
    cleaned = (url or "").strip()
    parsed = parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise APIError(HTTPStatus.BAD_REQUEST, f"{field_name} 不是有效的 URL", code="invalid_url")
    return cleaned


def sibling_endpoint_url(url: str, endpoint_name: str) -> str:
    parsed = parse.urlparse(url)
    endpoint = endpoint_name.strip("/")
    path = parsed.path.rstrip("/")
    if not path:
        new_path = f"/{endpoint}"
    elif path.endswith("/responses"):
        new_path = f"{path[: -len('/responses')]}/{endpoint}"
    else:
        new_path = f"{path}/{endpoint}"
    return parse.urlunparse(parsed._replace(path=new_path, params="", query="", fragment=""))


def optional_string(
    payload: dict[str, Any], name: str, allowed: set[str] | None = None
) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if allowed is not None and cleaned not in allowed:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            f"参数 {name} 不支持: {cleaned}",
            code="invalid_parameter",
        )
    return cleaned


def optional_int(payload: dict[str, Any], name: str, minimum: int, maximum: int) -> int | None:
    value = payload.get(name)
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            f"参数 {name} 必须是整数",
            code="invalid_parameter",
        ) from exc
    if parsed < minimum or parsed > maximum:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            f"参数 {name} 必须在 {minimum} 到 {maximum} 之间",
            code="invalid_parameter",
        )
    return parsed


def openai_image_options(payload: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    allowed_values: dict[str, set[str]] = {
        "quality": {"auto", "low", "medium", "high"},
        "background": {"auto", "opaque", "transparent"},
        "output_format": {"png", "jpeg", "webp"},
        "moderation": {"auto", "low"},
    }
    for name, allowed in allowed_values.items():
        value = optional_string(payload, name, allowed)
        if value is not None:
            options[name] = value

    output_compression = optional_int(payload, "output_compression", 0, 100)
    if output_compression is not None and options.get("output_format") in {"jpeg", "webp"}:
        options["output_compression"] = output_compression

    return options


def request_metadata(payload: dict[str, Any], *, size: str | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if size:
        metadata["size"] = size
        metadata["requested_size"] = size
    for key in _IMAGE_OPTION_KEYS:
        value = payload.get(key)
        if value is not None and value != "":
            metadata[key] = value
    return metadata


def _parse_exact_size(size: Any) -> tuple[int, int] | None:
    if not isinstance(size, str):
        return None
    match = re.fullmatch(r"\s*(\d{2,5})x(\d{2,5})\s*", size)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


# cover-fit 归一化只允许"接近等比"的偏差：超过这个比例说明上游换了画幅，
# 裁剪会切掉海报边缘的文字/装饰（实测出现过 1088x2240 请求返回 1024x1536，
# cover 裁剪要砍掉 27% 宽度），这种情况必须保留原图走尺寸不一致提示。
_NORMALIZE_MAX_ASPECT_DELTA = 0.03


def _normalize_strict_size_image(
    image_bytes: bytes,
    image_mime: str,
    save_context: dict[str, Any],
) -> tuple[bytes, str, dict[str, object]]:
    if not save_context.get("strict_size"):
        return image_bytes, image_mime, {}
    target_size = _parse_exact_size(save_context.get("requested_size") or save_context.get("size"))
    if target_size is None:
        return image_bytes, image_mime, {}
    source_size = detect_image_dimensions(image_bytes)
    if source_size is not None and source_size[1] > 0:
        source_ratio = source_size[0] / source_size[1]
        target_ratio = target_size[0] / target_size[1]
        if abs(source_ratio - target_ratio) / target_ratio > _NORMALIZE_MAX_ASPECT_DELTA:
            log_event(
                logger,
                logging.WARNING,
                "image_size_normalize_skipped_aspect",
                target_size=f"{target_size[0]}x{target_size[1]}",
                source_size=f"{source_size[0]}x{source_size[1]}",
            )
            return image_bytes, image_mime, {}
    try:
        return resize_image_to_exact_size(image_bytes, image_mime, target_size)
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "image_size_normalize_failed",
            target_size=f"{target_size[0]}x{target_size[1]}",
            image_mime=image_mime,
            error=type(exc).__name__,
        )
        return image_bytes, image_mime, {}


def compact_raw_response(payload: Any) -> Any:
    """Return a preview-safe copy of an upstream payload.

    The browser still gets first-class image fields and persisted file URLs from
    `prepare_image_payload`; `raw_response` is only a debug preview and should
    not duplicate megabytes of image base64.
    """

    if isinstance(payload, dict):
        compacted: dict[str, Any] = {}
        for key, value in payload.items():
            if key in _RAW_IMAGE_KEYS and isinstance(value, str):
                compacted[key] = f"[omitted {len(value)} chars]"
            elif key in _RAW_IMAGE_URL_KEYS and isinstance(value, str) and value.startswith("data:image/"):
                compacted[key] = f"[omitted data URL {len(value)} chars]"
            else:
                compacted[key] = compact_raw_response(value)
        return compacted
    if isinstance(payload, list):
        return [compact_raw_response(item) for item in payload]
    return payload


def ensure_json_object(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        details = (
            json.dumps(payload, ensure_ascii=False, indent=2)
            if isinstance(payload, (list, dict))
            else repr(payload)
        )
        raise APIError(
            HTTPStatus.BAD_GATEWAY,
            f"{context} 返回的 JSON 不是对象",
            details[:4000],
            code="upstream_error",
        )
    return payload


def extract_response_image_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    output = payload.get("output")
    if not isinstance(output, list):
        return []
    images: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "image_generation_call":
            continue
        result = item.get("result")
        if isinstance(result, str) and result:
            images.append(
                {
                    "b64_json": result,
                    "revised_prompt": item.get("revised_prompt"),
                }
            )
    return images


def extract_response_image_item(payload: dict[str, Any]) -> dict[str, Any]:
    return next(iter(extract_response_image_items(payload)), {})


def normalize_responses_image_payload(
    payload: dict[str, Any],
    *,
    fallback_b64: str | None = None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    items = extract_response_image_items(payload)
    if not items and fallback_b64:
        items = [{"b64_json": fallback_b64}]

    normalized: dict[str, Any] = {
        "data": items,
        "created": payload.get("created_at") or payload.get("created"),
        "response_id": payload.get("id"),
        "model": payload.get("model"),
        "status": payload.get("status"),
    }
    if events is not None:
        normalized["stream_events"] = events
    return normalized


def _image_item_payload(
    item: dict[str, Any],
    *,
    upstream: dict[str, Any],
    data_dir: Path,
    outputs_dir: Path,
    user_agent: str,
    save_context: dict[str, Any],
    fetch_remote: Any | None = None,
    image_transform: ImageTransform | None = None,
    index: int = 0,
) -> dict[str, Any]:
    base64_image = item.get("b64_json")
    image_data_url: str | None = None
    image_mime: str | None = None
    image_bytes: bytes | None = None
    image_url = item.get("url")

    if isinstance(base64_image, str) and base64_image:
        try:
            image_bytes = base64.b64decode(base64_image, validate=True)
            image_mime = detect_image_mime(image_bytes)
        except (ValueError, binascii.Error):
            image_bytes = None
            image_mime = None
        if image_mime == "application/octet-stream" or (
            image_bytes is not None and not is_decodable_image(image_bytes)
        ):
            image_bytes = None
            image_mime = None
        if image_bytes is not None and image_mime is not None:
            image_data_url = f"data:{image_mime};base64,{base64_image}"
        else:
            log_event(logger, logging.WARNING, "invalid_upstream_image_candidate", candidate_index=index)
    if image_bytes is None and isinstance(image_url, str) and image_url and fetch_remote is not None:
        image_bytes, image_mime = fetch_remote(image_url, user_agent)
        detected_mime = detect_image_mime(image_bytes)
        if detected_mime == "application/octet-stream" or not is_decodable_image(image_bytes):
            log_event(logger, logging.WARNING, "invalid_upstream_image_candidate", candidate_index=index)
            image_bytes = None
            image_mime = None
            image_url = None
        else:
            image_mime = detected_mime

    saved_payload: dict[str, Any] = {}
    if image_bytes and image_mime:
        image_bytes, image_mime, normalization_metadata = _normalize_strict_size_image(
            image_bytes,
            image_mime,
            save_context,
        )
        transform_metadata: dict[str, object] = {}
        if image_transform is not None:
            image_bytes, image_mime, transform_metadata = image_transform(
                image_bytes,
                image_mime,
                index,
            )
            image_data_url = (
                f"data:{image_mime};base64,"
                f"{base64.b64encode(image_bytes).decode('ascii')}"
            )
        saved_payload = save_output_image(
            data_dir=data_dir,
            outputs_dir=outputs_dir,
            mode=str(save_context.get("mode") or "result"),
            image_bytes=image_bytes,
            image_mime=image_mime,
            filename_prefix=str(save_context.get("filename_prefix") or ""),
            metadata={
                **save_context,
                "candidate_index": index,
                "created_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "upstream_created": upstream.get("created"),
                "upstream_image_url": image_url,
                "saved_image_mime": image_mime,
                **normalization_metadata,
                **transform_metadata,
            },
        )
        saved_payload.update(normalization_metadata)
        saved_payload.update(transform_metadata)

    # When the image is persisted, the browser loads it from the saved file URL
    # (same-origin), so we drop the multi-megabyte inline data URL to keep
    # responses small — especially with multiple candidates. The inline copy is
    # only kept as a fallback when persistence failed.
    inline_data_url = None if saved_payload.get("saved_image_url") else image_data_url

    return {
        # Original index within the upstream data list. DB records and the
        # browser payload are matched on this — positional matching breaks as
        # soon as one candidate is unsaveable and shifts the positions.
        "candidate_index": index,
        "image_data_url": inline_data_url,
        "image_url": image_url,
        "revised_prompt": item.get("revised_prompt"),
        **saved_payload,
    }


def prepare_image_payload(
    upstream: dict[str, Any],
    *,
    data_dir: Path,
    outputs_dir: Path,
    user_agent: str,
    save_context: dict[str, Any],
    fetch_remote: Any | None = None,
    image_transform: ImageTransform | None = None,
) -> dict[str, Any]:
    """Build the response payload sent back to the browser and persist the image.

    `fetch_remote` is an optional callable used for downloading an image referenced
    by URL. Tests may inject a stub here; in production it is wired to the async
    httpx-based downloader bridged via anyio.
    """

    data_items = upstream.get("data")
    candidate_items = [item for item in data_items if isinstance(item, dict)] if isinstance(data_items, list) else []
    requested_count = save_context.get("sample_count")
    candidate_limit = max(1, int(requested_count)) if requested_count is not None else None
    # Process candidates independently: a single sample that fails to download or
    # save must not discard the others. Only surface an error if every candidate
    # failed (otherwise the customer silently loses good images they asked for).
    images: list[dict[str, Any]] = []
    candidate_errors: list[Exception] = []
    for index, item in enumerate(candidate_items):
        try:
            payload = _image_item_payload(
                item,
                upstream=upstream,
                data_dir=data_dir,
                outputs_dir=outputs_dir,
                user_agent=user_agent,
                save_context=save_context,
                fetch_remote=fetch_remote,
                image_transform=image_transform,
                index=index,
            )
        except Exception as exc:
            candidate_errors.append(exc)
            continue
        # A data item with nothing renderable (no inline data, no URL, nothing
        # saved) is a placeholder, not a candidate: counting it would turn a
        # no-image upstream reply into a blank "success" and shift the ids of
        # the real images.
        if not (
            payload.get("image_data_url")
            or payload.get("image_url")
            or payload.get("saved_image_url")
        ):
            continue
        images.append(payload)
        if candidate_limit is not None and len(images) >= candidate_limit:
            if index + 1 < len(candidate_items):
                log_event(
                    logger,
                    logging.WARNING,
                    "upstream_candidate_count_capped",
                    requested_count=candidate_limit,
                    upstream_count=len(candidate_items),
                )
            break
    if not images and candidate_errors:
        raise candidate_errors[0]
    first_image = images[0] if images else {}

    return {
        "image_data_url": first_image.get("image_data_url"),
        "image_url": first_image.get("image_url"),
        "revised_prompt": first_image.get("revised_prompt"),
        "created": upstream.get("created"),
        "raw_response": compact_raw_response(upstream),
        "images": images,
        "candidate_count": len(images),
        **first_image,
    }

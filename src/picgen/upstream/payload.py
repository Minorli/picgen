from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib import parse

from ..errors import APIError
from ..storage import detect_image_mime, save_output_image

_IMAGE_OPTION_KEYS = ("quality", "background", "output_format", "output_compression", "moderation")


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
    for key in _IMAGE_OPTION_KEYS:
        value = payload.get(key)
        if value is not None and value != "":
            metadata[key] = value
    return metadata


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


def extract_response_image_item(payload: dict[str, Any]) -> dict[str, Any]:
    output = payload.get("output")
    if not isinstance(output, list):
        return {}
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "image_generation_call":
            continue
        result = item.get("result")
        if isinstance(result, str) and result:
            return {
                "b64_json": result,
                "revised_prompt": item.get("revised_prompt"),
            }
    return {}


def normalize_responses_image_payload(
    payload: dict[str, Any],
    *,
    fallback_b64: str | None = None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    first_item = extract_response_image_item(payload)
    if not first_item and fallback_b64:
        first_item = {"b64_json": fallback_b64}

    normalized: dict[str, Any] = {
        "data": [first_item] if first_item else [],
        "created": payload.get("created_at") or payload.get("created"),
        "response_id": payload.get("id"),
        "model": payload.get("model"),
        "status": payload.get("status"),
    }
    if events is not None:
        normalized["stream_events"] = events
    return normalized


def prepare_image_payload(
    upstream: dict[str, Any],
    *,
    data_dir: Path,
    outputs_dir: Path,
    user_agent: str,
    save_context: dict[str, Any],
    fetch_remote: Any | None = None,
) -> dict[str, Any]:
    """Build the response payload sent back to the browser and persist the image.

    `fetch_remote` is an optional callable used for downloading an image referenced
    by URL. Tests may inject a stub here; in production it is wired to the async
    httpx-based downloader bridged via anyio.
    """

    first_item: dict[str, Any] = {}
    data_items = upstream.get("data")
    if isinstance(data_items, list) and data_items:
        maybe_item = data_items[0]
        if isinstance(maybe_item, dict):
            first_item = maybe_item

    base64_image = first_item.get("b64_json")
    image_data_url: str | None = None
    image_mime: str | None = None
    image_bytes: bytes | None = None
    image_url = first_item.get("url")

    if isinstance(base64_image, str) and base64_image:
        try:
            image_bytes = base64.b64decode(base64_image, validate=True)
            image_mime = detect_image_mime(image_bytes)
        except (ValueError, binascii.Error):
            image_mime = "image/png"
        image_data_url = f"data:{image_mime};base64,{base64_image}"
    elif isinstance(image_url, str) and image_url and fetch_remote is not None:
        image_bytes, image_mime = fetch_remote(image_url, user_agent)

    saved_payload: dict[str, Any] = {}
    if image_bytes and image_mime:
        saved_payload = save_output_image(
            data_dir=data_dir,
            outputs_dir=outputs_dir,
            mode=str(save_context.get("mode") or "result"),
            image_bytes=image_bytes,
            image_mime=image_mime,
            metadata={
                **save_context,
                "created_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
                "upstream_created": upstream.get("created"),
                "upstream_image_url": image_url,
                "saved_image_mime": image_mime,
            },
        )

    return {
        "image_data_url": image_data_url,
        "image_url": image_url,
        "revised_prompt": first_item.get("revised_prompt"),
        "created": upstream.get("created"),
        "raw_response": upstream,
        **saved_payload,
    }

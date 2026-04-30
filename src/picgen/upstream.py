from __future__ import annotations

import base64
import binascii
import json
import sys
import time
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib import error, parse, request
from uuid import uuid4

from .errors import APIError
from .storage import detect_image_mime, save_output_image


def upstream_headers(user_agent: str, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


def debug_log(event: str, **fields: Any) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    field_text = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    print(f"[picgen] {timestamp} {event} {field_text}".rstrip(), file=sys.stderr, flush=True)


def decode_base64_blob(blob: str) -> bytes:
    data = blob.strip()
    if not data:
        raise APIError(HTTPStatus.BAD_REQUEST, "图片内容为空")
    if data.startswith("data:") and ";base64," in data:
        data = data.split(";base64,", 1)[1]
    try:
        return base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise APIError(HTTPStatus.BAD_REQUEST, "图片内容不是有效的 Base64 数据") from exc


def fetch_remote_image(image_url: str, user_agent: str) -> tuple[bytes, str]:
    req = request.Request(
        image_url,
        headers=upstream_headers(user_agent, {"Accept": "image/*"}),
        method="GET",
    )

    try:
        with request.urlopen(req, timeout=180) as response:
            image_bytes = response.read()
            response_mime = response.headers.get_content_type()
    except error.HTTPError as exc:
        raise APIError(HTTPStatus.BAD_GATEWAY, f"无法下载上游返回的图片: HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise APIError(HTTPStatus.BAD_GATEWAY, f"无法下载上游返回的图片: {exc.reason}") from exc

    if not image_bytes:
        raise APIError(HTTPStatus.BAD_GATEWAY, "上游返回了空图片")

    detected_mime = detect_image_mime(image_bytes)
    if response_mime and response_mime.startswith("image/"):
        return image_bytes, response_mime
    return image_bytes, detected_mime


def encode_multipart(fields: dict[str, Any], files: list[dict[str, Any]]) -> tuple[bytes, str]:
    boundary = f"----PicGenBoundary{uuid4().hex}"
    lines = bytearray()

    for name, value in fields.items():
        if value is None or value == "":
            continue
        lines.extend(f"--{boundary}\r\n".encode())
        lines.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        lines.extend(str(value).encode("utf-8"))
        lines.extend(b"\r\n")

    for file_part in files:
        lines.extend(f"--{boundary}\r\n".encode())
        disposition = (
            f'Content-Disposition: form-data; name="{file_part["field_name"]}"; '
            f'filename="{file_part["filename"]}"\r\n'
        )
        lines.extend(disposition.encode("utf-8"))
        lines.extend(f'Content-Type: {file_part["content_type"]}\r\n\r\n'.encode())
        lines.extend(file_part["data"])
        lines.extend(b"\r\n")

    lines.extend(f"--{boundary}--\r\n".encode())
    return bytes(lines), f"multipart/form-data; boundary={boundary}"


def validate_url(url: str, field_name: str) -> str:
    cleaned = url.strip()
    parsed = parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise APIError(HTTPStatus.BAD_REQUEST, f"{field_name} 不是有效的 URL")
    return cleaned


def optional_string(payload: dict[str, Any], name: str, allowed: set[str] | None = None) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if allowed is not None and cleaned not in allowed:
        raise APIError(HTTPStatus.BAD_REQUEST, f"参数 {name} 不支持: {cleaned}")
    return cleaned


def optional_int(payload: dict[str, Any], name: str, minimum: int, maximum: int) -> int | None:
    value = payload.get(name)
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise APIError(HTTPStatus.BAD_REQUEST, f"参数 {name} 必须是整数") from exc
    if parsed < minimum or parsed > maximum:
        raise APIError(HTTPStatus.BAD_REQUEST, f"参数 {name} 必须在 {minimum} 到 {maximum} 之间")
    return parsed


def openai_image_options(payload: dict[str, Any]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    allowed_values = {
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
    for key in ["quality", "background", "output_format", "output_compression", "moderation"]:
        value = payload.get(key)
        if value is not None and value != "":
            metadata[key] = value
    return metadata


def extract_error_message(response_body: str) -> tuple[str, str | None]:
    message = response_body.strip() or "上游接口返回了错误"
    details: str | None = None

    try:
        parsed_body = json.loads(response_body)
    except json.JSONDecodeError:
        return message, response_body.strip() or None

    if isinstance(parsed_body, dict):
        if parsed_body.get("cloudflare_error") is True and parsed_body.get("error_code") == 1010:
            message = "上游接口被 Cloudflare 拒绝访问: Error 1010"
            detail_text = str(
                parsed_body.get("detail") or "The site owner has blocked access based on your browser's signature."
            )
            ray_id = str(parsed_body.get("ray_id") or parsed_body.get("instance") or "").strip()
            zone = str(parsed_body.get("zone") or "").strip()
            owner_hint = str(parsed_body.get("what_you_should_do") or "").replace("**", "").strip()
            detail_lines = [
                detail_text,
                "这通常不是提示词、API Key 或本地页面的问题，而是上游站点的 Cloudflare 规则拦截了当前代理请求签名。",
            ]
            if owner_hint:
                detail_lines.append(owner_hint)
            if zone or ray_id:
                detail_lines.append(f"Zone: {zone or '-'}; Ray ID: {ray_id or '-'}")
            details = "\n".join(detail_lines)
            return message, details

        error_block = parsed_body.get("error")
        if isinstance(error_block, dict):
            message = str(error_block.get("message") or message)
            details = json.dumps(error_block, ensure_ascii=False, indent=2)
        else:
            details = json.dumps(parsed_body, ensure_ascii=False, indent=2)
    else:
        details = json.dumps(parsed_body, ensure_ascii=False, indent=2)

    return message, details


def ensure_json_object(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        details = (
            json.dumps(payload, ensure_ascii=False, indent=2)
            if isinstance(payload, (list, dict))
            else repr(payload)
        )
        raise APIError(HTTPStatus.BAD_GATEWAY, f"{context} 返回的 JSON 不是对象", details[:4000])
    return payload


def prepare_image_payload(
    upstream: dict[str, Any],
    *,
    data_dir: Path,
    outputs_dir: Path,
    user_agent: str,
    save_context: dict[str, Any],
) -> dict[str, Any]:
    first_item: dict[str, Any] = {}
    data_items = upstream.get("data")
    if isinstance(data_items, list) and data_items:
        maybe_item = data_items[0]
        if isinstance(maybe_item, dict):
            first_item = maybe_item

    base64_image = first_item.get("b64_json")
    image_data_url: str | None = None
    image_mime = None
    image_bytes: bytes | None = None
    image_url = first_item.get("url")

    if isinstance(base64_image, str) and base64_image:
        try:
            image_bytes = base64.b64decode(base64_image, validate=True)
            image_mime = detect_image_mime(image_bytes)
        except (ValueError, binascii.Error):
            image_mime = "image/png"
        image_data_url = f"data:{image_mime};base64,{base64_image}"
    elif isinstance(image_url, str) and image_url:
        image_bytes, image_mime = fetch_remote_image(image_url, user_agent)

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
                "created_at": datetime.now().isoformat(timespec="seconds"),
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


def run_upstream_json(url: str, api_key: str, payload: dict[str, Any], user_agent: str) -> dict[str, Any]:
    request_body = json.dumps(payload).encode("utf-8")
    started_at = time.perf_counter()
    debug_log(
        "upstream_json_start",
        url=url,
        model=payload.get("model"),
        size=payload.get("size"),
        prompt_chars=len(str(payload.get("prompt") or "")),
        body_bytes=len(request_body),
    )
    req = request.Request(
        url,
        data=request_body,
        headers=upstream_headers(
            user_agent,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        ),
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=180) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        debug_log(
            "upstream_json_http_error",
            url=url,
            status=exc.code,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            body_chars=len(body),
        )
        message, details = extract_error_message(body)
        raise APIError(exc.code, message, details) from exc
    except error.URLError as exc:
        debug_log(
            "upstream_json_url_error",
            url=url,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            reason=exc.reason,
        )
        raise APIError(HTTPStatus.BAD_GATEWAY, f"无法连接上游接口: {exc.reason}") from exc

    debug_log(
        "upstream_json_ok",
        url=url,
        elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
        body_chars=len(body),
    )

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise APIError(HTTPStatus.BAD_GATEWAY, "上游接口返回了无法解析的 JSON", body) from exc
    return ensure_json_object(parsed, "生成接口")


def run_upstream_multipart(
    url: str,
    api_key: str,
    fields: dict[str, Any],
    files: list[dict[str, Any]],
    user_agent: str,
) -> dict[str, Any]:
    body, content_type = encode_multipart(fields, files)
    started_at = time.perf_counter()
    debug_log(
        "upstream_multipart_start",
        url=url,
        model=fields.get("model"),
        prompt_chars=len(str(fields.get("prompt") or "")),
        files=",".join(str(file_part.get("filename")) for file_part in files),
        body_bytes=len(body),
    )
    req = request.Request(
        url,
        data=body,
        headers=upstream_headers(
            user_agent,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": content_type,
                "Accept": "application/json",
            },
        ),
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=180) as response:
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        debug_log(
            "upstream_multipart_http_error",
            url=url,
            status=exc.code,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            body_chars=len(body_text),
        )
        message, details = extract_error_message(body_text)
        raise APIError(exc.code, message, details) from exc
    except error.URLError as exc:
        debug_log(
            "upstream_multipart_url_error",
            url=url,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            reason=exc.reason,
        )
        raise APIError(HTTPStatus.BAD_GATEWAY, f"无法连接上游接口: {exc.reason}") from exc

    debug_log(
        "upstream_multipart_ok",
        url=url,
        elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
        body_chars=len(response_body),
    )

    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise APIError(HTTPStatus.BAD_GATEWAY, "上游接口返回了无法解析的 JSON", response_body) from exc
    return ensure_json_object(parsed, "编辑接口")

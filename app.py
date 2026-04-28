from __future__ import annotations

import argparse
import base64
import binascii
import json
import mimetypes
import os
import sys
import time
import traceback
import uuid
from datetime import datetime
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error, parse, request


ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"
DATA_DIR = ROOT_DIR / "data"
OUTPUTS_DIR = DATA_DIR / "outputs"


@dataclass(frozen=True)
class DefaultConfig:
    generate_url: str
    edit_url: str
    model: str
    size: str
    api_key: str


DEFAULT_CONFIG = DefaultConfig(
    generate_url=os.environ.get("PICGEN_DEFAULT_GENERATE_URL", "").strip(),
    edit_url=os.environ.get("PICGEN_DEFAULT_EDIT_URL", "https://sub.tidba.com/v1/images/edits").strip(),
    model=os.environ.get("PICGEN_DEFAULT_MODEL", "gpt-image-2").strip() or "gpt-image-2",
    size=os.environ.get("PICGEN_DEFAULT_SIZE", "1024x1024").strip() or "1024x1024",
    api_key=os.environ.get("PICGEN_DEFAULT_API_KEY", "").strip(),
)

UPSTREAM_USER_AGENT = (
    os.environ.get("PICGEN_UPSTREAM_USER_AGENT", "").strip()
    or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def upstream_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": UPSTREAM_USER_AGENT,
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


class APIError(Exception):
    def __init__(self, status: int, message: str, details: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


def extension_for_mime(image_mime: str) -> str:
    normalized = image_mime.lower().split(";", 1)[0].strip()
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    return mapping.get(normalized, ".png")


def sanitize_filename(name: str) -> str:
    cleaned = "".join(char for char in name if char not in {'"', "\r", "\n", "\\"}).strip()
    return cleaned or "image.png"


def detect_image_mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def detect_image_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
        return int.from_bytes(image_bytes[16:20], "big"), int.from_bytes(image_bytes[20:24], "big")

    if image_bytes.startswith((b"GIF87a", b"GIF89a")) and len(image_bytes) >= 10:
        return int.from_bytes(image_bytes[6:8], "little"), int.from_bytes(image_bytes[8:10], "little")

    if image_bytes.startswith(b"\xff\xd8"):
        index = 2
        sof_markers = {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }
        while index + 9 < len(image_bytes):
            if image_bytes[index] != 0xFF:
                index += 1
                continue
            marker = image_bytes[index + 1]
            index += 2
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if index + 2 > len(image_bytes):
                break
            segment_length = int.from_bytes(image_bytes[index:index + 2], "big")
            if segment_length < 2 or index + segment_length > len(image_bytes):
                break
            if marker in sof_markers and segment_length >= 7:
                height = int.from_bytes(image_bytes[index + 3:index + 5], "big")
                width = int.from_bytes(image_bytes[index + 5:index + 7], "big")
                return width, height
            index += segment_length

    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP" and len(image_bytes) >= 30:
        chunk_type = image_bytes[12:16]
        if chunk_type == b"VP8X" and len(image_bytes) >= 30:
            width = int.from_bytes(image_bytes[24:27], "little") + 1
            height = int.from_bytes(image_bytes[27:30], "little") + 1
            return width, height

    return None


def storage_url_for_path(file_path: Path) -> str:
    return f"/files/{file_path.relative_to(DATA_DIR).as_posix()}"


def fetch_remote_image(image_url: str) -> tuple[bytes, str]:
    req = request.Request(
        image_url,
        headers=upstream_headers({
            "Accept": "image/*",
        }),
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


def save_output_image(
    *,
    mode: str,
    image_bytes: bytes,
    image_mime: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    day_dir = OUTPUTS_DIR / datetime.now().strftime("%Y%m%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{mode}-{datetime.now().strftime('%H%M%S')}-{uuid.uuid4().hex[:8]}"
    image_path = day_dir / f"{stem}{extension_for_mime(image_mime)}"
    metadata_path = day_dir / f"{stem}.json"
    image_dimensions = detect_image_dimensions(image_bytes)

    image_path.write_bytes(image_bytes)
    metadata_path.write_text(
        json.dumps(
            {
                **metadata,
                "saved_image_width": image_dimensions[0] if image_dimensions else None,
                "saved_image_height": image_dimensions[1] if image_dimensions else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "saved_image_path": str(image_path),
        "saved_image_url": storage_url_for_path(image_path),
        "saved_image_name": image_path.name,
        "saved_image_mime": image_mime,
        "saved_image_width": image_dimensions[0] if image_dimensions else None,
        "saved_image_height": image_dimensions[1] if image_dimensions else None,
        "saved_metadata_path": str(metadata_path),
        "saved_metadata_url": storage_url_for_path(metadata_path),
    }


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


def encode_multipart(fields: dict[str, Any], files: list[dict[str, Any]]) -> tuple[bytes, str]:
    boundary = f"----PicGenBoundary{uuid.uuid4().hex}"
    lines = bytearray()

    for name, value in fields.items():
        if value is None or value == "":
            continue
        lines.extend(f"--{boundary}\r\n".encode("utf-8"))
        lines.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        lines.extend(str(value).encode("utf-8"))
        lines.extend(b"\r\n")

    for file_part in files:
        lines.extend(f"--{boundary}\r\n".encode("utf-8"))
        disposition = (
            f'Content-Disposition: form-data; name="{file_part["field_name"]}"; '
            f'filename="{file_part["filename"]}"\r\n'
        )
        lines.extend(disposition.encode("utf-8"))
        lines.extend(f'Content-Type: {file_part["content_type"]}\r\n\r\n'.encode("utf-8"))
        lines.extend(file_part["data"])
        lines.extend(b"\r\n")

    lines.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return bytes(lines), f"multipart/form-data; boundary={boundary}"


def validate_url(url: str, field_name: str) -> str:
    cleaned = url.strip()
    parsed = parse.urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise APIError(HTTPStatus.BAD_REQUEST, f"{field_name} 不是有效的 URL")
    return cleaned


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
            detail_text = str(parsed_body.get("detail") or "The site owner has blocked access based on your browser's signature.")
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
        details = json.dumps(payload, ensure_ascii=False, indent=2) if isinstance(payload, (list, dict)) else repr(payload)
        raise APIError(HTTPStatus.BAD_GATEWAY, f"{context} 返回的 JSON 不是对象", details[:4000])
    return payload


def prepare_image_payload(upstream: dict[str, Any], *, save_context: dict[str, Any]) -> dict[str, Any]:
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
        image_bytes, image_mime = fetch_remote_image(image_url)

    saved_payload: dict[str, Any] = {}
    if image_bytes and image_mime:
        saved_payload = save_output_image(
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


def run_upstream_json(url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
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
        headers=upstream_headers({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }),
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


def run_upstream_multipart(url: str, api_key: str, fields: dict[str, Any], files: list[dict[str, Any]]) -> dict[str, Any]:
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
        headers=upstream_headers({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "Accept": "application/json",
        }),
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


class PicGenHandler(SimpleHTTPRequestHandler):
    server_version = "PicGen/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        try:
            if path.startswith("/files/"):
                self.serve_storage_file(path.removeprefix("/files/"))
                return

            if path == "/api/config":
                self.write_json(
                    HTTPStatus.OK,
                    {
                        "generate_url": DEFAULT_CONFIG.generate_url,
                        "edit_url": DEFAULT_CONFIG.edit_url,
                        "default_model": DEFAULT_CONFIG.model,
                        "default_size": DEFAULT_CONFIG.size,
                        "has_default_api_key": bool(DEFAULT_CONFIG.api_key),
                        "storage_dir": str(OUTPUTS_DIR),
                    },
                )
                return

            if path == "/api/health":
                self.write_json(HTTPStatus.OK, {"ok": True})
                return

            super().do_GET()
        except APIError as exc:
            self.write_json(
                exc.status,
                {
                    "error": exc.message,
                    "details": exc.details,
                },
            )

    def serve_storage_file(self, relative_path: str) -> None:
        decoded_path = parse.unquote(relative_path).lstrip("/")
        target_path = (DATA_DIR / decoded_path).resolve()
        data_root = DATA_DIR.resolve()

        try:
            target_path.relative_to(data_root)
        except ValueError as exc:
            raise APIError(HTTPStatus.FORBIDDEN, "非法文件路径") from exc

        if not target_path.is_file():
            raise APIError(HTTPStatus.NOT_FOUND, "文件不存在")

        content_type = mimetypes.guess_type(target_path.name)[0] or "application/octet-stream"
        file_bytes = target_path.read_bytes()

        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(file_bytes)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(file_bytes)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        request_id = uuid.uuid4().hex[:8]
        started_at = time.perf_counter()
        debug_log("local_post_start", request_id=request_id, path=path)
        try:
            payload = self.read_json_body()
            debug_log(
                "local_post_payload",
                request_id=request_id,
                path=path,
                keys=",".join(sorted(payload.keys())),
            )
            if path == "/api/generate":
                response_payload = self.handle_generate(payload)
            elif path == "/api/edit":
                response_payload = self.handle_edit(payload)
            else:
                raise APIError(HTTPStatus.NOT_FOUND, "未知接口")
            debug_log(
                "local_post_ok",
                request_id=request_id,
                path=path,
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            )
            self.write_json(HTTPStatus.OK, response_payload)
        except APIError as exc:
            debug_log(
                "local_post_api_error",
                request_id=request_id,
                path=path,
                status=exc.status,
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                message=exc.message,
            )
            self.write_json(
                exc.status,
                {
                    "error": exc.message,
                    "details": exc.details,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            traceback.print_exc()
            debug_log(
                "local_post_internal_error",
                request_id=request_id,
                path=path,
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                message=exc,
            )
            self.write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "服务内部错误",
                    "details": str(exc),
                },
            )

    def read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0").strip()
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "无效的 Content-Length") from exc

        if content_length <= 0:
            raise APIError(HTTPStatus.BAD_REQUEST, "请求体为空")

        raw_body = self.rfile.read(content_length)
        try:
            parsed_body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "请求体不是有效的 JSON") from exc

        if not isinstance(parsed_body, dict):
            raise APIError(HTTPStatus.BAD_REQUEST, "请求体必须是 JSON 对象")
        return parsed_body

    def handle_generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("prompt", ""))
        if not prompt.strip():
            raise APIError(HTTPStatus.BAD_REQUEST, "生成提示词不能为空")

        endpoint_url = validate_url(
            str(payload.get("endpoint_url") or DEFAULT_CONFIG.generate_url),
            "生成接口 URL",
        )
        model = str(payload.get("model") or DEFAULT_CONFIG.model).strip() or DEFAULT_CONFIG.model
        size = str(payload.get("size") or DEFAULT_CONFIG.size).strip() or DEFAULT_CONFIG.size
        api_key = str(payload.get("api_key") or DEFAULT_CONFIG.api_key).strip()
        try:
            n = int(payload.get("n") or 1)
        except (TypeError, ValueError) as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "参数 n 必须是整数") from exc

        if not api_key:
            raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key")

        upstream_payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n,
        }
        upstream_response = run_upstream_json(endpoint_url, api_key, upstream_payload)

        return {
            "mode": "generate",
            "prompt": prompt,
            "model": model,
            "size": size,
            "endpoint_url": endpoint_url,
            **prepare_image_payload(
                upstream_response,
                save_context={
                    "mode": "generate",
                    "prompt": prompt,
                    "model": model,
                    "size": size,
                    "endpoint_url": endpoint_url,
                },
            ),
        }

    def handle_edit(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("prompt", ""))
        if not prompt.strip():
            raise APIError(HTTPStatus.BAD_REQUEST, "编辑指令不能为空")

        endpoint_url = validate_url(
            str(payload.get("endpoint_url") or DEFAULT_CONFIG.edit_url),
            "编辑接口 URL",
        )
        model = str(payload.get("model") or DEFAULT_CONFIG.model).strip() or DEFAULT_CONFIG.model
        api_key = str(payload.get("api_key") or DEFAULT_CONFIG.api_key).strip()

        if not api_key:
            raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key")

        image_part = parse_file_payload(payload.get("image"), "image", required=True)
        mask_part = parse_file_payload(payload.get("mask"), "mask", required=False)

        files = [part for part in [image_part, mask_part] if part is not None]
        size = str(payload.get("size") or "").strip()
        upstream_response = run_upstream_multipart(
            endpoint_url,
            api_key,
            fields={
                "model": model,
                "prompt": prompt,
                "size": size,
            },
            files=files,
        )

        return {
            "mode": "edit",
            "prompt": prompt,
            "model": model,
            "size": size or None,
            "endpoint_url": endpoint_url,
            "source_image_name": image_part["filename"],
            "mask_image_name": mask_part["filename"] if mask_part else None,
            **prepare_image_payload(
                upstream_response,
                save_context={
                    "mode": "edit",
                    "prompt": prompt,
                    "model": model,
                    "size": size or None,
                    "endpoint_url": endpoint_url,
                    "source_image_name": image_part["filename"],
                    "mask_image_name": mask_part["filename"] if mask_part else None,
                },
            ),
        }

    def write_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local UI for upstream image generation and editing APIs.")
    parser.add_argument("--host", default=os.environ.get("PICGEN_HOST", "127.0.0.1"), help="Bind host")
    parser.add_argument(
        "--port",
        default=int(os.environ.get("PICGEN_PORT", "8000")),
        type=int,
        help="Bind port",
    )
    return parser.parse_args()


def main() -> int:
    if not STATIC_DIR.exists():
        print(f"Static directory not found: {STATIC_DIR}", file=sys.stderr)
        return 1

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), PicGenHandler)
    print(f"PicGen server running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

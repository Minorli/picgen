from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from ..storage import extension_for_mime


def upstream_headers(user_agent: str, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    if extra_headers:
        headers.update(extra_headers)
    return headers


def ascii_multipart_filename(filename: str, content_type: str) -> str:
    raw_name = Path(filename or "").name
    raw_path = Path(raw_name)
    safe_stem = "".join(
        char if char.isascii() and (char.isalnum() or char in {"-", "_"}) else "-"
        for char in raw_path.stem
    ).strip("-_")
    safe_stem = (safe_stem or "image")[:72]
    safe_ext = "".join(
        char for char in raw_path.suffix.lower()
        if char.isascii() and (char.isalnum() or char == ".")
    )
    if not safe_ext.startswith(".") or len(safe_ext) < 2 or len(safe_ext) > 12:
        safe_ext = extension_for_mime(content_type)
    return f"{safe_stem}{safe_ext}"


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
        filename = ascii_multipart_filename(
            str(file_part["filename"]),
            str(file_part.get("content_type") or "application/octet-stream"),
        )
        disposition = (
            f'Content-Disposition: form-data; name="{file_part["field_name"]}"; '
            f'filename="{filename}"\r\n'
        )
        lines.extend(disposition.encode("utf-8"))
        lines.extend(f'Content-Type: {file_part["content_type"]}\r\n\r\n'.encode())
        lines.extend(file_part["data"])
        lines.extend(b"\r\n")

    lines.extend(f"--{boundary}--\r\n".encode())
    return bytes(lines), f"multipart/form-data; boundary={boundary}"

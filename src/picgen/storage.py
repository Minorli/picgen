from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from urllib import parse

from .errors import APIError
from .logging_config import get_logger, log_event

logger = get_logger("picgen.storage")


_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/octet-stream": ".bin",
}


def extension_for_mime(image_mime: str) -> str:
    normalized = image_mime.lower().split(";", 1)[0].strip()
    extension = _MIME_TO_EXT.get(normalized)
    if extension is None:
        log_event(logger, logging.WARNING, "unknown_image_mime", mime=image_mime)
        return ".bin"
    return extension


_FORBIDDEN_FILENAME_CHARS = frozenset({'"', "\r", "\n", "\\", "/", "\x00"})


def sanitize_filename(name: str) -> str:
    cleaned = "".join(char for char in name if char not in _FORBIDDEN_FILENAME_CHARS).strip()
    cleaned = cleaned.replace("..", "")
    cleaned = cleaned.replace(":", "-")
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
    log_event(logger, logging.WARNING, "unknown_image_signature", bytes=len(image_bytes))
    return "application/octet-stream"


def detect_image_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
        return int.from_bytes(image_bytes[16:20], "big"), int.from_bytes(image_bytes[20:24], "big")

    if image_bytes.startswith((b"GIF87a", b"GIF89a")) and len(image_bytes) >= 10:
        return int.from_bytes(image_bytes[6:8], "little"), int.from_bytes(image_bytes[8:10], "little")

    if image_bytes.startswith(b"\xff\xd8"):
        index = 2
        sof_markers = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
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


def storage_url_for_path(data_dir: Path, file_path: Path) -> str:
    return f"/files/{file_path.relative_to(data_dir).as_posix()}"


def resolve_storage_path(data_dir: Path, relative_path: str) -> Path:
    decoded_path = parse.unquote(relative_path).lstrip("/")
    # Disallow absolute paths or parent-only references early.
    if Path(decoded_path).is_absolute():
        raise APIError(HTTPStatus.FORBIDDEN, "非法文件路径", code="forbidden")
    target_path = (data_dir / decoded_path).resolve()
    data_root = data_dir.resolve()
    try:
        target_path.relative_to(data_root)
    except ValueError as exc:
        raise APIError(HTTPStatus.FORBIDDEN, "非法文件路径", code="forbidden") from exc
    return target_path


def _atomic_write_bytes(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=target.suffix, dir=str(target.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        tmp_path.replace(target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _atomic_write_text(target: Path, payload: str) -> None:
    _atomic_write_bytes(target, payload.encode("utf-8"))


def save_output_image(
    *,
    data_dir: Path,
    outputs_dir: Path,
    mode: str,
    image_bytes: bytes,
    image_mime: str,
    metadata: dict[str, object],
) -> dict[str, object]:
    now = datetime.now()
    day_dir = outputs_dir / now.strftime("%Y%m%d")
    stem = f"{mode}-{now.strftime('%H%M%S')}-{uuid.uuid4().hex[:8]}"
    image_path = day_dir / f"{stem}{extension_for_mime(image_mime)}"
    metadata_path = day_dir / f"{stem}.json"
    image_dimensions = detect_image_dimensions(image_bytes)

    _atomic_write_bytes(image_path, image_bytes)
    _atomic_write_text(
        metadata_path,
        json.dumps(
            {
                **metadata,
                "saved_image_width": image_dimensions[0] if image_dimensions else None,
                "saved_image_height": image_dimensions[1] if image_dimensions else None,
                "saved_image_bytes": len(image_bytes),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )

    log_event(
        logger,
        logging.INFO,
        "storage_saved",
        mode=mode,
        path=str(image_path),
        bytes=len(image_bytes),
        width=image_dimensions[0] if image_dimensions else None,
        height=image_dimensions[1] if image_dimensions else None,
    )

    return {
        "saved_image_path": str(image_path),
        "saved_image_url": storage_url_for_path(data_dir, image_path),
        "saved_image_name": image_path.name,
        "saved_image_mime": image_mime,
        "saved_image_width": image_dimensions[0] if image_dimensions else None,
        "saved_image_height": image_dimensions[1] if image_dimensions else None,
        "saved_metadata_path": str(metadata_path),
        "saved_metadata_url": storage_url_for_path(data_dir, metadata_path),
    }


def prune_old_outputs(outputs_dir: Path, retention_days: int) -> int:
    """Delete day-folders older than retention_days. Returns count removed."""

    if retention_days <= 0 or not outputs_dir.exists():
        return 0
    cutoff = datetime.now(tz=UTC) - timedelta(days=retention_days)
    removed = 0
    for entry in outputs_dir.iterdir():
        if not entry.is_dir():
            continue
        try:
            day = datetime.strptime(entry.name, "%Y%m%d").replace(tzinfo=UTC)
        except ValueError:
            continue
        if day < cutoff:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
            log_event(logger, logging.INFO, "storage_pruned", folder=str(entry))
    return removed

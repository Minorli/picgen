from __future__ import annotations

import hashlib
import logging
import os
import shutil
import stat
import tempfile
import uuid
import warnings
from datetime import datetime, timedelta
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from urllib import parse

from PIL import Image, ImageOps

from .errors import APIError
from .logging_config import get_logger, log_event

logger = get_logger("picgen.storage")


_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "application/octet-stream": ".bin",
}
_MIME_TO_PIL_FORMAT: dict[str, str] = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/webp": "WEBP",
}
MAX_EXACT_IMAGE_PIXELS = 8_294_400


def extension_for_mime(image_mime: str) -> str:
    normalized = image_mime.lower().split(";", 1)[0].strip()
    extension = _MIME_TO_EXT.get(normalized)
    if extension is None:
        log_event(logger, logging.WARNING, "unknown_image_mime", mime=image_mime)
        return ".bin"
    return extension


# ? # % 会破坏 saved_image_url：浏览器把 ? / # 当查询串和锚点截断 URL，
# % 在 resolve_storage_path 的二次解码里被再解一次。
_FORBIDDEN_FILENAME_CHARS = frozenset({'"', "\r", "\n", "\\", "/", "\x00", "?", "#", "%"})


def _sanitize_filename_core(name: str) -> str:
    cleaned = "".join(char for char in name if char not in _FORBIDDEN_FILENAME_CHARS).strip()
    cleaned = "-".join(cleaned.split())
    cleaned = cleaned.replace("..", "")
    cleaned = cleaned.replace(":", "-")
    return cleaned


def sanitize_filename(name: str) -> str:
    return _sanitize_filename_core(name) or "image.png"


def sanitize_filename_prefix(value: str) -> str:
    # An empty prefix must stay empty, and a junk-only prefix ("..", "??")
    # must not inherit sanitize_filename's "image.png" fallback — both would
    # otherwise become a literal output folder name shared across users.
    if not value.strip():
        return ""
    cleaned = _sanitize_filename_core(value).strip(".-_")
    return cleaned[:48].strip(".-_") or ""


def output_group_dir(outputs_dir: Path, now: datetime, filename_prefix: str = "") -> Path:
    day_dir = outputs_dir / now.strftime("%Y%m%d")
    safe_prefix = sanitize_filename_prefix(filename_prefix)
    if safe_prefix:
        return day_dir / safe_prefix
    return day_dir


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
            # JPEG permits any number of 0xFF fill bytes before a marker.
            # Treating the second 0xFF as the marker desynchronizes the parser.
            while index < len(image_bytes) and image_bytes[index] == 0xFF:
                index += 1
            if index >= len(image_bytes):
                break
            marker = image_bytes[index]
            index += 1
            if marker == 0x00:
                continue
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if index + 2 > len(image_bytes):
                break
            segment_length = int.from_bytes(image_bytes[index : index + 2], "big")
            if segment_length < 2 or index + segment_length > len(image_bytes):
                break
            if marker in sof_markers and segment_length >= 7:
                height = int.from_bytes(image_bytes[index + 3 : index + 5], "big")
                width = int.from_bytes(image_bytes[index + 5 : index + 7], "big")
                return _jpeg_display_dimensions(image_bytes, (width, height))
            index += segment_length

    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP" and len(image_bytes) >= 16:
        chunk_type = image_bytes[12:16]
        if chunk_type == b"VP8X" and len(image_bytes) >= 30:
            width = int.from_bytes(image_bytes[24:27], "little") + 1
            height = int.from_bytes(image_bytes[27:30], "little") + 1
            return width, height
        if chunk_type == b"VP8 " and len(image_bytes) >= 30 and image_bytes[23:26] == b"\x9d\x01\x2a":
            # Lossy keyframe: 3-byte frame tag, the 0x9d012a start code, then the
            # 14-bit width and height (little-endian).
            width = int.from_bytes(image_bytes[26:28], "little") & 0x3FFF
            height = int.from_bytes(image_bytes[28:30], "little") & 0x3FFF
            return width, height
        if chunk_type == b"VP8L" and len(image_bytes) >= 25 and image_bytes[20] == 0x2F:
            # Lossless: 0x2f signature, then 14-bit (width-1) and (height-1).
            bits = int.from_bytes(image_bytes[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return width, height

    return None


def is_decodable_image(image_bytes: bytes) -> bool:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as source:
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > MAX_EXACT_IMAGE_PIXELS:
                    return False
                if source.format not in {"PNG", "JPEG", "WEBP", "GIF"}:
                    return False
                source.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, TypeError, ValueError):
        return False
    return True


def _jpeg_display_dimensions(image_bytes: bytes, dimensions: tuple[int, int]) -> tuple[int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image_bytes)) as source:
                orientation = int(source.getexif().get(274, 1))
    except (Image.DecompressionBombError, OSError, TypeError, ValueError):
        return dimensions
    if orientation in {5, 6, 7, 8}:
        return dimensions[1], dimensions[0]
    return dimensions


def resize_image_to_exact_size(
    image_bytes: bytes,
    image_mime: str,
    target_size: tuple[int, int],
) -> tuple[bytes, str, dict[str, object]]:
    """Resize/crop an image to an exact canvas using a high-quality cover fit."""

    target_width, target_height = target_size
    if target_width <= 0 or target_height <= 0:
        raise ValueError("target_size must contain positive dimensions")

    source_dimensions = detect_image_dimensions(image_bytes)
    if (
        source_dimensions is not None
        and source_dimensions[0] * source_dimensions[1] > MAX_EXACT_IMAGE_PIXELS
    ):
        raise ValueError(f"source image exceeds {MAX_EXACT_IMAGE_PIXELS} pixels")
    if source_dimensions == target_size:
        return image_bytes, image_mime, {}

    normalized_mime = image_mime.lower().split(";", 1)[0].strip()
    output_format = _MIME_TO_PIL_FORMAT.get(normalized_mime)
    if output_format is None:
        raise ValueError(f"unsupported image mime for resizing: {image_mime}")

    with Image.open(BytesIO(image_bytes)) as source:
        decoded_width, decoded_height = source.size
        if decoded_width * decoded_height > MAX_EXACT_IMAGE_PIXELS:
            raise ValueError(f"source image exceeds {MAX_EXACT_IMAGE_PIXELS} pixels")
        image = ImageOps.exif_transpose(source)
        if source_dimensions is None:
            source_dimensions = image.size
        fitted = ImageOps.fit(
            image,
            (target_width, target_height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )

        if output_format == "JPEG" or fitted.mode == "CMYK":
            fitted = fitted.convert("RGB")

        output = BytesIO()
        if output_format == "PNG":
            fitted.save(output, format=output_format, compress_level=6)
        elif output_format == "JPEG":
            fitted.save(output, format=output_format, quality=95, optimize=True)
        elif output_format == "WEBP":
            fitted.save(output, format=output_format, quality=95)
        else:
            fitted.save(output, format=output_format)

    upstream_actual_size = f"{source_dimensions[0]}x{source_dimensions[1]}"
    return (
        output.getvalue(),
        normalized_mime,
        {
            "image_size_normalized": True,
            "image_size_normalized_method": "cover_lanczos",
            "upstream_actual_size": upstream_actual_size,
            "upstream_image_width": source_dimensions[0],
            "upstream_image_height": source_dimensions[1],
        },
    )


def composite_masked_edit_image(
    *,
    source_image_bytes: bytes,
    mask_image_bytes: bytes,
    generated_image_bytes: bytes,
    generated_image_mime: str,
) -> tuple[bytes, str, dict[str, object]]:
    """Keep source pixels wherever the OpenAI-style mask is opaque."""

    normalized_mime = generated_image_mime.lower().split(";", 1)[0].strip()
    output_format = _MIME_TO_PIL_FORMAT.get(normalized_mime)
    if output_format is None:
        raise ValueError(f"unsupported image mime for masked edit: {generated_image_mime}")

    with (
        Image.open(BytesIO(source_image_bytes)) as source_file,
        Image.open(BytesIO(mask_image_bytes)) as mask_file,
        Image.open(BytesIO(generated_image_bytes)) as generated_file,
    ):
        source = ImageOps.exif_transpose(source_file).convert("RGBA")
        mask = ImageOps.exif_transpose(mask_file)
        generated = ImageOps.exif_transpose(generated_file).convert("RGBA")
        if source.width * source.height > MAX_EXACT_IMAGE_PIXELS:
            raise ValueError(f"source image exceeds {MAX_EXACT_IMAGE_PIXELS} pixels")
        if mask.size != source.size:
            raise ValueError("mask dimensions must match source image dimensions")
        if "A" not in mask.getbands():
            raise ValueError("mask image must contain an alpha channel")
        if generated.size != source.size:
            generated = ImageOps.fit(
                generated,
                source.size,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )

        edit_alpha = ImageOps.invert(mask.getchannel("A"))
        composed = Image.composite(generated, source, edit_alpha)
        if output_format == "JPEG":
            composed = composed.convert("RGB")

        output = BytesIO()
        if output_format == "PNG":
            composed.save(output, format=output_format, compress_level=6)
        elif output_format == "JPEG":
            composed.save(output, format=output_format, quality=95, optimize=True)
        elif output_format == "WEBP":
            composed.save(output, format=output_format, quality=95)
        else:  # pragma: no cover - guarded by _MIME_TO_PIL_FORMAT
            composed.save(output, format=output_format)

    return (
        output.getvalue(),
        normalized_mime,
        {
            "mask_composited": True,
            "mask_preserve_mode": "inverse_alpha",
            "mask_source_size": f"{source.width}x{source.height}",
        },
    )


def storage_url_for_path(data_dir: Path, file_path: Path) -> str:
    # Relative URL (no leading slash) so it resolves correctly both when PicGen is
    # served at the site root and when it is mounted under a sub-path (e.g. /picgen/).
    return f"files/{file_path.relative_to(data_dir).as_posix()}"


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


def _image_metadata_payload(
    metadata: dict[str, object],
    image_bytes: bytes,
    image_dimensions: tuple[int, int] | None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        **metadata,
        **(extra or {}),
        "saved_image_width": image_dimensions[0] if image_dimensions else None,
        "saved_image_height": image_dimensions[1] if image_dimensions else None,
        "saved_image_bytes": len(image_bytes),
    }


def save_output_image(
    *,
    data_dir: Path,
    outputs_dir: Path,
    mode: str,
    image_bytes: bytes,
    image_mime: str,
    metadata: dict[str, object],
    filename_prefix: str = "",
) -> dict[str, object]:
    now = datetime.now()
    safe_prefix = sanitize_filename_prefix(filename_prefix)
    day_dir = output_group_dir(outputs_dir, now, safe_prefix)
    base_stem = f"{mode}-{now.strftime('%H%M%S')}-{uuid.uuid4().hex[:8]}"
    stem = f"{safe_prefix}-{base_stem}" if safe_prefix else base_stem
    image_path = day_dir / f"{stem}{extension_for_mime(image_mime)}"
    image_dimensions = detect_image_dimensions(image_bytes)
    metadata_payload = _image_metadata_payload(metadata, image_bytes, image_dimensions)

    _atomic_write_bytes(image_path, image_bytes)

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
        "saved_image_bytes": len(image_bytes),
        "saved_metadata_path": "",
        "saved_metadata_url": "",
        "metadata": metadata_payload,
    }


def _is_within_outputs(path: Path, outputs_dir: Path) -> bool:
    """The derived-image path can originate from a client-supplied string when
    the DB record has no saved path; never adopt a directory outside outputs."""

    try:
        path.resolve().relative_to(outputs_dir.resolve())
    except (ValueError, OSError):
        return False
    return True


def save_derived_output_image(
    *,
    data_dir: Path,
    outputs_dir: Path,
    source_image_path: str,
    mode: str,
    image_bytes: bytes,
    image_mime: str,
    metadata: dict[str, object],
    suffix: str,
) -> dict[str, object]:
    now = datetime.now()
    source_path = Path(source_image_path) if source_image_path else None
    source_digest = ""
    if source_path is not None and source_path.is_file() and _is_within_outputs(source_path, outputs_dir):
        relative_source = source_path.resolve().relative_to(outputs_dir.resolve())
        group_prefix = ""
        if len(relative_source.parts) >= 3:
            try:
                datetime.strptime(relative_source.parts[0], "%Y%m%d")
            except ValueError:
                pass
            else:
                group_prefix = relative_source.parts[1]
        day_dir = output_group_dir(outputs_dir, now, group_prefix)
        cleaned_source_stem = _sanitize_filename_core(source_path.stem).strip(".-_")
        source_stem = sanitize_filename_prefix(source_path.stem)
        if len(cleaned_source_stem) > 48:
            source_digest = hashlib.sha256(relative_source.as_posix().encode()).hexdigest()[:12]
    else:
        day_dir = outputs_dir / now.strftime("%Y%m%d")
        source_stem = ""

    if not source_stem:
        source_stem = f"{sanitize_filename_prefix(mode) or 'result'}-{now.strftime('%H%M%S')}-{uuid.uuid4().hex[:8]}"
    elif source_digest:
        source_stem = f"{source_stem[:35].rstrip('.-_')}-{source_digest}"

    safe_suffix = sanitize_filename_prefix(suffix) or "final"
    stem = f"{source_stem}-{safe_suffix}"
    image_path = day_dir / f"{stem}{extension_for_mime(image_mime)}"
    image_dimensions = detect_image_dimensions(image_bytes)
    metadata_payload = _image_metadata_payload(
        metadata,
        image_bytes,
        image_dimensions,
        extra={"source_image_path": source_image_path},
    )

    _atomic_write_bytes(image_path, image_bytes)

    log_event(
        logger,
        logging.INFO,
        "storage_derived_saved",
        mode=mode,
        path=str(image_path),
        source_path=source_image_path,
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
        "saved_image_bytes": len(image_bytes),
        "saved_metadata_path": "",
        "saved_metadata_url": "",
        "metadata": metadata_payload,
    }


def prune_old_outputs(outputs_dir: Path, retention_days: int) -> int:
    """Delete day-folders older than retention_days. Returns count removed."""

    if retention_days <= 0 or not outputs_dir.exists():
        return 0
    # Day-folders are named with local time in `save_output_image`, so compare
    # against local time here too — mixing UTC and local would prune a day early
    # or late for servers far from UTC.
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    for entry in outputs_dir.iterdir():
        try:
            day = datetime.strptime(entry.name, "%Y%m%d")
        except ValueError:
            continue
        # A day-folder's newest file can be written just before the next
        # midnight, so compare the folder's END of day against the cutoff.
        # Comparing its start (midnight) would delete files up to a day early —
        # with retention_days=1 an image saved at 23:59 would die minutes later.
        if day + timedelta(days=1) > cutoff:
            continue
        if entry.is_symlink():
            try:
                entry.unlink()
            except OSError as exc:
                log_event(logger, logging.WARNING, "storage_prune_failed", folder=str(entry), error=type(exc).__name__)
                continue
            removed += 1
            log_event(logger, logging.INFO, "storage_pruned", folder=str(entry))
            continue
        if not entry.is_dir():
            continue
        # Older releases wrote newly-created derived images back into the source
        # day-folder. Preserve those legacy files until their own retention age;
        # lstat intentionally ignores symlink targets.
        cutoff_ts = cutoff.timestamp()
        has_recent_file = False
        for file_path in entry.rglob("*"):
            try:
                file_stat = file_path.lstat()
                if stat.S_ISREG(file_stat.st_mode) and file_stat.st_mtime > cutoff_ts:
                    has_recent_file = True
                    break
            except OSError:
                continue
        if has_recent_file:
            log_event(logger, logging.INFO, "storage_prune_skipped_recent", folder=str(entry))
            continue
        try:
            shutil.rmtree(entry)
        except OSError as exc:
            log_event(logger, logging.WARNING, "storage_prune_failed", folder=str(entry), error=type(exc).__name__)
            continue
        removed += 1
        log_event(logger, logging.INFO, "storage_pruned", folder=str(entry))
    return removed

from __future__ import annotations

from datetime import datetime, timedelta
from http import HTTPStatus
from pathlib import Path

import pytest

from picgen.errors import APIError
from picgen.storage import (
    detect_image_dimensions,
    detect_image_mime,
    extension_for_mime,
    prune_old_outputs,
    resolve_storage_path,
    sanitize_filename,
    save_output_image,
)


def test_resolve_storage_path_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(APIError) as exc_info:
        resolve_storage_path(tmp_path, "../secret.txt")
    assert exc_info.value.status == HTTPStatus.FORBIDDEN
    assert exc_info.value.message == "非法文件路径"


def test_resolve_storage_path_rejects_url_encoded_traversal(tmp_path: Path) -> None:
    with pytest.raises(APIError):
        resolve_storage_path(tmp_path, "%2e%2e/secret.txt")


def test_resolve_storage_path_accepts_safe_subpath(tmp_path: Path) -> None:
    target = resolve_storage_path(tmp_path, "outputs/20260522/file.png")
    assert str(target).startswith(str(tmp_path.resolve()))


def test_detect_png_dimensions() -> None:
    image_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x02"
        b"\x00\x00\x00\x03"
        b"\x08\x02\x00\x00\x00"
        b"\x00\x00\x00\x00"
    )
    assert detect_image_dimensions(image_bytes) == (2, 3)


def test_detect_webp_vp8_lossy_dimensions() -> None:
    image_bytes = (
        b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP"
        + b"VP8 " + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00"  # 3-byte frame tag
        + b"\x9d\x01\x2a"  # keyframe start code
        + (4).to_bytes(2, "little")  # width
        + (5).to_bytes(2, "little")  # height
    )
    assert detect_image_dimensions(image_bytes) == (4, 5)


def test_detect_webp_vp8l_lossless_dimensions() -> None:
    # width-1 = 3, height-1 = 4 packed into 14-bit fields.
    bits = (3) | (4 << 14)
    image_bytes = (
        b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP"
        + b"VP8L" + b"\x00\x00\x00\x00"
        + b"\x2f"
        + bits.to_bytes(4, "little")
    )
    assert detect_image_dimensions(image_bytes) == (4, 5)


def test_detect_image_mime_recognises_signatures() -> None:
    assert detect_image_mime(b"\x89PNG\r\n\x1a\n\x00") == "image/png"
    assert detect_image_mime(b"\xff\xd8\xff") == "image/jpeg"
    assert detect_image_mime(b"GIF89a000") == "image/gif"
    assert detect_image_mime(b"RIFF0000WEBPVP8") == "image/webp"
    assert detect_image_mime(b"not-an-image") == "application/octet-stream"


def test_extension_for_unknown_mime_uses_bin() -> None:
    assert extension_for_mime("application/octet-stream") == ".bin"
    assert extension_for_mime("image/avif") == ".bin"


def test_sanitize_filename_strips_unsafe_characters() -> None:
    assert sanitize_filename("../../bad\"name.png") == "badname.png"
    assert sanitize_filename("clean.png") == "clean.png"
    assert sanitize_filename("") == "image.png"
    assert sanitize_filename("a/b\\c") == "abc"
    assert "\x00" not in sanitize_filename("ev\x00il.png")
    assert sanitize_filename("张 三") == "张-三"


def test_save_output_image_atomic(tmp_path: Path) -> None:
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x02"
        b"\x00\x00\x00\x03"
        b"\x08\x02\x00\x00\x00"
        b"\x00\x00\x00\x00"
    )
    payload = save_output_image(
        data_dir=tmp_path,
        outputs_dir=tmp_path / "outputs",
        mode="generate",
        image_bytes=png_bytes,
        image_mime="image/png",
        metadata={"mode": "generate", "prompt": "hi"},
    )
    saved_image = Path(payload["saved_image_path"])
    assert saved_image.is_file()
    assert saved_image.read_bytes() == png_bytes
    assert payload["saved_metadata_path"] == ""
    assert payload["saved_metadata_url"] == ""
    assert payload["metadata"] == {
        "mode": "generate",
        "prompt": "hi",
        "saved_image_width": 2,
        "saved_image_height": 3,
        "saved_image_bytes": len(png_bytes),
    }
    assert not list(saved_image.parent.glob("*.json"))
    # No temp files should be left behind
    assert not any(p.name.startswith(".tmp-") for p in saved_image.parent.iterdir())


def test_save_output_image_can_prefix_filename_with_user(tmp_path: Path) -> None:
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x02"
        b"\x00\x00\x00\x03"
        b"\x08\x02\x00\x00\x00"
        b"\x00\x00\x00\x00"
    )

    payload = save_output_image(
        data_dir=tmp_path,
        outputs_dir=tmp_path / "outputs",
        mode="reference",
        image_bytes=png_bytes,
        image_mime="image/png",
        metadata={"mode": "reference", "prompt": "hi"},
        filename_prefix="wilson wei",
    )

    assert Path(payload["saved_image_path"]).name.startswith("wilson-wei-reference-")


def test_prune_old_outputs_removes_old_folders(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    keep = outputs / datetime.now().strftime("%Y%m%d")
    keep.mkdir(parents=True)
    (keep / "a.png").write_bytes(b"x")
    old = outputs / (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    old.mkdir(parents=True)
    (old / "b.png").write_bytes(b"x")

    removed = prune_old_outputs(outputs, retention_days=7)

    assert removed == 1
    assert not old.exists()
    assert keep.exists()


def test_prune_old_outputs_noop_when_disabled(tmp_path: Path) -> None:
    assert prune_old_outputs(tmp_path, 0) == 0

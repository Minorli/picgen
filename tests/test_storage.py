from http import HTTPStatus
from pathlib import Path

import pytest

from picgen.errors import APIError
from picgen.storage import detect_image_dimensions, resolve_storage_path


def test_resolve_storage_path_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(APIError) as exc_info:
        resolve_storage_path(tmp_path, "../secret.txt")

    assert exc_info.value.status == HTTPStatus.FORBIDDEN
    assert exc_info.value.message == "非法文件路径"


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

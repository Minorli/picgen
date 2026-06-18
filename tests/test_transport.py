from __future__ import annotations

from picgen.upstream.transport import encode_multipart, sanitize_header_value


def test_sanitize_header_value_strips_control_chars():
    assert sanitize_header_value("image/png", fallback="x") == "image/png"
    assert sanitize_header_value("image/png\r\nX-Evil: 1", fallback="x") == "image/pngX-Evil: 1"
    assert sanitize_header_value("\r\n\t", fallback="application/octet-stream") == "application/octet-stream"
    assert sanitize_header_value("", fallback="application/octet-stream") == "application/octet-stream"


def test_encode_multipart_neutralizes_crlf_in_content_type():
    body, content_type = encode_multipart(
        {"model": "gpt-image-2"},
        [
            {
                "field_name": "image",
                "filename": "photo.png",
                "content_type": "image/png\r\nX-Injected: evil",
                "data": b"\x89PNG\r\n",
            }
        ],
    )
    # The CRLF is stripped, so the attacker cannot inject an extra header line into
    # the multipart part PicGen sends upstream.
    assert b"\r\nX-Injected:" not in body
    assert content_type.startswith("multipart/form-data; boundary=")


def test_encode_multipart_emits_clean_content_type_on_its_own_line():
    body, _ = encode_multipart(
        {},
        [{"field_name": "image", "filename": "photo.png", "content_type": "image/png", "data": b"\x89PNG"}],
    )
    assert b"Content-Type: image/png\r\n\r\n" in body

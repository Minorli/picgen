from __future__ import annotations

import os
from datetime import datetime, timedelta
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from picgen.errors import APIError
from picgen.storage import (
    composite_masked_edit_image,
    detect_image_dimensions,
    detect_image_mime,
    extension_for_mime,
    prune_old_outputs,
    resize_image_to_exact_size,
    resolve_storage_path,
    sanitize_filename,
    save_output_image,
    storage_is_writable,
)


def _png_bytes(width: int, height: int, color: tuple[int, int, int] = (20, 120, 200)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="PNG")
    return output.getvalue()


def _oriented_jpeg_bytes(width: int, height: int, orientation: int) -> bytes:
    output = BytesIO()
    exif = Image.Exif()
    exif[274] = orientation
    Image.new("RGB", (width, height), (20, 120, 200)).save(output, format="JPEG", exif=exif)
    return output.getvalue()


def test_storage_is_writable_fsyncs_and_cleans_up_probe(tmp_path: Path) -> None:
    assert storage_is_writable(tmp_path) is True
    assert list(tmp_path.glob(".picgen-ready-*")) == []


@pytest.mark.parametrize(
    ("blocks_available", "inodes_available"),
    ((0, 1), (4096, 0)),
)
def test_storage_is_writable_rejects_exhausted_filesystem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    blocks_available: int,
    inodes_available: int,
) -> None:
    filesystem = SimpleNamespace(
        f_blocks=1,
        f_bavail=blocks_available,
        f_frsize=4096,
        f_bsize=4096,
        f_files=1,
        f_favail=inodes_available,
    )
    monkeypatch.setattr("picgen.storage.os.statvfs", lambda _path: filesystem)

    assert storage_is_writable(tmp_path) is False
    assert list(tmp_path.glob(".picgen-ready-*")) == []


def test_storage_is_writable_cleans_up_after_fsync_failure(tmp_path: Path, monkeypatch) -> None:
    def fail_fsync(_file_descriptor: int) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr("picgen.storage.os.fsync", fail_fsync)

    assert storage_is_writable(tmp_path) is False
    assert list(tmp_path.glob(".picgen-ready-*")) == []


def test_masked_edit_composite_preserves_every_pixel_outside_transparent_mask() -> None:
    source = Image.new("RGBA", (4, 4), (220, 30, 30, 255))
    generated = Image.new("RGBA", (4, 4), (20, 80, 220, 255))
    mask = Image.new("RGBA", (4, 4), (255, 255, 255, 255))
    mask.putpixel((1, 1), (255, 255, 255, 0))
    mask.putpixel((2, 2), (255, 255, 255, 0))

    def encode(image: Image.Image) -> bytes:
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    result_bytes, result_mime, metadata = composite_masked_edit_image(
        source_image_bytes=encode(source),
        mask_image_bytes=encode(mask),
        generated_image_bytes=encode(generated),
        generated_image_mime="image/png",
    )

    with Image.open(BytesIO(result_bytes)) as result:
        assert result.convert("RGBA").getpixel((0, 0)) == (220, 30, 30, 255)
        assert result.convert("RGBA").getpixel((3, 3)) == (220, 30, 30, 255)
        assert result.convert("RGBA").getpixel((1, 1)) == (20, 80, 220, 255)
        assert result.convert("RGBA").getpixel((2, 2)) == (20, 80, 220, 255)
    assert result_mime == "image/png"
    assert metadata == {
        "mask_composited": True,
        "mask_preserve_mode": "inverse_alpha",
        "mask_source_size": "4x4",
    }


def test_masked_edit_composite_uses_png8_palette_transparency_as_alpha() -> None:
    source = Image.new("RGBA", (4, 4), (220, 30, 30, 255))
    generated = Image.new("RGBA", (4, 4), (20, 80, 220, 255))
    mask = Image.new("P", (4, 4), 1)
    mask.putpalette([0, 0, 0, 255, 255, 255] + [0, 0, 0] * 254)
    mask.putpixel((1, 1), 0)
    mask.putpixel((2, 2), 0)
    mask.info["transparency"] = bytes([0, 255])

    def encode(image: Image.Image) -> bytes:
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    mask_bytes = encode(mask)
    assert b"tRNS" in mask_bytes
    with Image.open(BytesIO(mask_bytes)) as persisted_mask:
        assert persisted_mask.mode == "P"
        assert persisted_mask.getbands() == ("P",)
        assert "transparency" in persisted_mask.info

    result_bytes, result_mime, metadata = composite_masked_edit_image(
        source_image_bytes=encode(source),
        mask_image_bytes=mask_bytes,
        generated_image_bytes=encode(generated),
        generated_image_mime="image/png",
    )

    with Image.open(BytesIO(result_bytes)) as result:
        rgba = result.convert("RGBA")
        assert rgba.getpixel((0, 0)) == (220, 30, 30, 255)
        assert rgba.getpixel((3, 3)) == (220, 30, 30, 255)
        assert rgba.getpixel((1, 1)) == (20, 80, 220, 255)
        assert rgba.getpixel((2, 2)) == (20, 80, 220, 255)
    assert result_mime == "image/png"
    assert metadata["mask_composited"] is True


@pytest.mark.parametrize("oversized_part", ["source", "mask", "generated"])
def test_masked_edit_composite_rejects_oversized_inputs_before_decode(oversized_part: str) -> None:
    images = {
        "source": bytearray(_png_bytes(1, 1)),
        "mask": bytearray(_png_bytes(1, 1)),
        "generated": bytearray(_png_bytes(1, 1)),
    }
    images[oversized_part][16:20] = (4096).to_bytes(4, "big")
    images[oversized_part][20:24] = (4096).to_bytes(4, "big")

    with pytest.raises(ValueError, match=rf"{oversized_part} image exceeds"):
        composite_masked_edit_image(
            source_image_bytes=bytes(images["source"]),
            mask_image_bytes=bytes(images["mask"]),
            generated_image_bytes=bytes(images["generated"]),
            generated_image_mime="image/png",
        )


def test_masked_edit_composite_converts_pillow_decompression_bomb_to_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_output = BytesIO()
    Image.new("RGB", (3, 1), (220, 30, 30)).save(source_output, format="TIFF")
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)

    with pytest.raises(ValueError, match=r"source image exceeds"):
        composite_masked_edit_image(
            source_image_bytes=source_output.getvalue(),
            mask_image_bytes=_png_bytes(1, 1),
            generated_image_bytes=_png_bytes(1, 1),
            generated_image_mime="image/png",
        )


def test_masked_edit_composite_returns_to_source_dimensions_before_preserving_pixels() -> None:
    source = Image.new("RGBA", (4, 6), (220, 30, 30, 255))
    generated = Image.new("RGBA", (2, 2), (20, 80, 220, 255))
    mask = Image.new("RGBA", source.size, (255, 255, 255, 255))
    mask.putpixel((2, 3), (255, 255, 255, 0))

    def encode(image: Image.Image) -> bytes:
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    result_bytes, _, _ = composite_masked_edit_image(
        source_image_bytes=encode(source),
        mask_image_bytes=encode(mask),
        generated_image_bytes=encode(generated),
        generated_image_mime="image/png",
    )

    with Image.open(BytesIO(result_bytes)) as result:
        rgba = result.convert("RGBA")
        assert rgba.size == source.size
        assert rgba.getpixel((0, 0)) == (220, 30, 30, 255)
        assert rgba.getpixel((3, 5)) == (220, 30, 30, 255)
        assert rgba.getpixel((2, 3)) == (20, 80, 220, 255)


def test_itinerary_map_svg_requires_coordinates(tmp_path: Path) -> None:
    from picgen.itinerary_map import build_itinerary_map_plan

    plan = build_itinerary_map_plan(
        title="多彩新疆游",
        subtitle="5/12 - 5/24",
        stops=[
            {"date": "5/12", "name": "乌鲁木齐", "lat": 43.8256, "lng": 87.6168, "transport": "飞机"},
            {"date": "5/13", "name": "赛里木湖", "transport": "包车"},
        ],
    )

    assert plan["status"] == "needs_confirmation"
    assert plan["stops"][0]["status"] == "ok"
    assert plan["stops"][1]["status"] == "needs_coordinates"
    assert "缺少坐标" in plan["warnings"][0]


def test_itinerary_map_svg_renders_program_owned_route_layer(tmp_path: Path) -> None:
    from picgen.itinerary_map import build_itinerary_map_plan, render_itinerary_map_svg, save_itinerary_map_svg

    plan = build_itinerary_map_plan(
        title="多彩新疆游",
        subtitle="5/12 - 5/24",
        stops=[
            {"date": "5/12", "name": "乌鲁木齐", "lat": 43.8256, "lng": 87.6168, "transport": "飞机"},
            {"date": "5/13", "name": "赛里木湖", "lat": 44.5946, "lng": 81.1606, "transport": "包车"},
            {"date": "5/20", "name": "喀什", "lat": 39.4704, "lng": 75.9898, "transport": "飞机"},
        ],
    )

    assert plan["status"] == "ready"
    svg = render_itinerary_map_svg(plan)

    assert "<svg" in svg
    assert 'data-layer="program-route"' in svg
    assert 'data-layer="program-labels"' in svg
    assert 'data-layer="program-poster-map-base"' in svg
    assert 'class="map-callout"' in svg
    assert "多彩新疆游" in svg
    assert "乌鲁木齐" in svg
    assert "赛里木湖" in svg
    assert "喀什" in svg
    assert " C " in svg
    assert "6renyou.png" not in svg
    assert "AI" not in svg

    embedded_logo_svg = render_itinerary_map_svg(plan, logo_href="data:image/png;base64,abc123")
    assert "data:image/png;base64,abc123" in embedded_logo_svg
    external_background_svg = render_itinerary_map_svg(plan, background_image_url="https://example.com/map.png")
    assert "https://example.com/map.png" not in external_background_svg

    saved = save_itinerary_map_svg(
        data_dir=tmp_path,
        outputs_dir=tmp_path / "outputs",
        svg_text=svg,
        metadata={"mode": "itinerary", "prompt": "route"},
        filename_prefix="alice",
        width=1792,
        height=1792,
    )

    saved_path = Path(saved["saved_image_path"])
    assert saved_path.suffix == ".svg"
    assert saved["saved_image_mime"] == "image/svg+xml"
    assert saved_path.is_file()
    assert saved_path.read_text(encoding="utf-8") == svg


@pytest.mark.asyncio
async def test_itinerary_map_plan_can_geocode_missing_coordinates() -> None:
    from picgen.itinerary_map import build_itinerary_map_plan_async

    async def geocode(name: str) -> list[dict[str, object]]:
        if name == "城市 A":
            return [{"name": "城市 A", "lat": 35.6812, "lng": 139.7671, "confidence": 0.98}]
        return []

    plan = await build_itinerary_map_plan_async(
        title="全球旅行路线图",
        subtitle="D1 - D2",
        stops=[
            {"date": "D1", "name": "城市 A", "transport": "火车"},
            {"date": "D2", "name": "城市 B", "lat": 34.6937, "lng": 135.5023, "transport": "自驾"},
        ],
        geocode=geocode,
    )

    assert plan["status"] == "ready"
    assert plan["stops"][0]["status"] == "ok"
    assert plan["stops"][0]["geocoded"] is True
    assert plan["stops"][0]["lat"] == 35.6812


@pytest.mark.asyncio
async def test_itinerary_map_plan_marks_ambiguous_geocoding_for_confirmation() -> None:
    from picgen.itinerary_map import build_itinerary_map_plan_async

    async def geocode(_name: str) -> list[dict[str, object]]:
        return [
            {"name": "城市 A", "lat": 1.0, "lng": 2.0, "confidence": 0.8},
            {"name": "城市 A 另一个", "lat": 3.0, "lng": 4.0, "confidence": 0.76},
        ]

    plan = await build_itinerary_map_plan_async(
        title="全球旅行路线图",
        subtitle="D1",
        stops=[{"name": "城市 A"}],
        geocode=geocode,
    )

    assert plan["status"] == "needs_confirmation"
    assert plan["stops"][0]["status"] == "ambiguous"
    assert len(plan["stops"][0]["candidates"]) == 2


@pytest.mark.asyncio
async def test_itinerary_map_plan_reuses_geocode_results_for_duplicate_stops() -> None:
    from picgen.itinerary_map import build_itinerary_map_plan_async

    calls: list[str] = []

    async def geocode(name: str) -> list[dict[str, object]]:
        calls.append(name)
        return [{"name": name, "lat": 48.8566, "lng": 2.3522, "confidence": 0.96}]

    plan = await build_itinerary_map_plan_async(
        title="欧洲旅行路线图",
        subtitle="D1 - D3",
        stops=[
            {"date": "D1", "name": "巴黎"},
            {"date": "D2", "name": "巴黎"},
            {"date": "D3", "name": "罗马", "lat": 41.9028, "lng": 12.4964},
        ],
        geocode=geocode,
    )

    assert calls == ["巴黎"]
    assert plan["status"] == "ready"
    assert plan["stops"][0]["status"] == "ok"
    assert plan["stops"][1]["status"] == "ok"
    assert plan["stops"][0]["lat"] == plan["stops"][1]["lat"]


@pytest.mark.asyncio
async def test_itinerary_map_plan_caps_external_geocode_lookups() -> None:
    from picgen.itinerary_map import MAX_GEOCODE_LOOKUPS_PER_PLAN, build_itinerary_map_plan_async

    calls: list[str] = []

    async def geocode(name: str) -> list[dict[str, object]]:
        calls.append(name)
        index = len(calls)
        return [{"name": name, "lat": float(index), "lng": float(index), "confidence": 0.9}]

    stops = [{"date": f"D{index}", "name": f"城市 {index}"} for index in range(1, MAX_GEOCODE_LOOKUPS_PER_PLAN + 4)]
    plan = await build_itinerary_map_plan_async(
        title="全球旅行路线图",
        subtitle="D1 - D27",
        stops=stops,
        geocode=geocode,
    )

    assert len(calls) == MAX_GEOCODE_LOOKUPS_PER_PLAN
    assert plan["stops"][MAX_GEOCODE_LOOKUPS_PER_PLAN - 1]["status"] == "ok"
    assert plan["stops"][MAX_GEOCODE_LOOKUPS_PER_PLAN]["status"] == "needs_coordinates"
    assert plan["stops"][MAX_GEOCODE_LOOKUPS_PER_PLAN]["geocode_skipped"] is True


def test_itinerary_map_plan_applies_valid_approximate_coordinates_only() -> None:
    from picgen.itinerary_map import apply_itinerary_coordinate_estimates, build_itinerary_map_plan

    plan = build_itinerary_map_plan(
        title="全球旅行路线图",
        subtitle="D1 - D2",
        stops=[
            {"date": "D1", "name": "巴黎"},
            {"date": "D2", "name": "罗马"},
        ],
    )

    completed = apply_itinerary_coordinate_estimates(
        plan,
        [
            {"index": 0, "name": "巴黎", "lat": 48.8566, "lng": 2.3522, "confidence": 0.7},
            {"index": 1, "name": "罗马", "lat": 120.0, "lng": 12.4964, "confidence": 0.9},
        ],
    )

    assert completed["status"] == "needs_confirmation"
    assert completed["stops"][0]["status"] == "ok"
    assert completed["stops"][0]["coordinate_source"] == "ai_approximate"
    assert completed["stops"][0]["approximate"] is True
    assert completed["stops"][1]["status"] == "needs_coordinates"
    assert "罗马" in completed["warnings"][0]


def test_itinerary_map_filters_instruction_rows_and_uses_dense_layout() -> None:
    from picgen.itinerary_map import build_itinerary_map_plan, render_itinerary_map_svg

    base_stops = [
        {"date": "9月5", "name": "罗马", "lat": 41.9028, "lng": 12.4964},
        {"date": "9月7", "name": "佛罗伦萨", "lat": 43.7696, "lng": 11.2558},
        {"date": "9月8", "name": "比萨", "lat": 43.7228, "lng": 10.4017},
        {"date": "9月9", "name": "威尼斯", "lat": 45.4408, "lng": 12.3155},
        {"date": "9月10", "name": "科尔蒂纳丹佩佐", "lat": 46.5405, "lng": 12.1357},
        {"date": "9月11", "name": "锡尔苗内", "lat": 45.493, "lng": 10.608},
        {"date": "9月11", "name": "米兰", "lat": 45.4642, "lng": 9.19},
        {"date": "9月12", "name": "苏黎世", "lat": 47.3769, "lng": 8.5417},
        {"date": "9月12", "name": "卢塞恩", "lat": 47.0502, "lng": 8.3093},
        {"date": "9月12", "name": "格林德瓦", "lat": 46.6242, "lng": 8.0414},
        {"date": "9月13", "name": "因特拉肯", "lat": 46.6863, "lng": 7.8632},
        {"date": "9月14", "name": "采尔马特", "lat": 46.0207, "lng": 7.7491},
        {"date": "9月14", "name": "日内瓦", "lat": 46.2044, "lng": 6.1432},
        {"date": "9月15", "name": "蒙特勒", "lat": 46.4312, "lng": 6.9107},
        {"date": "9月16", "name": "第戎", "lat": 47.322, "lng": 5.0415},
        {"date": "9月17", "name": "巴黎", "lat": 48.8566, "lng": 2.3522},
    ]
    plan = build_itinerary_map_plan(
        title="深研法意瑞",
        subtitle="9/5 - 9/19",
        stops=[
            *base_stops,
            {"name": "地点与地理校验", "lat": 48.8566, "lng": 2.3522},
            {"name": "必须保持真实相对位置", "lat": 48.8566, "lng": 2.3522},
            {"name": "不要标注公里数，不要标注汽车", "lat": 48.8566, "lng": 2.3522},
        ],
    )

    assert plan["status"] == "ready"
    assert [stop["name"] for stop in plan["stops"]][-1] == "巴黎"
    assert "地点与地理校验" not in str(plan["stops"])

    svg = render_itinerary_map_svg(plan, width=1920, height=1088)

    assert 'data-density="dense"' in svg
    assert 'data-layer="program-labels"' in svg
    assert 'class="map-callout"' in svg
    assert 'data-layer="program-index-labels"' in svg
    assert 'data-layer="program-itinerary-table"' not in svg
    assert 'data-layer="program-poster-map-base"' in svg
    assert " C " in svg
    assert "蒙特勒" in svg
    assert "巴黎" in svg
    assert "地点与地理校验" not in svg
    assert "不要标注公里数" not in svg
    assert "第 16 站" not in svg


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
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x03\x08\x02\x00\x00\x00\x00\x00\x00\x00"
    )
    assert detect_image_dimensions(image_bytes) == (2, 3)


def test_resize_image_to_exact_size_records_source_dimensions() -> None:
    resized_bytes, resized_mime, metadata = resize_image_to_exact_size(
        _png_bytes(10, 20),
        "image/png",
        (20, 40),
    )

    assert resized_mime == "image/png"
    assert detect_image_dimensions(resized_bytes) == (20, 40)
    assert metadata == {
        "image_size_normalized": True,
        "image_size_normalized_method": "cover_lanczos",
        "upstream_actual_size": "10x20",
        "upstream_image_width": 10,
        "upstream_image_height": 20,
    }


def test_resize_image_to_exact_size_rejects_oversized_source_before_decode() -> None:
    image_bytes = bytearray(_png_bytes(1, 1))
    image_bytes[16:20] = (4096).to_bytes(4, "big")
    image_bytes[20:24] = (4096).to_bytes(4, "big")

    with pytest.raises(ValueError, match="source image exceeds"):
        resize_image_to_exact_size(bytes(image_bytes), "image/png", (20, 40))


def test_detect_jpeg_dimensions_skips_repeated_marker_fill_bytes() -> None:
    image_bytes = _oriented_jpeg_bytes(100, 200, 1)
    padded_marker = image_bytes[:3] + b"\xff" + image_bytes[3:]

    assert Image.open(BytesIO(padded_marker)).size == (100, 200)
    assert detect_image_dimensions(padded_marker) == (100, 200)


def test_resize_rechecks_jpeg_pixel_limit_after_pillow_opens_image() -> None:
    image_bytes = bytearray(_oriented_jpeg_bytes(100, 200, 1))
    image_bytes[3:3] = b"\xff"
    sof_index = image_bytes.find(b"\xff\xc0")
    assert sof_index > 0
    image_bytes[sof_index + 5 : sof_index + 7] = (4096).to_bytes(2, "big")
    image_bytes[sof_index + 7 : sof_index + 9] = (4096).to_bytes(2, "big")

    with pytest.raises(ValueError, match="source image exceeds"):
        resize_image_to_exact_size(bytes(image_bytes), "image/jpeg", (20, 40))


def test_detect_webp_vp8_lossy_dimensions() -> None:
    image_bytes = (
        b"RIFF"
        + b"\x00\x00\x00\x00"
        + b"WEBP"
        + b"VP8 "
        + b"\x00\x00\x00\x00"
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
        b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"VP8L" + b"\x00\x00\x00\x00" + b"\x2f" + bits.to_bytes(4, "little")
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
    assert sanitize_filename('../../bad"name.png') == "badname.png"
    assert sanitize_filename("clean.png") == "clean.png"
    assert sanitize_filename("") == "image.png"
    assert sanitize_filename("a/b\\c") == "abc"
    assert "\x00" not in sanitize_filename("ev\x00il.png")
    assert sanitize_filename("张 三") == "张-三"


def test_save_output_image_atomic(tmp_path: Path) -> None:
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x03\x08\x02\x00\x00\x00\x00\x00\x00\x00"
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
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x03\x08\x02\x00\x00\x00\x00\x00\x00\x00"
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
    saved_image = Path(payload["saved_image_path"])
    assert saved_image.parent.name == "wilson-wei"
    assert saved_image.parent.parent.name == datetime.now().strftime("%Y%m%d")


def test_prune_old_outputs_removes_old_folders(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    keep = outputs / datetime.now().strftime("%Y%m%d")
    keep.mkdir(parents=True)
    (keep / "a.png").write_bytes(b"x")
    old = outputs / (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    old.mkdir(parents=True)
    stale_file = old / "b.png"
    stale_file.write_bytes(b"x")
    # 文件 mtime 也要是旧的：文件夹里存在保留期内的新文件时（比如给旧图
    # 贴 LOGO 产出的成品）整个文件夹会被跳过，不再按名字整删。
    old_ts = (datetime.now() - timedelta(days=30)).timestamp()
    os.utime(stale_file, (old_ts, old_ts))

    removed = prune_old_outputs(outputs, retention_days=7)

    assert removed == 1
    assert not old.exists()
    assert keep.exists()


def test_prune_old_outputs_does_not_follow_recent_symlink(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    old = outputs / (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    old.mkdir(parents=True)
    external = tmp_path / "recent.png"
    external.write_bytes(b"recent")
    (old / "external.png").symlink_to(external)

    removed = prune_old_outputs(outputs, retention_days=7)

    assert removed == 1
    assert not old.exists()
    assert external.exists()


def test_prune_old_outputs_unlinks_dated_directory_symlink_without_following_it(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "recent.png").write_bytes(b"recent")
    linked_day = outputs / (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    linked_day.symlink_to(external, target_is_directory=True)

    removed = prune_old_outputs(outputs, retention_days=7)

    assert removed == 1
    assert not linked_day.exists()
    assert (external / "recent.png").exists()


def test_detect_image_dimensions_honors_jpeg_exif_orientation() -> None:
    image_bytes = _oriented_jpeg_bytes(100, 200, orientation=6)
    large_app2 = b"\xff\xe2" + (65535).to_bytes(2, "big") + (b"x" * 65533)
    image_bytes = image_bytes[:2] + large_app2 + image_bytes[2:]

    assert detect_image_dimensions(image_bytes) == (200, 100)
    resized, image_mime, metadata = resize_image_to_exact_size(image_bytes, "image/jpeg", (200, 100))

    assert resized == image_bytes
    assert image_mime == "image/jpeg"
    assert metadata == {}


def test_prune_old_outputs_noop_when_disabled(tmp_path: Path) -> None:
    assert prune_old_outputs(tmp_path, 0) == 0

from __future__ import annotations

from pathlib import Path

import pytest

from picgen import itinerary_map as im


def _project(stops, *, width=1792, height=1792):
    return im._project_stops(
        [{**s, "status": "ok"} for s in stops], width=width, height=height
    )


def _render_heading(*, title: str, subtitle: str = "") -> str:
    return im.render_itinerary_map_svg(
        {
            "title": title,
            "subtitle": subtitle,
            "stops": [
                {"name": "巴黎", "lat": 48.8566, "lng": 2.3522, "status": "ok"},
                {"name": "罗马", "lat": 41.9028, "lng": 12.4964, "status": "ok"},
            ],
        }
    )


def test_title_font_subsetting_continues_after_non_oserror(monkeypatch) -> None:
    broken_dir = Path("/broken-static")
    working_dir = Path("/working-static")
    calls: list[Path] = []

    def subset(font_path: Path, _glyphs: str) -> bytes:
        calls.append(font_path)
        if font_path.is_relative_to(broken_dir):
            raise ValueError("invalid font")
        return b"fallback-font"

    im._embedded_title_font_face_css_cached.cache_clear()
    monkeypatch.setattr(im, "_candidate_static_dirs", lambda: [broken_dir, working_dir])
    monkeypatch.setattr(im, "_subset_title_font_bytes", subset)

    try:
        css = im._embedded_title_font_face_css("欧洲行程")
    finally:
        im._embedded_title_font_face_css_cached.cache_clear()

    assert "data:font/ttf;base64," in css
    assert calls == [
        broken_dir / im.TITLE_FONT_RELATIVE_PATH,
        working_dir / im.TITLE_FONT_RELATIVE_PATH,
    ]


def test_failed_title_subset_does_not_evict_other_cached_titles(monkeypatch) -> None:
    calls: list[str] = []

    def subset(_font_path: Path, glyphs: str) -> bytes:
        calls.append(glyphs)
        if glyphs == "乙":
            raise OSError("temporarily unavailable")
        return f"font-{glyphs}".encode()

    im._embedded_title_font_face_css_cached.cache_clear()
    monkeypatch.setattr(im, "_candidate_static_dirs", lambda: [Path("/static")])
    monkeypatch.setattr(im, "_subset_title_font_bytes", subset)

    try:
        first_css = im._embedded_title_font_face_css("甲")
        assert im._embedded_title_font_face_css("乙") == ""
        assert im._embedded_title_font_face_css("乙") == ""
        assert im._embedded_title_font_face_css("甲") == first_css
    finally:
        im._embedded_title_font_face_css_cached.cache_clear()

    assert calls.count("甲") == 1
    assert calls.count("乙") == 2


@pytest.mark.parametrize(
    ("title", "font_size"),
    [
        ("甲" * 8, 80),
        ("甲" * 9, 64),
        ("甲" * 11, 52),
    ],
)
def test_itinerary_title_font_size_uses_character_tiers(title: str, font_size: int) -> None:
    svg = _render_heading(title=title)

    assert f".title{{font-size:{font_size}px" in svg


@pytest.mark.parametrize(
    ("subtitle", "font_size"),
    [
        ("乙" * 20, 32),
        ("乙" * 21, 26),
        ("乙" * 25, 21),
    ],
)
def test_itinerary_subtitle_font_size_uses_character_tiers(subtitle: str, font_size: int) -> None:
    svg = _render_heading(title="欧洲旅行", subtitle=subtitle)

    assert f".subtitle{{font-size:{font_size}px" in svg


def test_itinerary_heading_truncates_after_smallest_font_tier() -> None:
    svg = _render_heading(title="甲" * 13, subtitle="乙" * 31)

    assert f">{'甲' * 11}…</text>" in svg
    assert f">{'乙' * 29}…</text>" in svg
    assert "甲" * 13 not in svg
    assert "乙" * 31 not in svg


def test_country_label_resolves_border_cities_by_nearest_box_center():
    # Overlapping bounding boxes used to mislabel border cities (first-match-wins).
    assert im._country_label_from_coordinates(43.70, 7.27) == "法国"  # Nice
    assert im._country_label_from_coordinates(47.80, 13.05) == "奥地利"  # Salzburg
    assert im._country_label_from_coordinates(46.20, 6.14) == "瑞士"  # Geneva
    # Interior cities are unambiguous.
    assert im._country_label_from_coordinates(48.85, 2.35) == "法国"  # Paris
    assert im._country_label_from_coordinates(41.90, 12.50) == "意大利"  # Rome


def test_xml_clean_text_removes_all_xml_10_invalid_codepoints() -> None:
    assert im._clean_text("A\x08B\ud800C\ufffeD\U00100000E") == "ABCDE"


def test_antimeridian_route_drawn_in_correct_direction():
    # Tokyo -> Honolulu is an eastward Pacific hop; Tokyo (west) must end up left of
    # Honolulu (east), not flung to opposite edges wrapping the wrong way.
    points = _project(
        [
            {"lat": 35.68, "lng": 139.69, "name": "Tokyo"},
            {"lat": 21.31, "lng": -157.86, "name": "Honolulu"},
        ]
    )
    tokyo_x, honolulu_x = points[0]["x"], points[1]["x"]
    assert tokyo_x < honolulu_x


def test_identical_coordinates_cluster_near_canvas_center():
    points = _project([{"lat": 48.85, "lng": 2.35, "name": f"Paris{i}"} for i in range(3)])
    centroid_x = sum(p["x"] for p in points) / len(points)
    # Was ~349 (upper-left) before the fix; must now sit at the horizontal center.
    assert abs(centroid_x - 1792 / 2) < 60


def test_ai_coordinate_estimate_does_not_pin_stop_to_a_different_city():
    plan = {"stops": [im._normalize_stop({"name": "东京"}, 0)]}
    # AI mis-numbers: returns Kyoto's coords under index 0 (the 东京 slot).
    result = im.apply_itinerary_coordinate_estimates(
        plan, [{"index": 0, "name": "京都", "lat": 35.01, "lng": 135.77}]
    )
    stop = result["stops"][0]
    assert stop["status"] == "needs_coordinates"
    assert stop.get("lat") is None

    # A correct (name-matching) estimate still resolves, even under a wrong index.
    ok = im.apply_itinerary_coordinate_estimates(
        {"stops": [im._normalize_stop({"name": "东京"}, 0)]},
        [{"index": 9, "name": "东京", "lat": 35.68, "lng": 139.69}],
    )
    assert ok["stops"][0]["status"] == "ok"
    assert round(ok["stops"][0]["lat"], 2) == 35.68

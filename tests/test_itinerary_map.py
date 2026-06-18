from __future__ import annotations

from picgen import itinerary_map as im


def _project(stops, *, width=1792, height=1792):
    return im._project_stops(
        [{**s, "status": "ok"} for s in stops], width=width, height=height
    )


def test_country_label_resolves_border_cities_by_nearest_box_center():
    # Overlapping bounding boxes used to mislabel border cities (first-match-wins).
    assert im._country_label_from_coordinates(43.70, 7.27) == "法国"  # Nice
    assert im._country_label_from_coordinates(47.80, 13.05) == "奥地利"  # Salzburg
    assert im._country_label_from_coordinates(46.20, 6.14) == "瑞士"  # Geneva
    # Interior cities are unambiguous.
    assert im._country_label_from_coordinates(48.85, 2.35) == "法国"  # Paris
    assert im._country_label_from_coordinates(41.90, 12.50) == "意大利"  # Rome


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

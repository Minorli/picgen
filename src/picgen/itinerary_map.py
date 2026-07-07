from __future__ import annotations

import asyncio
import base64
import html
import math
import os
import re
import struct
import tempfile
import time
import uuid
import zlib
from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib import parse

import httpx

from .config import Settings
from .restricted_destinations import stop_has_restricted_destination
from .storage import output_group_dir, sanitize_filename_prefix, storage_url_for_path

SVG_MIME = "image/svg+xml"
DEFAULT_CANVAS_WIDTH = 1792
DEFAULT_CANVAS_HEIGHT = 1792
MAX_GEOCODE_LOOKUPS_PER_PLAN = 24
NOMINATIM_MIN_REQUEST_INTERVAL_SECONDS = 1.05
LOGO_HREF = "6renyou.png"
TITLE_FONT_FAMILY = "PicGenRouteTitle"
TITLE_FONT_RELATIVE_PATH = Path("fonts/zcool-xiaowei/ZCOOLXiaoWei-Regular.ttf")
INSTRUCTION_STOP_PREFIXES = (
    "地点与地理校验",
    "地理校验",
    "画面要求",
    "程序坐标",
    "行程基础信息",
    "逐日行程",
)
INSTRUCTION_STOP_PHRASES = (
    "必须保持真实相对位置",
    "不要标注公里数",
    "不要标注",
    "不要让 ai",
    "不要让AI",
    "程序会用官方",
    "左上角预留",
    "不能为了画面",
    "日期必须逐日出现",
    "每两个连续地点之间",
    "交通工具图标",
)
RGBColor = tuple[int, int, int]
_LAST_NOMINATIM_REQUEST_AT = 0.0
_NOMINATIM_LOCKS: dict[int, asyncio.Lock] = {}


def _candidate_static_dirs() -> list[Path]:
    candidates: list[Path] = []
    env_static_dir = os.getenv("PICGEN_STATIC_DIR")
    if env_static_dir:
        candidates.append(Path(env_static_dir))
    module_path = Path(__file__).resolve()
    candidates.extend(
        [
            module_path.parents[2] / "static",
            Path.cwd() / "static",
            Path("/app/static"),
        ]
    )
    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(resolved)
    return deduped


@lru_cache(maxsize=1)
def _embedded_title_font_face_css_cached() -> str:
    for static_dir in _candidate_static_dirs():
        font_path = static_dir / TITLE_FONT_RELATIVE_PATH
        try:
            font_bytes = font_path.read_bytes()
        except OSError:
            continue
        encoded = base64.b64encode(font_bytes).decode("ascii")
        return (
            "/* ZCOOL XiaoWei, SIL Open Font License 1.1 */"
            f"@font-face{{font-family:'{TITLE_FONT_FAMILY}';"
            "src:url(data:font/ttf;base64,"
            f"{encoded}) format('truetype');font-weight:400;font-style:normal;font-display:block}}"
        )
    return ""


def _embedded_title_font_face_css() -> str:
    # Only cache SUCCESS: a transient read failure (missing volume, bad cwd at
    # first render) must not permanently strip the title font from every
    # poster this process renders afterwards.
    css = _embedded_title_font_face_css_cached()
    if not css:
        _embedded_title_font_face_css_cached.cache_clear()
    return css

COUNTRY_LABEL_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("意大利", ("意大利", "italy", "italia")),
    ("瑞士", ("瑞士", "switzerland", "schweiz", "suisse", "svizzera")),
    ("法国", ("法国", "france")),
    ("西班牙", ("西班牙", "spain", "españa", "espana")),
    ("葡萄牙", ("葡萄牙", "portugal")),
    ("德国", ("德国", "germany", "deutschland")),
    ("奥地利", ("奥地利", "austria", "österreich", "osterreich")),
    ("英国", ("英国", "united kingdom", "great britain", "england", "scotland", "wales")),
    ("荷兰", ("荷兰", "netherlands", "holland")),
    ("比利时", ("比利时", "belgium", "belgië", "belgique")),
    ("希腊", ("希腊", "greece")),
    ("土耳其", ("土耳其", "turkey", "türkiye", "turkiye")),
    ("中国", ("中国", "china")),
    ("日本", ("日本", "japan")),
    ("韩国", ("韩国", "south korea", "korea", "대한민국")),
    ("泰国", ("泰国", "thailand")),
    ("越南", ("越南", "vietnam", "viet nam")),
    ("新加坡", ("新加坡", "singapore")),
    ("马来西亚", ("马来西亚", "malaysia")),
    ("印尼", ("印尼", "印度尼西亚", "indonesia")),
    ("印度", ("印度", "india")),
    ("美国", ("美国", "united states", "usa", "u.s.a.", "america")),
    ("加拿大", ("加拿大", "canada")),
    ("墨西哥", ("墨西哥", "mexico", "méxico")),
    ("肯尼亚", ("肯尼亚", "kenya")),
    ("坦桑尼亚", ("坦桑尼亚", "tanzania")),
    ("摩洛哥", ("摩洛哥", "morocco")),
    ("埃及", ("埃及", "egypt")),
    ("南非", ("南非", "south africa")),
    ("澳大利亚", ("澳大利亚", "australia")),
    ("新西兰", ("新西兰", "new zealand")),
)

COUNTRY_BOUNDING_BOXES: tuple[tuple[str, float, float, float, float], ...] = (
    ("瑞士", 45.7, 47.9, 5.8, 10.7),
    ("意大利", 35.0, 47.2, 6.4, 18.9),
    ("法国", 41.0, 51.4, -5.6, 9.9),
    ("西班牙", 35.5, 43.9, -9.5, 4.4),
    ("葡萄牙", 36.8, 42.2, -9.6, -6.0),
    ("德国", 47.2, 55.2, 5.8, 15.1),
    ("奥地利", 46.2, 49.2, 9.4, 17.2),
    ("荷兰", 50.6, 53.8, 3.2, 7.3),
    ("比利时", 49.4, 51.7, 2.5, 6.5),
    ("英国", 49.7, 59.0, -8.7, 2.2),
    ("希腊", 34.5, 41.9, 19.0, 29.7),
    ("土耳其", 35.8, 42.2, 25.6, 44.9),
    ("日本", 24.0, 46.4, 122.8, 146.1),
    ("韩国", 33.0, 38.9, 124.4, 131.0),
    ("新加坡", 1.1, 1.6, 103.5, 104.1),
    ("马来西亚", 0.7, 7.5, 99.5, 119.3),
    ("泰国", 5.4, 20.6, 97.3, 105.8),
    ("越南", 8.0, 23.5, 102.0, 109.9),
    ("印尼", -11.2, 6.2, 95.0, 141.2),
    ("印度", 6.5, 35.8, 68.0, 97.5),
    ("中国", 18.0, 54.5, 73.0, 135.5),
    ("加拿大", 41.6, 83.2, -141.0, -52.5),
    ("美国", 18.8, 71.5, -171.8, -66.5),
    ("墨西哥", 14.3, 32.8, -118.8, -86.6),
    ("摩洛哥", 27.5, 35.9, -13.5, -1.0),
    ("埃及", 22.0, 31.8, 24.7, 36.9),
    ("肯尼亚", -4.8, 5.2, 33.8, 42.2),
    ("坦桑尼亚", -11.9, -0.9, 29.0, 40.8),
    ("南非", -35.0, -22.0, 16.0, 33.2),
    ("澳大利亚", -44.0, -10.0, 112.0, 154.0),
    ("新西兰", -47.5, -34.0, 166.0, 179.9),
)


def _clean_text(value: Any, *, limit: int = 160) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    return cleaned[:limit]


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _valid_lat_lng(lat: float | None, lng: float | None) -> bool:
    return lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180


def _normalize_stop(raw: dict[str, Any], index: int) -> dict[str, Any]:
    lat = _float_or_none(raw.get("lat"))
    lng = _float_or_none(raw.get("lng"))
    status = "ok" if _valid_lat_lng(lat, lng) else "needs_coordinates"
    return {
        "index": index,
        "date": _clean_text(raw.get("date"), limit=32),
        "name": _clean_text(raw.get("name"), limit=120) or f"地点 {index + 1}",
        "label": _clean_text(raw.get("label"), limit=120),
        "country": _clean_text(raw.get("country"), limit=48),
        "transport": _clean_text(raw.get("transport"), limit=40),
        "note": _clean_text(raw.get("note"), limit=180),
        "lat": lat,
        "lng": lng,
        "status": status,
        "confidence": 1.0 if status == "ok" else 0.0,
    }


def _looks_like_instruction_stop(stop: dict[str, Any]) -> bool:
    name = _clean_text(stop.get("name"), limit=120)
    if not name:
        return True
    folded = name.casefold()
    if any(name.startswith(prefix) for prefix in INSTRUCTION_STOP_PREFIXES):
        return True
    return any(phrase.casefold() in folded for phrase in INSTRUCTION_STOP_PHRASES)


def _normalize_stops(stops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for stop in stops[:80]:
        if _looks_like_instruction_stop(stop):
            continue
        normalized.append(_normalize_stop(stop, len(normalized)))
    return normalized


GeocodeFn = Callable[[str], Awaitable[list[dict[str, object]]]]


def _geocode_cache_key(stop: dict[str, Any]) -> str:
    name = _clean_text(stop.get("name"), limit=120).casefold()
    country = _clean_text(stop.get("country"), limit=48).casefold()
    return f"{name}\n{country}"


def _geocode_query(stop: dict[str, Any]) -> str:
    name = _clean_text(stop.get("name"), limit=120)
    country = _clean_text(stop.get("country"), limit=48)
    if country and country.casefold() not in name.casefold():
        return f"{name}, {country}"
    return name


def _nominatim_lock_for_current_loop() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    loop_id = id(loop)
    lock = _NOMINATIM_LOCKS.get(loop_id)
    if lock is None:
        lock = asyncio.Lock()
        _NOMINATIM_LOCKS[loop_id] = lock
    return lock


async def _wait_for_nominatim_slot() -> None:
    global _LAST_NOMINATIM_REQUEST_AT

    now = time.monotonic()
    delay = _LAST_NOMINATIM_REQUEST_AT + NOMINATIM_MIN_REQUEST_INTERVAL_SECONDS - now
    if delay > 0:
        await asyncio.sleep(delay)
    _LAST_NOMINATIM_REQUEST_AT = time.monotonic()


async def geocode_place_with_settings(name: str, settings: Settings) -> list[dict[str, object]]:
    try:
        provider = settings.map_provider
        if provider == "amap" and settings.amap_key:
            return await _geocode_amap(name, settings)
        if provider == "mapbox" and settings.mapbox_token:
            return await _geocode_mapbox(name, settings)
        return await _geocode_nominatim(name, settings)
    except (httpx.HTTPError, ValueError):
        return []


async def _geocode_amap(name: str, settings: Settings) -> list[dict[str, object]]:
    async with httpx.AsyncClient(timeout=settings.map_geocode_timeout_seconds) as client:
        response = await client.get(
            "https://restapi.amap.com/v3/geocode/geo",
            params={"key": settings.amap_key, "address": name, "output": "json"},
        )
        response.raise_for_status()
        payload = response.json()
    geocodes = payload.get("geocodes")
    if not isinstance(geocodes, list):
        return []
    results: list[dict[str, object]] = []
    for item in geocodes[:5]:
        if not isinstance(item, dict):
            continue
        location = str(item.get("location") or "")
        if "," not in location:
            continue
        lng_text, lat_text = location.split(",", 1)
        lat = _float_or_none(lat_text)
        lng = _float_or_none(lng_text)
        if not _valid_lat_lng(lat, lng):
            continue
        confidence = 0.95 if str(item.get("level") or "") in {"兴趣点", "道路", "门牌号", "区县"} else 0.9
        results.append(
            {
                "name": item.get("formatted_address") or name,
                "address": item.get("formatted_address") or "",
                "country": item.get("country") or "",
                "lat": lat,
                "lng": lng,
                "confidence": confidence,
            }
        )
    return results


async def _geocode_mapbox(name: str, settings: Settings) -> list[dict[str, object]]:
    async with httpx.AsyncClient(timeout=settings.map_geocode_timeout_seconds) as client:
        response = await client.get(
            # Percent-encode the whole name: "/", "?", "#" in a stop name would
            # otherwise become URL structure and query the wrong text (or 404).
            f"https://api.mapbox.com/geocoding/v5/mapbox.places/{parse.quote(name, safe='')}.json",
            params={"access_token": settings.mapbox_token, "limit": 5, "language": "zh"},
        )
        response.raise_for_status()
        payload = response.json()
    features = payload.get("features")
    if not isinstance(features, list):
        return []
    results: list[dict[str, object]] = []
    for item in features[:5]:
        if not isinstance(item, dict):
            continue
        center = item.get("center")
        if not isinstance(center, list) or len(center) < 2:
            continue
        lng = _float_or_none(center[0])
        lat = _float_or_none(center[1])
        if not _valid_lat_lng(lat, lng):
            continue
        relevance = _float_or_none(item.get("relevance")) or 0.0
        results.append(
            {
                "name": item.get("text") or item.get("place_name") or name,
                "address": item.get("place_name") or "",
                "country": _country_label_from_text(item.get("place_name") or ""),
                "lat": lat,
                "lng": lng,
                "confidence": relevance,
            }
        )
    return results


async def _geocode_nominatim(name: str, settings: Settings) -> list[dict[str, object]]:
    if not settings.nominatim_url:
        return []
    async with _nominatim_lock_for_current_loop():
        await _wait_for_nominatim_slot()
        async with httpx.AsyncClient(timeout=settings.map_geocode_timeout_seconds) as client:
            response = await client.get(
                settings.nominatim_url,
                params={"q": name, "format": "jsonv2", "limit": 5, "accept-language": "zh-CN,zh,en"},
                headers={"User-Agent": settings.upstream_user_agent},
            )
            response.raise_for_status()
            payload = response.json()
    if not isinstance(payload, list):
        return []
    results: list[dict[str, object]] = []
    for item in payload[:5]:
        if not isinstance(item, dict):
            continue
        lat = _float_or_none(item.get("lat"))
        lng = _float_or_none(item.get("lon"))
        if not _valid_lat_lng(lat, lng):
            continue
        importance = _float_or_none(item.get("importance")) or 0.0
        place_rank = _float_or_none(item.get("place_rank")) or 99.0
        confidence = max(0.55, min(0.98, 0.72 + importance * 0.22 + max(0.0, 30.0 - place_rank) / 120.0))
        results.append(
            {
                "name": item.get("name") or item.get("display_name") or name,
                "address": item.get("display_name") or "",
                "country": _country_label_from_text(item.get("display_name") or ""),
                "lat": lat,
                "lng": lng,
                "confidence": confidence,
            }
        )
    return results


def build_itinerary_map_plan(
    *,
    title: str,
    subtitle: str = "",
    stops: list[dict[str, Any]],
    route_style: str = "comic",
) -> dict[str, Any]:
    normalized_stops = _normalize_stops(stops)
    status, warnings = _plan_status_and_warnings(normalized_stops)
    return {
        "status": status,
        "title": _clean_text(title, limit=120) or "定制旅行路线图",
        "subtitle": _clean_text(subtitle, limit=160),
        "route_style": _clean_text(route_style, limit=32) or "comic",
        "stops": normalized_stops,
        "warnings": warnings,
        "background_policy": "ai_optional_no_text_no_routes",
        "final_overlay_policy": "program_points_routes_labels_logo_slot",
    }


def _plan_status_and_warnings(stops: list[dict[str, Any]]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    for stop in stops:
        if stop["status"] == "ok":
            continue
        if stop["status"] == "ambiguous":
            warnings.append(f"{stop['date'] or stop['index'] + 1} {stop['name']} 有多个候选坐标，需要用户确认。")
        else:
            warnings.append(f"{stop['date'] or stop['index'] + 1} {stop['name']} 缺少坐标，不能生成伪精确地图。")

    ready_stops = [stop for stop in stops if stop["status"] == "ok"]
    if len(ready_stops) < 2 and not warnings:
        warnings.append("至少需要两个带坐标的地点才能生成路线图。")

    status = "ready" if not warnings and len(ready_stops) >= 2 else "needs_confirmation"
    return status, warnings


def _safe_index(value: Any, stop_count: int) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if 0 <= parsed < stop_count:
        return parsed
    if 1 <= parsed <= stop_count:
        return parsed - 1
    return None


def _clean_confidence(value: Any) -> float:
    parsed = _float_or_none(value)
    if parsed is None:
        return 0.58
    return max(0.0, min(1.0, parsed))


def apply_itinerary_coordinate_estimates(
    plan: dict[str, Any],
    estimates: list[dict[str, Any]],
    *,
    source: str = "ai_approximate",
) -> dict[str, Any]:
    raw_stops = [stop for stop in plan.get("stops", []) if isinstance(stop, dict)]
    by_index: dict[int, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}

    for estimate in estimates:
        lat = _float_or_none(estimate.get("lat"))
        lng = _float_or_none(estimate.get("lng"))
        if not _valid_lat_lng(lat, lng):
            continue
        normalized_estimate = {
            "name": _clean_text(estimate.get("name"), limit=120),
            "lat": lat,
            "lng": lng,
            "confidence": _clean_confidence(estimate.get("confidence")),
            "note": _clean_text(estimate.get("note") or estimate.get("address"), limit=180),
            "country": _clean_text(estimate.get("country"), limit=48),
        }
        index = _safe_index(estimate.get("index"), len(raw_stops))
        if index is not None:
            by_index[index] = normalized_estimate
        name = str(normalized_estimate["name"]).casefold()
        if name:
            by_name[name] = normalized_estimate

    completed_stops: list[dict[str, Any]] = []
    for stop in raw_stops:
        if stop.get("status") == "ok":
            completed_stops.append({**stop})
            continue
        index = _safe_index(stop.get("index"), len(raw_stops))
        stop_name = str(stop.get("name") or "").casefold()
        name_estimate = by_name.get(stop_name) if stop_name else None
        index_estimate = by_index.get(index) if index is not None else None
        # Prefer a name match. Only fall back to the index match if it does NOT name a
        # different place — otherwise a single mis-numbered AI estimate would silently
        # pin this stop to another city's coordinates. A contradicting index match is
        # dropped so the stop stays unresolved (the customer is told) rather than wrong.
        selected_estimate = name_estimate or index_estimate
        if (
            selected_estimate is index_estimate
            and index_estimate is not None
            and stop_name
        ):
            estimate_name = str(index_estimate.get("name") or "").casefold()
            if estimate_name and estimate_name != stop_name:
                selected_estimate = None
        if selected_estimate is None:
            completed_stops.append({**stop})
            continue
        completed = {
            **stop,
            "lat": selected_estimate["lat"],
            "lng": selected_estimate["lng"],
            "status": "ok",
            "confidence": selected_estimate["confidence"],
            "geocoded": True,
            "geocoded_name": selected_estimate["name"] or stop.get("name", ""),
            "geocoded_address": selected_estimate["note"],
            # Never let an estimate WITHOUT a country wipe the user's explicit
            # one — the coordinate-box fallback that then kicks in mislabels
            # border cities (e.g. 都灵 → 法国).
            "country": selected_estimate["country"] or str(stop.get("country") or ""),
            "coordinate_source": source,
            "approximate": True,
        }
        completed.pop("candidates", None)
        completed_stops.append(completed)

    status, warnings = _plan_status_and_warnings(completed_stops)
    return {
        **plan,
        "status": status,
        "stops": completed_stops,
        "warnings": warnings,
    }


async def build_itinerary_map_plan_async(
    *,
    title: str,
    subtitle: str = "",
    stops: list[dict[str, Any]],
    route_style: str = "comic",
    geocode: GeocodeFn | None = None,
) -> dict[str, Any]:
    normalized_stops = _normalize_stops(stops)
    if geocode is not None:
        geocode_cache: dict[str, list[dict[str, object]]] = {}
        geocode_lookup_count = 0
        for stop in normalized_stops:
            if stop["status"] == "ok":
                continue
            cache_key = _geocode_cache_key(stop)
            candidates = geocode_cache.get(cache_key)
            if candidates is None:
                if geocode_lookup_count >= MAX_GEOCODE_LOOKUPS_PER_PLAN:
                    stop["geocode_skipped"] = True
                    continue
                candidates = await geocode(_geocode_query(stop))
                geocode_lookup_count += 1
                geocode_cache[cache_key] = candidates
            valid_candidates: list[dict[str, object]] = []
            for candidate in candidates[:5]:
                lat = _float_or_none(candidate.get("lat"))
                lng = _float_or_none(candidate.get("lng"))
                if not _valid_lat_lng(lat, lng):
                    continue
                cleaned_candidate = {
                    "name": _clean_text(candidate.get("name"), limit=120) or stop["name"],
                    "lat": lat,
                    "lng": lng,
                    "confidence": _float_or_none(candidate.get("confidence")) or 0.0,
                    "address": _clean_text(candidate.get("address"), limit=180),
                    "country": _clean_text(candidate.get("country"), limit=48),
                }
                if stop_has_restricted_destination(cleaned_candidate):
                    continue
                valid_candidates.append(cleaned_candidate)
            if len(valid_candidates) == 1:
                candidate = valid_candidates[0]
                stop["lat"] = candidate["lat"]
                stop["lng"] = candidate["lng"]
                stop["status"] = "ok"
                stop["confidence"] = candidate["confidence"]
                stop["geocoded"] = True
                stop["geocoded_name"] = candidate["name"]
                stop["geocoded_address"] = candidate["address"]
                stop["country"] = candidate["country"] or str(stop.get("country") or "")
            elif valid_candidates:
                stop["status"] = "ambiguous"
                stop["candidates"] = valid_candidates

    warnings = []
    for stop in normalized_stops:
        if stop["status"] == "ok":
            continue
        if stop["status"] == "ambiguous":
            warnings.append(f"{stop['date'] or stop['index'] + 1} {stop['name']} 有多个候选坐标，需要用户确认。")
        else:
            warnings.append(f"{stop['date'] or stop['index'] + 1} {stop['name']} 缺少坐标，不能生成伪精确地图。")

    ready_stops = [stop for stop in normalized_stops if stop["status"] == "ok"]
    if len(ready_stops) < 2 and not warnings:
        warnings.append("至少需要两个带坐标的地点才能生成路线图。")

    status = "ready" if not warnings and len(ready_stops) >= 2 else "needs_confirmation"
    return {
        "status": status,
        "title": _clean_text(title, limit=120) or "定制旅行路线图",
        "subtitle": _clean_text(subtitle, limit=160),
        "route_style": _clean_text(route_style, limit=32) or "comic",
        "stops": normalized_stops,
        "warnings": warnings,
        "background_policy": "ai_optional_no_text_no_routes",
        "final_overlay_policy": "program_points_routes_labels_logo_slot",
    }


def _mercator(lat: float, lng: float) -> tuple[float, float]:
    clamped_lat = max(min(lat, 85.05112878), -85.05112878)
    x = (lng + 180.0) / 360.0
    sin_lat = math.sin(math.radians(clamped_lat))
    y = 0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)
    return x, y


def _project_stops(
    stops: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    reserve_right: float = 0.0,
) -> list[dict[str, Any]]:
    coords: list[tuple[float, float, dict[str, Any]]] = []
    for stop in stops:
        lat = stop.get("lat")
        lng = stop.get("lng")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            continue
        coords.append((float(lat), float(lng), stop))

    if not coords:
        return []

    # Unwrap longitudes for antimeridian-crossing routes (e.g. Tokyo↔Honolulu) so the
    # route takes the short Pacific path instead of wrapping the wrong way around the map.
    lngs = [lng for _, lng, _ in coords]
    if max(lngs) - min(lngs) > 180.0:
        coords = [(lat, lng + 360.0 if lng < 0 else lng, stop) for lat, lng, stop in coords]

    projected = []
    for lat, lng, stop in coords:
        mx, my = _mercator(lat, lng)
        projected.append({**stop, "_mx": mx, "_my": my})

    min_x = min(stop["_mx"] for stop in projected)
    max_x = max(stop["_mx"] for stop in projected)
    min_y = min(stop["_my"] for stop in projected)
    max_y = max(stop["_my"] for stop in projected)
    real_span_x = max_x - min_x
    real_span_y = max_y - min_y

    margin_x = width * 0.16
    margin_top = height * 0.22
    margin_bottom = height * 0.17
    drawable_w = width - margin_x * 2 - reserve_right
    drawable_h = height - margin_top - margin_bottom
    # Floor the span used for SCALING so a single-city / very-tight cluster doesn't zoom
    # in to fill the whole poster; use the REAL span for route size so identical
    # coordinates yield a zero-width route centered on the canvas (not the corner).
    min_scale_span = 0.012
    scale = min(drawable_w / max(real_span_x, min_scale_span), drawable_h / max(real_span_y, min_scale_span))
    route_w = real_span_x * scale
    route_h = real_span_y * scale
    offset_x = (width - reserve_right - route_w) / 2
    offset_y = margin_top + (drawable_h - route_h) / 2

    raw_points = [
        {
            **stop,
            "x": offset_x + (stop["_mx"] - min_x) * scale,
            "y": offset_y + (stop["_my"] - min_y) * scale,
        }
        for stop in projected
    ]
    return _spread_close_points(raw_points, width=width, height=height)


def _spread_close_points(
    points: list[dict[str, Any]],
    *,
    width: int,
    height: int,
) -> list[dict[str, Any]]:
    if len(points) < 2:
        return points
    min_distance = max(30.0, min(width, height) * 0.032)
    left = 42.0
    right = width - 42.0
    top = max(190.0, height * 0.12)
    bottom = height - 58.0
    mutable_points = [
        {
            **point,
            "x": float(point["x"]),
            "y": float(point["y"]),
        }
        for point in points
    ]
    for _ in range(8):
        moved = False
        for left_index in range(len(mutable_points)):
            for right_index in range(left_index + 1, len(mutable_points)):
                first = mutable_points[left_index]
                second = mutable_points[right_index]
                dx = float(second["x"]) - float(first["x"])
                dy = float(second["y"]) - float(first["y"])
                distance = math.hypot(dx, dy)
                if distance >= min_distance:
                    continue
                if distance < 0.001:
                    angle = (left_index * 1.618 + right_index * 0.932) * math.pi
                    dx = math.cos(angle)
                    dy = math.sin(angle)
                    distance = 1.0
                push = (min_distance - distance) / 2.0 + 0.2
                nx = dx / distance
                ny = dy / distance
                first_x = min(max(float(first["x"]) - nx * push, left), right)
                first_y = min(max(float(first["y"]) - ny * push, top), bottom)
                second_x = min(max(float(second["x"]) + nx * push, left), right)
                second_y = min(max(float(second["y"]) + ny * push, top), bottom)
                mutable_points[left_index] = {**first, "x": first_x, "y": first_y}
                mutable_points[right_index] = {**second, "x": second_x, "y": second_y}
                moved = True
        if not moved:
            break
    return mutable_points


def project_itinerary_points(
    plan: dict[str, Any],
    *,
    width: int = DEFAULT_CANVAS_WIDTH,
    height: int = DEFAULT_CANVAS_HEIGHT,
    reserve_right: float = 0.0,
) -> list[dict[str, Any]]:
    return _project_stops(
        [
            stop
            for stop in plan.get("stops", [])
            if isinstance(stop, dict) and stop.get("status") == "ok" and not _looks_like_instruction_stop(stop)
        ],
        width=width,
        height=height,
        reserve_right=reserve_right,
    )


def _svg_text(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _country_label_from_text(value: Any) -> str:
    folded = str(value or "").casefold()
    if not folded:
        return ""
    # Among all alias hits pick the LONGEST alias: plain first-match returned
    # 印度 for "Indiana, United States" ("india" ⊂ "indiana") and 韩国 for
    # "North Korea" ("korea" beats "north korea" by table order). ASCII aliases
    # additionally require word boundaries so substrings inside longer words
    # don't count at all.
    best_label = ""
    best_alias_len = 0
    for label, aliases in COUNTRY_LABEL_ALIASES:
        for alias in aliases:
            alias_folded = alias.casefold()
            if alias_folded.isascii():
                if not re.search(rf"\b{re.escape(alias_folded)}\b", folded):
                    continue
            elif alias_folded not in folded:
                continue
            if len(alias_folded) > best_alias_len:
                best_alias_len = len(alias_folded)
                best_label = label
    return best_label


def _country_label_from_coordinates(lat: float | None, lng: float | None) -> str:
    if not _valid_lat_lng(lat, lng):
        return ""
    assert lat is not None
    assert lng is not None
    # Bounding boxes overlap at borders, so first-match-wins mislabels border cities
    # (Nice→Italy, Como→Switzerland). Among every box that contains the point, pick the
    # one whose center is nearest. NOTE: this is still box-based, not polygon-based —
    # cities that sit deep inside a NEIGHBOUR's box (e.g. Turin, well within the France
    # box) resolve wrong by any box metric. The user's explicit country always takes
    # precedence in _country_label_for_stop, which is the reliable path for such stops.
    best_label = ""
    best_distance = float("inf")
    for label, min_lat, max_lat, min_lng, max_lng in COUNTRY_BOUNDING_BOXES:
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
            center_lat = (min_lat + max_lat) / 2.0
            center_lng = (min_lng + max_lng) / 2.0
            distance = (lat - center_lat) ** 2 + (lng - center_lng) ** 2
            if distance < best_distance:
                best_distance = distance
                best_label = label
    return best_label


def _is_composite_country_label(value: str) -> bool:
    return any(separator in value for separator in ("/", "／", "、", ",", "，", "&", "和"))


def _country_label_for_stop(stop: dict[str, Any]) -> str:
    explicit = _clean_text(stop.get("country"), limit=48)
    if explicit and not _is_composite_country_label(explicit):
        return _country_label_from_text(explicit) or explicit
    coordinate_label = _country_label_from_coordinates(_float_or_none(stop.get("lat")), _float_or_none(stop.get("lng")))
    if coordinate_label:
        return coordinate_label
    text_label = _country_label_from_text(
        " ".join(
            str(stop.get(key) or "")
            for key in ("name", "label", "note", "geocoded_name", "geocoded_address", "address")
        )
    )
    if text_label:
        return text_label
    return ""


def _country_label_candidates(
    x: float,
    y: float,
    *,
    width: int,
    height: int,
    route_center: tuple[float, float],
) -> list[tuple[float, float]]:
    vector_x = x - route_center[0]
    vector_y = y - route_center[1]
    norm = math.hypot(vector_x, vector_y)
    if norm < 1:
        vector_x = 1.0
        vector_y = -0.35
        norm = math.hypot(vector_x, vector_y)
    outward_x = vector_x / norm
    outward_y = vector_y / norm
    offset = max(70.0, min(width, height) * 0.078)
    return [
        (x - outward_x * offset * 1.05, y - outward_y * offset * 1.05),
        ((x + route_center[0]) / 2.0, (y + route_center[1]) / 2.0),
        (x + outward_x * offset * 1.25, y + outward_y * offset * 1.25),
        (x + outward_x * offset * 1.85, y + outward_y * offset * 1.85),
        (x - outward_y * offset * 0.85, y + outward_x * offset * 0.85),
        (x + outward_y * offset * 0.85, y - outward_x * offset * 0.85),
        (x, y - offset),
        (x, y + offset),
        (x - offset, y),
        (x + offset, y),
    ]


def _country_label_nodes(
    points: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    has_logo: bool,
    avoid_boxes: list[tuple[float, float, float, float]] | None = None,
) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        label = _country_label_for_stop(point)
        if not label:
            continue
        grouped.setdefault(label, []).append(point)
    if not grouped:
        return []

    route_center = (
        sum(float(point["x"]) for point in points) / max(1, len(points)),
        sum(float(point["y"]) for point in points) / max(1, len(points)),
    )
    occupied: list[tuple[float, float, float, float]] = [
        (width * 0.5 - 380.0, 38.0, width * 0.5 + 380.0, 192.0),
    ]
    if has_logo:
        occupied.append((46.0, 44.0, min(392.0, width * 0.34), 182.0))
    # The callout scrolls were placed moments earlier by an independent pass;
    # without their boxes here, big country names routinely land half-buried
    # under a date/name scroll.
    occupied.extend(avoid_boxes or [])
    point_pad_x = max(120.0, width * 0.07)
    point_pad_y = max(58.0, height * 0.038)
    for point in points:
        x = float(point["x"])
        y = float(point["y"])
        occupied.append((x - point_pad_x, y - point_pad_y, x + point_pad_x, y + point_pad_y))

    nodes: list[str] = []
    for label, label_points in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        centroid_x = sum(float(point["x"]) for point in label_points) / len(label_points)
        centroid_y = sum(float(point["y"]) for point in label_points) / len(label_points)
        font_size = 42.0 if len(label_points) >= 3 else 34.0
        box_w = _estimated_country_label_width(label, font_size)
        box_h = font_size * 1.25
        best: tuple[float, float, tuple[float, float, float, float]] | None = None
        best_score = float("inf")
        for candidate_x, candidate_y in _country_label_candidates(
            centroid_x,
            centroid_y,
            width=width,
            height=height,
            route_center=route_center,
        ):
            side_margin = max(92.0, width * 0.105)
            x = min(max(candidate_x, box_w / 2 + side_margin), width - box_w / 2 - side_margin)
            y = min(max(candidate_y, height * 0.22), height - 86.0)
            box = (x - box_w / 2, y - box_h, x + box_w / 2, y + box_h * 0.24)
            overlap = sum(_overlap_area(box, existing) for existing in occupied)
            distance = math.hypot(x - centroid_x, y - centroid_y)
            edge_clearance = min(box[0], width - box[2], box[1], height - box[3])
            edge_penalty = max(0.0, 92.0 - edge_clearance) * 8.0
            score = overlap * 18.0 + distance + edge_penalty
            if score < best_score:
                best_score = score
                best = (x, y, box)
        if best is None:
            continue
        x, y, box = best
        occupied.append(box)
        nodes.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
            f'class="country-label{" small" if font_size < 40 else ""}">{_svg_text(label)}</text>'
        )
    return nodes


def _estimated_country_label_width(label: str, font_size: float) -> float:
    width = 0.0
    for char in label:
        width += font_size * (1.22 if "\u4e00" <= char <= "\u9fff" else 0.68)
    return max(118.0, width + font_size * 1.1)


def _route_path(points: list[dict[str, Any]]) -> str:
    if not points:
        return ""
    commands = [f"M {points[0]['x']:.1f} {points[0]['y']:.1f}"]
    if len(points) == 2:
        first = points[0]
        second = points[1]
        dx = float(second["x"]) - float(first["x"])
        dy = float(second["y"]) - float(first["y"])
        distance = math.hypot(dx, dy) or 1.0
        bend = min(80.0, distance * 0.18)
        nx = -dy / distance
        ny = dx / distance
        c1x = float(first["x"]) + dx * 0.34 + nx * bend
        c1y = float(first["y"]) + dy * 0.34 + ny * bend
        c2x = float(first["x"]) + dx * 0.66 + nx * bend
        c2y = float(first["y"]) + dy * 0.66 + ny * bend
        commands.append(f"C {c1x:.1f} {c1y:.1f} {c2x:.1f} {c2y:.1f} {second['x']:.1f} {second['y']:.1f}")
        return " ".join(commands)

    tension = 0.72
    for index in range(len(points) - 1):
        p0 = points[max(0, index - 1)]
        p1 = points[index]
        p2 = points[index + 1]
        p3 = points[min(len(points) - 1, index + 2)]
        c1x = float(p1["x"]) + (float(p2["x"]) - float(p0["x"])) * tension / 6.0
        c1y = float(p1["y"]) + (float(p2["y"]) - float(p0["y"])) * tension / 6.0
        c2x = float(p2["x"]) - (float(p3["x"]) - float(p1["x"])) * tension / 6.0
        c2y = float(p2["y"]) - (float(p3["y"]) - float(p1["y"])) * tension / 6.0
        commands.append(f"C {c1x:.1f} {c1y:.1f} {c2x:.1f} {c2y:.1f} {p2['x']:.1f} {p2['y']:.1f}")
    return " ".join(commands)


def _is_transfer_segment(
    start: dict[str, Any],
    end: dict[str, Any],
    *,
    distance: float,
    median_distance: float,
) -> bool:
    transport_text = f"{start.get('transport') or ''} {end.get('transport') or ''}"
    transfer_terms = ("飞", "航", "转机", "飞机", "flight", "airport")
    if any(term.casefold() in transport_text.casefold() for term in transfer_terms):
        return True
    return distance > max(360.0, median_distance * 3.2)


def _curved_segment_path(
    start: dict[str, Any],
    end: dict[str, Any],
    *,
    index: int,
    width: int,
    height: int,
) -> str:
    sx = float(start["x"])
    sy = float(start["y"])
    ex = float(end["x"])
    ey = float(end["y"])
    dx = ex - sx
    dy = ey - sy
    distance = math.hypot(dx, dy) or 1.0
    normal_x = -dy / distance
    normal_y = dx / distance
    mid_x = (sx + ex) / 2.0
    mid_y = (sy + ey) / 2.0
    center_x = width / 2.0
    center_y = height / 2.0
    outward = 1.0 if (mid_x - center_x) * normal_x + (mid_y - center_y) * normal_y >= 0 else -1.0
    if abs((mid_x - center_x) * normal_x + (mid_y - center_y) * normal_y) < 1:
        outward = 1.0 if index % 2 == 0 else -1.0
    bend = min(max(distance * 0.22, 42.0), 168.0) * outward
    c1x = sx + dx * 0.32 + normal_x * bend
    c1y = sy + dy * 0.32 + normal_y * bend
    c2x = sx + dx * 0.68 + normal_x * bend
    c2y = sy + dy * 0.68 + normal_y * bend
    return f"M {sx:.1f} {sy:.1f} C {c1x:.1f} {c1y:.1f} {c2x:.1f} {c2y:.1f} {ex:.1f} {ey:.1f}"


def _route_segments(points: list[dict[str, Any]], *, width: int, height: int) -> list[dict[str, Any]]:
    if len(points) < 2:
        return []
    distances = [
        math.hypot(float(points[index + 1]["x"]) - float(point["x"]), float(points[index + 1]["y"]) - float(point["y"]))
        for index, point in enumerate(points[:-1])
    ]
    sorted_distances = sorted(distances)
    median_distance = sorted_distances[len(sorted_distances) // 2] if sorted_distances else 0.0
    segments: list[dict[str, Any]] = []
    for index, point in enumerate(points[:-1]):
        next_point = points[index + 1]
        distance = distances[index]
        segments.append(
            {
                "path": _curved_segment_path(point, next_point, index=index, width=width, height=height),
                "transfer": _is_transfer_segment(point, next_point, distance=distance, median_distance=median_distance),
                "start": point,
                "end": next_point,
            }
        )
    return segments


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _encode_rgb_png(width: int, height: int, pixels: bytearray) -> bytes:
    rows = bytearray()
    stride = width * 3
    for y in range(height):
        rows.append(0)
        start = y * stride
        rows.extend(pixels[start : start + stride])
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(bytes(rows), level=6)),
            _png_chunk(b"IEND", b""),
        ]
    )


def _set_pixel(pixels: bytearray, width: int, height: int, x: int, y: int, color: RGBColor) -> None:
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    offset = (y * width + x) * 3
    pixels[offset] = color[0]
    pixels[offset + 1] = color[1]
    pixels[offset + 2] = color[2]


def _draw_circle(
    pixels: bytearray,
    width: int,
    height: int,
    cx: float,
    cy: float,
    radius: float,
    color: RGBColor,
) -> None:
    min_x = max(0, int(cx - radius - 1))
    max_x = min(width - 1, int(cx + radius + 1))
    min_y = max(0, int(cy - radius - 1))
    max_y = min(height - 1, int(cy + radius + 1))
    radius_sq = radius * radius
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= radius_sq:
                _set_pixel(pixels, width, height, x, y, color)


def _draw_line(
    pixels: bytearray,
    width: int,
    height: int,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    radius: float,
    color: RGBColor,
) -> None:
    steps = max(1, int(math.hypot(x2 - x1, y2 - y1) * 1.15))
    for step in range(steps + 1):
        ratio = step / steps
        _draw_circle(
            pixels,
            width,
            height,
            x1 + (x2 - x1) * ratio,
            y1 + (y2 - y1) * ratio,
            radius,
            color,
        )


_DIGIT_FONT: dict[str, tuple[str, ...]] = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
}


def _fill_rect(
    pixels: bytearray,
    width: int,
    height: int,
    left: int,
    top: int,
    rect_width: int,
    rect_height: int,
    color: RGBColor,
) -> None:
    right = min(width, left + rect_width)
    bottom = min(height, top + rect_height)
    for y in range(max(0, top), bottom):
        for x in range(max(0, left), right):
            _set_pixel(pixels, width, height, x, y, color)


def _draw_digit_text(
    pixels: bytearray,
    width: int,
    height: int,
    text: str,
    center_x: float,
    center_y: float,
    *,
    scale: int,
    color: RGBColor,
) -> None:
    glyphs = [_DIGIT_FONT[char] for char in text if char in _DIGIT_FONT]
    if not glyphs:
        return
    glyph_width = 3 * scale
    gap = max(1, scale)
    total_width = len(glyphs) * glyph_width + (len(glyphs) - 1) * gap
    total_height = 5 * scale
    x = round(center_x - total_width / 2)
    y = round(center_y - total_height / 2)
    for glyph in glyphs:
        for row_index, row in enumerate(glyph):
            for col_index, value in enumerate(row):
                if value == "1":
                    _fill_rect(
                        pixels,
                        width,
                        height,
                        x + col_index * scale,
                        y + row_index * scale,
                        scale,
                        scale,
                        color,
                    )
        x += glyph_width + gap


def _cubic_point(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    inv = 1.0 - t
    x = inv**3 * p0[0] + 3 * inv * inv * t * p1[0] + 3 * inv * t * t * p2[0] + t**3 * p3[0]
    y = inv**3 * p0[1] + 3 * inv * inv * t * p1[1] + 3 * inv * t * t * p2[1] + t**3 * p3[1]
    return x, y


def _draw_curved_segment(
    pixels: bytearray,
    width: int,
    height: int,
    start: dict[str, Any],
    end: dict[str, Any],
    *,
    index: int,
    radius: float,
    color: RGBColor,
) -> None:
    sx = float(start["x"])
    sy = float(start["y"])
    ex = float(end["x"])
    ey = float(end["y"])
    dx = ex - sx
    dy = ey - sy
    distance = math.hypot(dx, dy) or 1.0
    normal_x = -dy / distance
    normal_y = dx / distance
    mid_x = (sx + ex) / 2.0
    mid_y = (sy + ey) / 2.0
    center_x = width / 2.0
    center_y = height / 2.0
    outward = 1.0 if (mid_x - center_x) * normal_x + (mid_y - center_y) * normal_y >= 0 else -1.0
    if abs((mid_x - center_x) * normal_x + (mid_y - center_y) * normal_y) < 1:
        outward = 1.0 if index % 2 == 0 else -1.0
    bend = min(max(distance * 0.22, 42.0), 168.0) * outward
    p0 = (sx, sy)
    p1 = (sx + dx * 0.32 + normal_x * bend, sy + dy * 0.32 + normal_y * bend)
    p2 = (sx + dx * 0.68 + normal_x * bend, sy + dy * 0.68 + normal_y * bend)
    p3 = (ex, ey)
    previous = p0
    steps = max(8, int(distance / 7.0))
    for step in range(1, steps + 1):
        point = _cubic_point(p0, p1, p2, p3, step / steps)
        _draw_line(pixels, width, height, previous[0], previous[1], point[0], point[1], radius=radius, color=color)
        previous = point


def render_itinerary_control_png(
    plan: dict[str, Any],
    *,
    width: int = DEFAULT_CANVAS_WIDTH,
    height: int = DEFAULT_CANVAS_HEIGHT,
) -> bytes:
    points = project_itinerary_points(plan, width=width, height=height)
    if len(points) < 2:
        raise ValueError("至少需要两个带坐标的地点才能渲染路线图")

    bg: RGBColor = (249, 244, 229)
    land: RGBColor = (235, 216, 145)
    route_shadow: RGBColor = (255, 246, 224)
    route: RGBColor = (168, 95, 75)
    dot: RGBColor = (33, 43, 54)
    marker_fill: RGBColor = (255, 247, 198)
    logo_hint: RGBColor = (236, 232, 214)
    # bytes(bg) * n repeats at the C level; bg * n would first build a 3*n-element
    # pointer tuple (~77 MB at 1792², ~400 MB at 4096²) before the bytearray copy.
    pixels = bytearray(bytes(bg) * (width * height))

    safe_w = max(220, int(width * 0.18))
    safe_h = max(90, int(height * 0.09))
    _fill_rect(pixels, width, height, 44, 44, safe_w, safe_h, logo_hint)

    min_x = max(0, int(min(float(point["x"]) for point in points) - width * 0.12))
    max_x = min(width - 1, int(max(float(point["x"]) for point in points) + width * 0.12))
    min_y = max(0, int(min(float(point["y"]) for point in points) - height * 0.10))
    max_y = min(height - 1, int(max(float(point["y"]) for point in points) + height * 0.10))
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if ((x - (min_x + max_x) / 2.0) / max(1, (max_x - min_x) / 2.0)) ** 2 + (
                (y - (min_y + max_y) / 2.0) / max(1, (max_y - min_y) / 2.0)
            ) ** 2 <= 1.04:
                _set_pixel(pixels, width, height, x, y, land)

    for index, point in enumerate(points[:-1]):
        _draw_curved_segment(
            pixels,
            width,
            height,
            point,
            points[index + 1],
            index=index,
            radius=6.5,
            color=route_shadow,
        )
    for index, point in enumerate(points[:-1]):
        _draw_curved_segment(
            pixels,
            width,
            height,
            point,
            points[index + 1],
            index=index,
            radius=2.8,
            color=route,
        )
    marker_radius = max(10.0, min(16.0, width * 0.0086))
    digit_scale = max(2, round(marker_radius / 6.0))
    for index, point in enumerate(points, start=1):
        point_x = float(point["x"])
        point_y = float(point["y"])
        _draw_circle(pixels, width, height, point_x, point_y, marker_radius + 7.0, route_shadow)
        _draw_circle(pixels, width, height, point_x, point_y, marker_radius + 3.0, route)
        _draw_circle(pixels, width, height, point_x, point_y, marker_radius, marker_fill)
        _draw_digit_text(
            pixels,
            width,
            height,
            f"{index:02d}",
            point_x,
            point_y,
            scale=digit_scale,
            color=dot,
        )
    return _encode_rgb_png(width, height, pixels)


def _short_text(value: Any, *, limit: int) -> str:
    text = _clean_text(value, limit=limit + 1)
    if len(text) <= limit:
        return text
    return f"{text[: max(1, limit - 1)]}…"


def _overlap_area(box: tuple[float, float, float, float], other: tuple[float, float, float, float]) -> float:
    left = max(box[0], other[0])
    top = max(box[1], other[1])
    right = min(box[2], other[2])
    bottom = min(box[3], other[3])
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def _dense_index_labels(points: list[dict[str, Any]], *, width: int, height: int) -> list[str]:
    occupied: list[tuple[float, float, float, float]] = []
    nodes: list[str] = []
    candidates = (
        (-34.0, -34.0),
        (34.0, -34.0),
        (-34.0, 34.0),
        (34.0, 34.0),
        (0.0, -44.0),
        (0.0, 44.0),
        (-50.0, 0.0),
        (50.0, 0.0),
        (-58.0, -18.0),
        (58.0, -18.0),
        (-58.0, 18.0),
        (58.0, 18.0),
    )
    badge_w = 34.0
    badge_h = 28.0
    for index, point in enumerate(points):
        x = float(point["x"])
        y = float(point["y"])
        best: tuple[float, float, tuple[float, float, float, float]] | None = None
        best_score = float("inf")
        for dx, dy in candidates:
            cx = min(max(x + dx, 40.0), width - 480.0)
            cy = min(max(y + dy, 184.0), height - 60.0)
            box = (cx - badge_w / 2, cy - badge_h / 2, cx + badge_w / 2, cy + badge_h / 2)
            overlap = sum(_overlap_area(box, item) for item in occupied)
            distance = abs(dx) + abs(dy)
            score = overlap * 100.0 + distance
            if score < best_score:
                best_score = score
                best = (cx, cy, box)
        if best is None:
            continue
        cx, cy, box = best
        occupied.append(box)
        leader = ""
        if abs(cx - x) + abs(cy - y) > 34:
            leader = f'<line x1="{x - cx:.1f}" y1="{y - cy:.1f}" x2="0" y2="0" class="map-index-leader"/>'
        nodes.append(
            f'<g class="map-index-badge" transform="translate({cx:.1f} {cy:.1f})">'
            f"{leader}"
            '<circle cx="0" cy="0" r="15" fill="#fff7c7" opacity="0.96"/>'
            '<circle cx="0" cy="0" r="13" fill="none" stroke="#7f5f45" stroke-width="1.35"/>'
            f'<text x="0" y="6" text-anchor="middle" class="map-index">{index + 1}</text>'
            "</g>"
        )
    return nodes


def _label_candidate_centers(
    index: int,
    point: dict[str, Any],
    *,
    width: int,
    height: int,
    route_center: tuple[float, float],
) -> list[tuple[float, float]]:
    x = float(point["x"])
    y = float(point["y"])
    horizontal = max(150.0, min(255.0, width * 0.12))
    vertical = max(78.0, min(138.0, height * 0.095))
    vector_x = x - route_center[0]
    vector_y = y - route_center[1]
    norm = math.hypot(vector_x, vector_y)
    if norm < 1:
        vector_x = -1.0 if index % 2 else 1.0
        vector_y = -0.45 if index % 3 else 0.45
        norm = math.hypot(vector_x, vector_y)
    outward_x = vector_x / norm
    outward_y = vector_y / norm
    tangent_x = -outward_y
    tangent_y = outward_x
    preferred_side = 1.0
    if x > width * 0.64:
        preferred_side = -1.0
    elif x > width * 0.36:
        preferred_side = 1.0 if index % 2 == 0 else -1.0

    candidates = [
        (x + outward_x * horizontal * 1.15, y + outward_y * vertical * 1.15),
        (
            x + outward_x * horizontal * 1.25 + tangent_x * 72.0,
            y + outward_y * vertical * 1.25 + tangent_y * 72.0,
        ),
        (
            x + outward_x * horizontal * 1.25 - tangent_x * 72.0,
            y + outward_y * vertical * 1.25 - tangent_y * 72.0,
        ),
        (x + preferred_side * horizontal, y - vertical),
        (x + preferred_side * horizontal, y + vertical),
        (x - preferred_side * horizontal, y - vertical),
        (x - preferred_side * horizontal, y + vertical),
        (x, y - vertical * 1.45),
        (x, y + vertical * 1.45),
        (x + preferred_side * horizontal * 1.22, y),
        (x - preferred_side * horizontal * 1.22, y),
        (x + preferred_side * horizontal * 1.55, y - vertical * 0.25),
        (x - preferred_side * horizontal * 1.55, y + vertical * 0.25),
    ]
    if height < 1200:
        candidates.extend(
            [
                (x + preferred_side * horizontal * 1.48, y - vertical * 0.45),
                (x - preferred_side * horizontal * 1.48, y + vertical * 0.45),
            ]
        )
    return candidates


def _clamp_label_box(
    cx: float,
    cy: float,
    *,
    width: int,
    height: int,
    label_w: float,
    label_h: float,
) -> tuple[float, float, tuple[float, float, float, float]]:
    left_limit = 42.0
    right_limit = width - 42.0 - label_w
    top_limit = max(142.0, height * 0.12)
    bottom_limit = height - 48.0 - label_h
    x = min(max(cx - label_w / 2.0, left_limit), right_limit)
    y = min(max(cy - label_h / 2.0, top_limit), bottom_limit)
    return x, y, (x, y, x + label_w, y + label_h)


def _box_anchor(point: dict[str, Any], box: tuple[float, float, float, float]) -> tuple[float, float]:
    x = float(point["x"])
    y = float(point["y"])
    anchor_x = min(max(x, box[0]), box[2])
    anchor_y = min(max(y, box[1]), box[3])
    if box[0] < x < box[2] and box[1] < y < box[3]:
        distances = {
            "left": abs(x - box[0]),
            "right": abs(box[2] - x),
            "top": abs(y - box[1]),
            "bottom": abs(box[3] - y),
        }
        side = min(distances, key=lambda name: distances[name])
        if side == "left":
            anchor_x = box[0]
        elif side == "right":
            anchor_x = box[2]
        elif side == "top":
            anchor_y = box[1]
        else:
            anchor_y = box[3]
    return anchor_x, anchor_y


def _callout_scroll_path(x: float, y: float, w: float, h: float) -> str:
    notch = min(18.0, h * 0.34)
    return (
        f"M {x + notch:.1f} {y:.1f} "
        f"C {x + 7:.1f} {y + 2:.1f} {x + 2:.1f} {y + 10:.1f} {x:.1f} {y + h / 2:.1f} "
        f"C {x + 2:.1f} {y + h - 10:.1f} {x + 8:.1f} {y + h - 2:.1f} {x + notch:.1f} {y + h:.1f} "
        f"L {x + w - notch:.1f} {y + h:.1f} "
        f"C {x + w - 8:.1f} {y + h - 2:.1f} {x + w - 2:.1f} {y + h - 10:.1f} "
        f"{x + w:.1f} {y + h / 2:.1f} "
        f"C {x + w - 2:.1f} {y + 10:.1f} {x + w - 7:.1f} {y + 2:.1f} {x + w - notch:.1f} {y:.1f} "
        "Z"
    )


def _callout_labels(
    points: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    has_logo: bool,
) -> tuple[list[str], list[tuple[float, float, float, float]]]:
    """Return the callout SVG nodes AND the boxes they occupy, so later layout
    passes (country labels) can avoid drawing underneath them."""

    dense_layout = len(points) > 12
    min_label_w = 186.0 if dense_layout else 154.0
    max_label_w = 242.0 if dense_layout else 216.0
    label_w = max(min_label_w, min(max_label_w, width * (0.18 if dense_layout else 0.13)))
    label_h = 50.0 if dense_layout and height >= 1200 else (54.0 if height >= 1200 else 50.0)
    route_center = (
        sum(float(point["x"]) for point in points) / max(1, len(points)),
        sum(float(point["y"]) for point in points) / max(1, len(points)),
    )
    occupied: list[tuple[float, float, float, float]] = [
        (width * 0.5 - 360.0, 42.0, width * 0.5 + 360.0, 190.0),
    ]
    if has_logo:
        occupied.append((46.0, 46.0, min(390.0, width * 0.34), 178.0))
    # Keep scrolls off the numbered route dots of OTHER stops — without these
    # pads a callout can sit right on top of a neighbouring marker (visible on
    # dense multi-country routes in production).
    dot_pad = 34.0
    for point in points:
        px, py = float(point["x"]), float(point["y"])
        occupied.append((px - dot_pad, py - dot_pad, px + dot_pad, py + dot_pad))

    nodes: list[str] = []
    callout_boxes: list[tuple[float, float, float, float]] = []
    for index, point in enumerate(points):
        best: tuple[float, float, tuple[float, float, float, float]] | None = None
        best_score = float("inf")
        for cx, cy in _label_candidate_centers(
            index,
            point,
            width=width,
            height=height,
            route_center=route_center,
        ):
            label_x, label_y, box = _clamp_label_box(
                cx, cy, width=width, height=height, label_w=label_w, label_h=label_h
            )
            overlap = sum(_overlap_area(box, existing) for existing in occupied)
            distance = math.hypot(
                (box[0] + box[2]) / 2.0 - float(point["x"]), (box[1] + box[3]) / 2.0 - float(point["y"])
            )
            route_penalty = (
                280.0 if box[0] <= float(point["x"]) <= box[2] and box[1] <= float(point["y"]) <= box[3] else 0.0
            )
            score = overlap * 26.0 + distance + route_penalty
            if score < best_score:
                best_score = score
                best = (label_x, label_y, box)
        if best is None:
            continue

        label_x, label_y, box = best
        occupied.append(box)
        callout_boxes.append(box)
        anchor_x, anchor_y = _box_anchor(point, box)
        # limit=10 keeps a full ISO date ("2026-07-07") intact — 7 mangled it
        # into "2026-0…" despite the recipe promising complete dates. Overlong
        # captions are compressed to the scroll width via textLength below.
        date = _svg_text(_short_text(point.get("date"), limit=10))
        name = _svg_text(_short_text(point.get("name"), limit=12 if dense_layout else 10))
        transport = _svg_text(_short_text(point.get("transport"), limit=8))
        caption = f"{date}  {name}" if date else name
        scroll_path = _callout_scroll_path(label_x, label_y, label_w, label_h)
        transport_y = label_y + (43.0 if label_h <= 52 else 46.0)
        caption_fit = (
            f' textLength="{label_w - 54.0:.1f}" lengthAdjust="spacingAndGlyphs"'
            if len(caption) >= (12 if dense_layout else 10)
            else ""
        )
        transport_node = (
            f'<text x="{label_x + 39:.1f}" y="{transport_y:.1f}" class="callout-transport">{transport}</text>'
            if transport
            else ""
        )
        nodes.append(
            '<g class="map-callout">'
            f'<path d="M {float(point["x"]):.1f} {float(point["y"]):.1f} '
            f"C {(float(point['x']) + anchor_x) / 2:.1f} {float(point['y']):.1f} "
            f'{anchor_x:.1f} {(float(point["y"]) + anchor_y) / 2:.1f} {anchor_x:.1f} {anchor_y:.1f}" '
            'class="callout-leader"/>'
            f'<path d="{scroll_path}" class="callout-scroll"/>'
            f'<circle cx="{label_x + 21:.1f}" cy="{label_y + label_h / 2:.1f}" r="12" class="callout-chip"/>'
            f'<text x="{label_x + 21:.1f}" y="{label_y + label_h / 2 + 5.0:.1f}" text-anchor="middle" '
            f'class="callout-index">{index + 1}</text>'
            f'<text x="{label_x + 39:.1f}" y="{label_y + 25:.1f}" '
            f'class="callout-main"{caption_fit}>{caption}</text>'
            f"{transport_node}"
            "</g>"
        )
    return nodes, callout_boxes


def _poster_land_path(points: list[dict[str, Any]], *, width: int, height: int) -> str:
    min_x = min(float(point["x"]) for point in points)
    max_x = max(float(point["x"]) for point in points)
    min_y = min(float(point["y"]) for point in points)
    max_y = max(float(point["y"]) for point in points)
    pad_x = max(190.0, width * 0.14)
    pad_y = max(150.0, height * 0.13)
    left = max(44.0, min_x - pad_x)
    right = min(width - 44.0, max_x + pad_x)
    top = max(height * 0.16, min_y - pad_y)
    bottom = min(height - 54.0, max_y + pad_y)
    if right - left < width * 0.55:
        expand = (width * 0.55 - (right - left)) / 2.0
        left = max(44.0, left - expand)
        right = min(width - 44.0, right + expand)
    if bottom - top < height * 0.48:
        expand = (height * 0.48 - (bottom - top)) / 2.0
        top = max(height * 0.16, top - expand)
        bottom = min(height - 54.0, bottom + expand)
    mid_x = (left + right) / 2.0
    mid_y = (top + bottom) / 2.0
    return (
        f"M {left + 34:.1f} {top + 42:.1f} "
        f"C {mid_x - (right - left) * 0.36:.1f} {top - 24:.1f}, "
        f"{mid_x + (right - left) * 0.12:.1f} {top + 10:.1f}, "
        f"{right - 46:.1f} {top + 64:.1f} "
        f"C {right + 28:.1f} {mid_y - (bottom - top) * 0.18:.1f}, "
        f"{right - 22:.1f} {mid_y + (bottom - top) * 0.22:.1f}, "
        f"{right - 82:.1f} {bottom - 38:.1f} "
        f"C {mid_x + (right - left) * 0.22:.1f} {bottom + 34:.1f}, "
        f"{mid_x - (right - left) * 0.25:.1f} {bottom - 2:.1f}, "
        f"{left + 72:.1f} {bottom - 70:.1f} "
        f"C {left - 26:.1f} {mid_y + (bottom - top) * 0.18:.1f}, "
        f"{left + 16:.1f} {mid_y - (bottom - top) * 0.28:.1f}, "
        f"{left + 34:.1f} {top + 42:.1f} Z"
    )


def _decorative_doodles(points: list[dict[str, Any]], *, width: int, height: int) -> list[str]:
    min_x = min(float(point["x"]) for point in points)
    max_x = max(float(point["x"]) for point in points)
    min_y = min(float(point["y"]) for point in points)
    max_y = max(float(point["y"]) for point in points)
    doodles: list[str] = ['<g data-layer="program-map-illustration" opacity="0.72">']
    anchors = [
        (min_x - 120.0, min_y + 88.0, "tree"),
        (max_x + 92.0, min_y + 130.0, "mountain"),
        ((min_x + max_x) / 2.0 - 140.0, (min_y + max_y) / 2.0 - 42.0, "town"),
        (min_x + 98.0, max_y + 102.0, "tree"),
        (max_x - 110.0, max_y + 92.0, "mountain"),
    ]
    for index, (raw_x, raw_y, kind) in enumerate(anchors):
        x = min(max(raw_x, 76.0), width - 150.0)
        y = min(max(raw_y, height * 0.2), height - 112.0)
        if kind == "mountain":
            doodles.append(
                f'<g class="doodle-mountain" transform="translate({x:.1f} {y:.1f})">'
                '<path d="M0 54 L42 0 L84 54 Z" class="doodle-fill"/>'
                '<path d="M42 0 L54 54 M42 0 L28 54" class="doodle-line"/>'
                '<path d="M74 54 L112 14 L150 54 Z" class="doodle-fill alt"/>'
                '<path d="M112 14 L122 54 M112 14 L100 54" class="doodle-line"/>'
                "</g>"
            )
        elif kind == "town":
            doodles.append(
                f'<g class="doodle-town" transform="translate({x:.1f} {y:.1f})">'
                '<path d="M0 58 H136 M8 58 V20 H46 V58 M56 58 V8 H104 V58 M112 58 V30 H132 V58" class="doodle-line"/>'
                '<path d="M56 8 L80 -10 L104 8 M8 20 L27 4 L46 20 M112 30 L122 18 L132 30" class="doodle-line"/>'
                '<circle cx="80" cy="24" r="7" class="doodle-dot"/>'
                "</g>"
            )
        else:
            doodles.append(
                f'<g class="doodle-tree" transform="translate({x:.1f} {y:.1f}) rotate({-8 if index % 2 else 7})">'
                '<path d="M38 72 V36" class="doodle-line"/>'
                '<path d="M38 38 C10 24 18 -4 42 10 C56 -12 88 2 76 30 '
                'C96 40 78 68 50 56 C40 76 10 62 22 42 C28 36 32 34 38 38 Z" '
                'class="doodle-fill green"/>'
                '<path d="M38 40 C30 48 26 56 18 62 M42 42 C56 44 66 50 76 60" class="doodle-line"/>'
                "</g>"
            )
    doodles.append("</g>")
    return doodles


def render_itinerary_map_svg(
    plan: dict[str, Any],
    *,
    width: int = DEFAULT_CANVAS_WIDTH,
    height: int = DEFAULT_CANVAS_HEIGHT,
    background_image_url: str = "",
    logo_href: str = "",
    reserve_logo_area: bool | None = None,
) -> str:
    reserve_logo = bool(logo_href) if reserve_logo_area is None else reserve_logo_area
    clean_stops = [
        stop for stop in plan.get("stops", []) if isinstance(stop, dict) and not _looks_like_instruction_stop(stop)
    ]
    dense_layout = len(clean_stops) > 12
    points = project_itinerary_points({"stops": clean_stops}, width=width, height=height)
    if len(points) < 2:
        raise ValueError("至少需要两个带坐标的地点才能渲染路线图")

    route_path = _route_path(points)
    route_segments = _route_segments(points, width=width, height=height)
    route_casing_nodes = [
        f'<path d="{segment["path"]}" class="route-casing{" transfer" if segment["transfer"] else ""}"/>'
        for segment in route_segments
    ]
    route_line_nodes = [
        f'<path d="{segment["path"]}" class="route-line{" transfer" if segment["transfer"] else ""}"/>'
        for segment in route_segments
    ]
    title = _svg_text(plan.get("title") or "定制旅行路线图")
    subtitle = _svg_text(plan.get("subtitle") or "")
    safe_background_url = (
        background_image_url
        if background_image_url.startswith(
            (
                "data:image/png;base64,",
                "data:image/jpeg;base64,",
                "data:image/jpg;base64,",
                "data:image/webp;base64,",
            )
        )
        else ""
    )
    land_path = _poster_land_path(points, width=width, height=height)
    background = (
        # preserveAspectRatio="none": the AI paints terrain at the control
        # PNG's locked pixel coordinates, and the route/dots are drawn at those
        # exact coordinates. "slice" would crop a background whose aspect ratio
        # differs from the canvas (upstream size mismatches happen), shifting
        # every painted city away from its dot. Stretching keeps alignment.
        '<g data-layer="ai-stylized-map-background">'
        f'<image href="{_svg_text(safe_background_url)}" x="0" y="0" width="{width}" height="{height}" '
        'preserveAspectRatio="none" opacity="0.96"/>'
        "</g>"
        if safe_background_url
        else ""
    )
    poster_base_nodes = (
        []
        if safe_background_url
        else [
            '<g data-layer="program-poster-map-base" filter="url(#paperShadow)">',
            f'<path d="{land_path}" fill="url(#landWash)" stroke="#d4aa4a" stroke-width="10" '
            'stroke-linejoin="round" opacity=".86"/>',
            f'<path d="{land_path}" fill="none" stroke="#8e6a2d" stroke-width="3" '
            'stroke-linejoin="round" stroke-dasharray="14 12" opacity=".34"/>',
            "</g>",
            '<g data-layer="program-map-wash" opacity="0.46">',
            '<path d="M35 270 C330 110 530 220 740 116 C1040 -30 1255 172 1545 72 C1698 20 1810 56 1908 0" '
            'fill="none" stroke="#76b9d6" stroke-width="118" stroke-linecap="round" opacity=".24"/>',
            '<path d="M-20 1540 C250 1390 390 1548 680 1410 C1020 1250 1190 1360 '
            '1490 1220 C1680 1130 1790 1165 1880 1090" '
            'fill="none" stroke="#6db9d5" stroke-width="138" stroke-linecap="round" opacity=".22"/>',
            '<path d="M86 1160 C390 1010 600 1130 870 980 C1090 858 1280 875 1542 740" '
            'fill="none" stroke="#83ae72" stroke-width="92" stroke-linecap="round" opacity=".18"/>',
            "</g>",
        ]
    )

    stop_nodes: list[str] = []
    route_point_nodes: list[str] = []
    for index, point in enumerate(points):
        x = float(point["x"])
        y = float(point["y"])
        stop_nodes.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9.2" class="route-dot-halo"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.1" class="route-dot"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" class="route-dot-core"/>'
        )
        route_point_nodes.append(
            f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" class="route-dot-index">{index + 1}</text>'
        )
    label_nodes, callout_boxes = _callout_labels(points, width=width, height=height, has_logo=reserve_logo)
    country_nodes = _country_label_nodes(
        points,
        width=width,
        height=height,
        has_logo=reserve_logo,
        avoid_boxes=callout_boxes,
    )
    index_nodes = (
        _dense_index_labels(points, width=width, height=height)
        if dense_layout and len(points) > len(label_nodes)
        else []
    )
    doodle_nodes = [] if safe_background_url else _decorative_doodles(points, width=width, height=height)

    logo_group = (
        "\n".join(
            [
                '<g data-layer="program-logo">',
                f'<image href="{_svg_text(logo_href)}" x="72" y="62" width="260" preserveAspectRatio="xMinYMin meet"/>',
                "</g>",
            ]
        )
        if logo_href
        else ""
    )
    svg_open = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">'
    )
    title_font_face_css = _embedded_title_font_face_css() if safe_background_url else ""
    return "\n".join(
        [
            svg_open[:-1] + f' data-density="{"dense" if dense_layout else "normal"}">',
            "<defs>",
            '<linearGradient id="paper" x1="0" y1="0" x2="1" y2="1">',
            '<stop offset="0" stop-color="#fff7e8"/>',
            '<stop offset="0.55" stop-color="#eef4df"/>',
            '<stop offset="1" stop-color="#dff3f7"/>',
            "</linearGradient>",
            '<linearGradient id="landWash" x1="0" y1="0" x2="1" y2="1">',
            '<stop offset="0" stop-color="#f8d979"/>',
            '<stop offset="0.52" stop-color="#f2c966"/>',
            '<stop offset="1" stop-color="#eadf9c"/>',
            "</linearGradient>",
            '<linearGradient id="titleInk" x1="0" y1="0" x2="0" y2="1">',
            '<stop offset="0" stop-color="#1e140c"/>',
            '<stop offset="0.58" stop-color="#3f2614"/>',
            '<stop offset="1" stop-color="#6f401d"/>',
            "</linearGradient>",
            '<linearGradient id="titleGold" x1="0" y1="0" x2="1" y2="1">',
            '<stop offset="0" stop-color="#f4d58a"/>',
            '<stop offset="0.55" stop-color="#b9823f"/>',
            '<stop offset="1" stop-color="#6f451f"/>',
            "</linearGradient>",
            '<filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">',
            '<feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#5d3a16" flood-opacity="0.12"/>',
            "</filter>",
            '<filter id="titleCast" x="-20%" y="-35%" width="140%" height="170%">',
            '<feDropShadow dx="0" dy="5" stdDeviation="3" flood-color="#4b2d16" flood-opacity="0.28"/>',
            "</filter>",
            '<filter id="paperShadow" x="-18%" y="-18%" width="136%" height="136%">',
            '<feDropShadow dx="0" dy="10" stdDeviation="10" flood-color="#5d3a16" flood-opacity="0.12"/>',
            "</filter>",
            '<filter id="titleBrushRough" x="-8%" y="-35%" width="116%" height="175%">',
            '<feTurbulence type="fractalNoise" baseFrequency="0.012 0.055" numOctaves="2" seed="17" result="noise"/>',
            '<feDisplacementMap in="SourceGraphic" in2="noise" scale="1.05" '
            'xChannelSelector="R" yChannelSelector="G"/>',
            "</filter>",
            "<style>",
            title_font_face_css,
            ".title,.title-shadow,.title-brush,.title-gold-edge,.subtitle,.subtitle-glow{"
            f"font-family:'{TITLE_FONT_FAMILY}','ZCOOL XiaoWei','Noto Serif CJK SC',"
            "'Source Han Serif SC','Songti SC',serif;"
            "letter-spacing:0}",
            ".title-shadow{font-size:80px;font-weight:900;fill:#4b2d16;opacity:.18;filter:url(#titleCast)}",
            ".title-wash{fill:#f0d49a;fill-opacity:.34;stroke:#b9823f;stroke-width:1.1;opacity:.62}",
            ".title-brush{font-size:80px;font-weight:900;fill:none;stroke:#fff4d7;stroke-width:8.5;"
            "stroke-linejoin:round;stroke-linecap:round;paint-order:stroke;opacity:.92;filter:url(#titleBrushRough)}",
            ".title-gold-edge{font-size:80px;font-weight:900;fill:none;stroke:url(#titleGold);stroke-width:2.4;"
            "stroke-linejoin:round;stroke-linecap:round;opacity:.82;filter:url(#titleBrushRough)}",
            ".title{font-size:80px;font-weight:900;fill:url(#titleInk);paint-order:stroke;stroke:#2a1609;"
            "stroke-width:.55;stroke-linejoin:round;filter:url(#titleBrushRough)}",
            ".subtitle-glow{font-size:32px;font-weight:700;fill:none;stroke:#fff2d7;stroke-width:5;"
            "stroke-linejoin:round;opacity:.88}",
            ".subtitle{font-size:32px;font-weight:700;fill:#7a4c22;paint-order:stroke;stroke:#fff8e6;"
            "stroke-width:.9;stroke-linejoin:round}",
            ".title-ornament{fill:none;stroke:#9b6b35;stroke-width:1.7;stroke-linecap:round;opacity:.44}",
            ".country-label{font:760 46px system-ui,'PingFang SC','Microsoft YaHei',sans-serif;fill:#735b3e;"
            "opacity:.54;letter-spacing:0;paint-order:stroke;stroke:#fff7df;stroke-width:7px;stroke-linejoin:round;"
            "stroke-opacity:.72}",
            ".country-label.small{font-size:36px;opacity:.50}",
            ".route-dot-index{font:800 10px system-ui,'PingFang SC','Microsoft YaHei',sans-serif;fill:#ffffff}",
            ".map-index{font:800 15px system-ui,'PingFang SC','Microsoft YaHei',sans-serif;fill:#7f5f45}",
            ".map-index-leader{stroke:#7f5f45;stroke-width:1.05;stroke-linecap:round;opacity:.26}",
            ".callout-scroll{fill:#fff4df;fill-opacity:.60;stroke:#b99662;stroke-width:.85;opacity:.92}",
            ".callout-leader{fill:none;stroke:#735a42;stroke-width:.9;stroke-linecap:round;opacity:.24}",
            ".callout-chip{fill:#7f5f45;stroke:#fff7e7;stroke-width:2.2}",
            ".callout-index{font:800 14px system-ui,'PingFang SC','Microsoft YaHei',sans-serif;fill:#fff8e8}",
            ".callout-main{font:680 18px system-ui,'PingFang SC','Microsoft YaHei',sans-serif;"
            "fill:#2d251b;letter-spacing:0}",
            ".callout-transport{font:620 13px system-ui,'PingFang SC','Microsoft YaHei',sans-serif;"
            "fill:#735033;letter-spacing:0}",
            ".route-dot-halo{fill:#fff3d5;stroke:#ffffff;stroke-width:2.8;opacity:.88}",
            ".route-dot{fill:#7f5f45;stroke:#fff3d5;stroke-width:2.1}",
            ".route-dot-core{fill:#ffffff;opacity:.96}",
            ".route-casing{fill:none;stroke:#fff4dc;stroke-width:7.8;stroke-linecap:round;stroke-linejoin:round;opacity:.72}",
            ".route-line{fill:none;stroke:#7f5f45;stroke-width:3.8;stroke-linecap:round;stroke-linejoin:round}",
            ".route-casing.transfer{stroke-width:6.8;opacity:.66}",
            ".route-line.transfer{stroke-width:3.2;opacity:.62}",
            ".doodle-line{fill:none;stroke:#5f4020;stroke-width:5;stroke-linecap:round;stroke-linejoin:round;opacity:.76}",
            ".doodle-fill{fill:#e4b45b;stroke:#5f4020;stroke-width:4;stroke-linejoin:round;opacity:.62}",
            ".doodle-fill.alt{fill:#d8c978}",
            ".doodle-fill.green{fill:#7fb36b;opacity:.45}",
            ".doodle-dot{fill:#a73b28;opacity:.72}",
            "</style>",
            "</defs>",
            '<rect width="100%" height="100%" fill="url(#paper)"/>',
            background,
            *poster_base_nodes,
            *doodle_nodes,
            logo_group,
            '<g data-layer="program-title" text-anchor="middle">',
            f'<path d="M {width / 2 - 330:.0f} 88 C {width / 2 - 228:.0f} 66 '
            f'{width / 2 - 122:.0f} 76 {width / 2 - 18:.0f} 76 C '
            f'{width / 2 + 98:.0f} 77 {width / 2 + 216:.0f} 66 {width / 2 + 330:.0f} 90 '
            f'C {width / 2 + 206:.0f} 112 {width / 2 + 118:.0f} 105 {width / 2 + 4:.0f} 112 '
            f'C {width / 2 - 106:.0f} 118 {width / 2 - 222:.0f} 113 {width / 2 - 330:.0f} 88 Z" '
            'class="title-wash"/>',
            f'<text x="{width / 2 + 2:.0f}" y="122" class="title-shadow">{title}</text>',
            f'<text x="{width / 2:.0f}" y="118" class="title-brush">{title}</text>',
            f'<text x="{width / 2:.0f}" y="118" class="title-gold-edge">{title}</text>',
            f'<text x="{width / 2:.0f}" y="118" class="title">{title}</text>',
            f'<text x="{width / 2:.0f}" y="166" class="subtitle-glow">{subtitle}</text>',
            f'<text x="{width / 2:.0f}" y="166" class="subtitle">{subtitle}</text>',
            f'<path d="M {width / 2 - 172:.0f} 181 C {width / 2 - 112:.0f} 171 '
            f'{width / 2 - 66:.0f} 171 {width / 2 - 24:.0f} 181" class="title-ornament"/>',
            f'<path d="M {width / 2 + 24:.0f} 181 C {width / 2 + 66:.0f} 171 '
            f'{width / 2 + 112:.0f} 171 {width / 2 + 172:.0f} 181" class="title-ornament"/>',
            "</g>",
            '<g data-layer="program-route" filter="url(#softShadow)">',
            f"<!-- combined reference path: {route_path} -->",
            *route_casing_nodes,
            *route_line_nodes,
            *stop_nodes,
            *route_point_nodes,
            "</g>",
            '<g data-layer="program-country-labels">',
            *country_nodes,
            "</g>",
            '<g data-layer="program-index-labels">',
            *index_nodes,
            "</g>",
            '<g data-layer="program-labels">',
            *label_nodes,
            "</g>",
            "</svg>",
        ]
    )


def save_itinerary_map_svg(
    *,
    data_dir: Path,
    outputs_dir: Path,
    svg_text: str,
    metadata: dict[str, object],
    filename_prefix: str = "",
    width: int = DEFAULT_CANVAS_WIDTH,
    height: int = DEFAULT_CANVAS_HEIGHT,
) -> dict[str, object]:
    now = datetime.now()
    safe_prefix = sanitize_filename_prefix(filename_prefix)
    day_dir = output_group_dir(outputs_dir, now, safe_prefix)
    base_stem = f"itinerary-map-{now.strftime('%H%M%S')}-{uuid.uuid4().hex[:8]}"
    stem = f"{safe_prefix}-{base_stem}" if safe_prefix else base_stem
    image_path = day_dir / f"{stem}.svg"
    payload = svg_text.encode("utf-8")
    day_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=".svg", dir=str(day_dir))
    temporary_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        temporary_path.replace(image_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return {
        "saved_image_path": str(image_path),
        "saved_image_url": storage_url_for_path(data_dir, image_path),
        "saved_image_name": image_path.name,
        "saved_image_mime": SVG_MIME,
        "saved_image_width": width,
        "saved_image_height": height,
        "saved_image_bytes": len(payload),
        "saved_metadata_path": "",
        "saved_metadata_url": "",
        "metadata": {
            **metadata,
            "saved_image_width": width,
            "saved_image_height": height,
            "saved_image_bytes": len(payload),
            "final_overlay_policy": "program_points_routes_labels_logo_slot",
        },
    }

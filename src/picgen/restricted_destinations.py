from __future__ import annotations

import math
import re
from typing import Any

RESTRICTED_DESTINATION_CODE = "restricted_destination"
RESTRICTED_DESTINATION_ERROR = "请求包含受限目的地或受限地标，已按平台规则阻止。"

_RESTRICTED_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"梵\s*蒂\s*[冈岡]",
        r"vatican(?:\s+city)?",
        r"vaticano",
        r"holy\s+see",
        r"圣\s*座",
        r"羅馬\s*教廷",
        r"罗马\s*教廷",
        r"西\s*斯\s*廷",
        r"sistine",
        r"梵\s*蒂\s*[冈岡]\s*博物馆",
        r"musei\s+vaticani",
        r"vatican\s+museums?",
        r"圣\s*彼\s*得\s*(?:大教堂|广场|廣場|宗座圣殿|宗座聖殿)",
        r"st\.?\s*peter'?s\s*(?:basilica|square)",
        r"basilica\s+di\s+san\s+pietro",
        r"piazza\s+san\s+pietro",
        r"apostolic\s+palace",
        r"papal\s+palace",
        r"教\s*皇\s*宫",
        r"宗\s*座\s*宫",
    )
)

_RESTRICTED_COORDINATE_BOXES: tuple[tuple[float, float, float, float], ...] = (
    # Vatican City and immediately adjacent Vatican tourism landmarks.
    (41.8985, 41.9088, 12.4440, 12.4598),
)

_RESTRICTED_EXCLUSION_SENTENCE_PATTERN = re.compile(
    r"[^。！？.!?\n]*(?:不得出现|不得包含|不能出现|不能包含|不要出现|不要画出|不要标注|禁止出现|禁止包含|"
    r"完全排除|必须完全排除|必须排除)[^。！？.!?\n]*(?:[。！？.!?]|\n|$)",
    re.IGNORECASE,
)

RESTRICTED_DESTINATION_GUARD_TEXT = (
    "硬性目的地限制：成图、地图、路线、标题、标签、图例、装饰、背景地标、AI 自行补充的推荐点和任何可见文字中，"
    "都不得出现 Vatican City / Holy See / 梵蒂冈 / 圣座，"
    "也不得出现梵蒂冈博物馆、圣彼得大教堂、圣彼得广场、西斯廷教堂、宗座宫等相关地标或符号。"
    "即使这些元素是模型自行联想到的热门景点，也必须完全排除，不要画出、标注或暗示。"
)


def restricted_destination_matches_text(value: Any) -> list[str]:
    text = str(value or "")
    if not text:
        return []
    return [pattern.pattern for pattern in _RESTRICTED_TEXT_PATTERNS if pattern.search(text)]


def contains_restricted_destination_text(value: Any) -> bool:
    return bool(restricted_destination_matches_text(value))


def contains_restricted_destination_request_text(value: Any) -> bool:
    return contains_restricted_destination_text(_without_restricted_destination_guard(value))


def coordinates_in_restricted_destination(lat: Any, lng: Any) -> bool:
    parsed_lat = _float_or_none(lat)
    parsed_lng = _float_or_none(lng)
    if parsed_lat is None or parsed_lng is None:
        return False
    return any(
        min_lat <= parsed_lat <= max_lat and min_lng <= parsed_lng <= max_lng
        for min_lat, max_lat, min_lng, max_lng in _RESTRICTED_COORDINATE_BOXES
    )


def stop_has_restricted_destination(value: dict[str, Any]) -> bool:
    stop_text = " ".join(
        str(value.get(key) or "")
        for key in ("name", "label", "country", "transport", "note", "address", "geocoded_name", "geocoded_address")
    )
    return contains_restricted_destination_text(stop_text) or coordinates_in_restricted_destination(
        value.get("lat"), value.get("lng")
    )


def values_contain_restricted_destination(values: list[Any] | tuple[Any, ...]) -> bool:
    return any(contains_restricted_destination_request_text(value) for value in values)


def append_restricted_destination_guard(prompt: str) -> str:
    cleaned = str(prompt or "").strip()
    if not cleaned:
        return RESTRICTED_DESTINATION_GUARD_TEXT
    if RESTRICTED_DESTINATION_GUARD_TEXT in cleaned:
        return cleaned
    return f"{cleaned}\n\n{RESTRICTED_DESTINATION_GUARD_TEXT}"


def _without_restricted_destination_guard(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    cleaned = text.replace(RESTRICTED_DESTINATION_GUARD_TEXT, "")
    cleaned = re.sub(
        r"硬性目的地限制[:：].*?(?:。|$)",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = _RESTRICTED_EXCLUSION_SENTENCE_PATTERN.sub(_remove_restricted_exclusion_sentence, cleaned)
    return cleaned


def _remove_restricted_exclusion_sentence(match: re.Match[str]) -> str:
    sentence = match.group(0)
    if contains_restricted_destination_text(sentence):
        return ""
    return sentence


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

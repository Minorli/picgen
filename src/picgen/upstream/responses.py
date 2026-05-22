from __future__ import annotations

import logging
from typing import Any

from ..logging_config import get_logger, log_event
from .payload import extract_response_image_item, normalize_responses_image_payload

logger = get_logger("picgen.upstream.responses")


def parse_sse_json_events(body: str) -> list[dict[str, Any]]:
    import json as _json

    events: list[dict[str, Any]] = []
    data_lines: list[str] = []

    def flush_event() -> None:
        if not data_lines:
            return
        data = "\n".join(data_lines).strip()
        data_lines.clear()
        if not data or data == "[DONE]":
            return
        try:
            parsed = _json.loads(data)
        except _json.JSONDecodeError:
            return
        if isinstance(parsed, dict):
            events.append(parsed)

    for raw_line in body.splitlines():
        line = raw_line.rstrip("\r\n")
        if not line:
            flush_event()
            continue
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())

    flush_event()
    return events


def event_image_base64(event: dict[str, Any]) -> str | None:
    for key in ("partial_image_b64", "result", "b64_json", "image_b64"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value

    item = event.get("item")
    if isinstance(item, dict):
        for key in ("result", "b64_json"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value

    response = event.get("response")
    if isinstance(response, dict):
        first_item = extract_response_image_item(response)
        value = first_item.get("b64_json")
        if isinstance(value, str) and value:
            return value

    return None


def stream_events_to_image_payload(
    events: list[dict[str, Any]],
    *,
    url: str,
    started_at: float,
) -> dict[str, Any]:
    import time as _time

    last_image_b64: str | None = None
    completed_response: dict[str, Any] = {}
    for event in events:
        image_b64 = event_image_base64(event)
        if image_b64:
            last_image_b64 = image_b64
        response_payload = event.get("response")
        if isinstance(response_payload, dict):
            completed_response = response_payload

    log_event(
        logger,
        logging.INFO,
        "upstream_responses_stream_ok",
        url=url,
        elapsed_ms=round((_time.perf_counter() - started_at) * 1000, 1),
        events=len(events),
        has_image=bool(last_image_b64 or extract_response_image_item(completed_response)),
    )
    return normalize_responses_image_payload(
        completed_response,
        fallback_b64=last_image_b64,
        events=events[-20:],
    )

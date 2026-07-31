from __future__ import annotations

import logging
from typing import Any

from ..logging_config import get_logger, log_event
from ..redaction import redact_sensitive_text
from .payload import extract_response_image_item, normalize_responses_image_payload

logger = get_logger("picgen.upstream.responses")


def parse_sse_json_events(body: str) -> list[dict[str, Any]]:
    import json as _json
    import re as _re

    events: list[dict[str, Any]] = []
    data_lines: list[str] = []
    dropped = 0

    def flush_event() -> None:
        nonlocal dropped
        if not data_lines:
            return
        data = "\n".join(data_lines).strip()
        data_lines.clear()
        if not data or data == "[DONE]":
            return
        try:
            parsed = _json.loads(data)
        except _json.JSONDecodeError:
            dropped += 1
            return
        if isinstance(parsed, dict):
            events.append(parsed)

    # SSE frames are delimited by \r\n / \n / \r ONLY. str.splitlines() would
    # also split on U+2028/U+2029/\x0b/…, which are legal raw inside JSON
    # strings — a model output containing one would shred the event's JSON.
    for raw_line in _re.split(r"\r\n|\r|\n", body):
        line = raw_line
        if not line:
            flush_event()
            continue
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())

    flush_event()
    if dropped:
        log_event(
            logger,
            logging.WARNING,
            "responses_sse_events_dropped",
            dropped=dropped,
            parsed=len(events),
        )
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


def event_text_delta(event: dict[str, Any]) -> str | None:
    event_type = str(event.get("type") or "")
    if event_type not in {"response.output_text.delta", "response.text.delta"}:
        return None
    for key in ("delta", "text", "output_text"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def response_has_text(response: dict[str, Any]) -> bool:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return True
    output = response.get("output")
    for item in output if isinstance(output, list) else []:
        if not isinstance(item, dict):
            continue
        for key in ("text", "output_text"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return True
        content = item.get("content")
        for part in content if isinstance(content, list) else []:
            if not isinstance(part, dict) or part.get("type") not in {"output_text", "text"}:
                continue
            value = part.get("text") or part.get("output_text")
            if isinstance(value, str) and value.strip():
                return True
    return False


def stream_events_to_image_payload(
    events: list[dict[str, Any]],
    *,
    url: str,
    started_at: float,
) -> dict[str, Any]:
    import time as _time

    last_image_b64: str | None = None
    completed_response: dict[str, Any] = {}
    text_chunks: list[str] = []
    event_types: list[str] = []
    for event in events:
        event_type = redact_sensitive_text(str(event.get("type") or "").strip(), limit=120)
        if event_type and event_type not in event_types:
            event_types.append(event_type)
        image_b64 = event_image_base64(event)
        if image_b64:
            last_image_b64 = image_b64
        text_delta = event_text_delta(event)
        if text_delta:
            text_chunks.append(text_delta)
        response_payload = event.get("response")
        if isinstance(response_payload, dict):
            completed_response = response_payload
    has_image = bool(last_image_b64 or extract_response_image_item(completed_response))
    has_text = bool(text_chunks) or response_has_text(completed_response)
    response_status = redact_sensitive_text(
        str(completed_response.get("status") or "").strip(),
        limit=120,
    )
    response_error = completed_response.get("error")
    response_error_code = (
        redact_sensitive_text(
            str(response_error.get("code") or response_error.get("type") or "").strip(),
            limit=120,
        )
        if isinstance(response_error, dict)
        else ""
    )

    log_event(
        logger,
        logging.INFO if has_image or has_text else logging.WARNING,
        "upstream_responses_stream_ok",
        url=url,
        elapsed_ms=round((_time.perf_counter() - started_at) * 1000, 1),
        events=len(events),
        event_types=event_types[-20:],
        response_status=response_status,
        response_error_code=response_error_code,
        has_image=has_image,
        has_text=has_text,
    )
    if has_image:
        normalized = normalize_responses_image_payload(
            completed_response,
            fallback_b64=last_image_b64,
            events=events[-20:],
        )
        if completed_response.get("output_text"):
            normalized["output_text"] = completed_response["output_text"]
        elif text_chunks:
            normalized["output_text"] = "".join(text_chunks)
        return normalized

    payload = dict(completed_response)
    if text_chunks and not isinstance(payload.get("output_text"), str):
        payload["output_text"] = "".join(text_chunks)
    payload["stream_events"] = events[-20:]
    return payload

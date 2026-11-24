from __future__ import annotations

import codecs
import json
import logging
import re
from collections import deque
from collections.abc import AsyncIterator, Iterable
from typing import Any

from ..errors import APIError
from ..logging_config import get_logger, log_event
from ..redaction import redact_sensitive_text
from .errors import raise_for_image_response_error, raise_for_response_error, response_image_diagnostics
from .payload import extract_response_image_item, normalize_responses_image_payload

logger = get_logger("picgen.upstream.responses")


def parse_sse_json_events(body: str) -> list[dict[str, Any]]:
    import json as _json
    import re as _re

    events: list[dict[str, Any]] = []
    data_lines: list[str] = []
    event_name = ""
    dropped = 0

    def flush_event() -> None:
        nonlocal dropped, event_name
        name = event_name
        event_name = ""
        if not data_lines:
            return
        data = "\n".join(data_lines).strip()
        data_lines.clear()
        if not data or data == "[DONE]":
            return
        try:
            parsed = _json.loads(data)
        except RecursionError as exc:
            raise APIError(
                502,
                "图片生成服务返回了无法解析的响应，请稍后再试。",
                "Responses SSE JSON 嵌套层级过深。",
                code="upstream_invalid_response",
            ) from exc
        except _json.JSONDecodeError:
            dropped += 1
            return
        if isinstance(parsed, dict):
            if name and not parsed.get("type"):
                parsed = {**parsed, "type": name}
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
        elif line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()

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


class _SseStreamAssembler:
    """Incrementally fold Responses SSE JSON events without retaining every
    multi-megabyte ``partial_image_b64`` frame in memory simultaneously."""

    def __init__(self, *, url: str, started_at: float, expect_image: bool = False) -> None:
        self.url = url
        self.started_at = started_at
        self.expect_image = expect_image
        self.last_image_b64: str | None = None
        self.last_final_image_b64: str | None = None
        self.saw_completed_response = False
        self.completed_response: dict[str, Any] = {}
        self.text_chunks: list[str] = []
        self.event_types: list[str] = []
        self.stream_error: APIError | None = None
        self.image_items: dict[str, dict[str, Any]] = {}
        self.final_item_keys: set[str] = set()
        self.refusal_keys: set[str] = set()
        self.event_count = 0
        self.recent_events: deque[dict[str, Any]] = deque(maxlen=20)
        self.stopped = False

    def _remember_item(self, item: dict[str, Any], index: Any = None) -> str:
        key = str(item.get("id") or (f"index:{index}" if index is not None else "unknown"))
        self.image_items[key] = {**self.image_items.get(key, {}), **item}
        return key

    def feed(self, event: dict[str, Any]) -> bool:
        if self.stopped:
            return False
        self.event_count += 1
        raw_event_type = event["type"].strip() if isinstance(event.get("type"), str) else ""
        # Strip bulky partial_image_b64 from the tail diagnostic ring buffer once read,
        # while keeping result/b64_json on final events for normalize_responses_image_payload.
        if raw_event_type == "response.image_generation_call.partial_image" and "partial_image_b64" in event:
            compact_event = {k: v for k, v in event.items() if k != "partial_image_b64"}
            self.recent_events.append(compact_event)
        else:
            self.recent_events.append(event)

        event_type = redact_sensitive_text(raw_event_type, limit=120)
        if event_type and event_type not in self.event_types:
            self.event_types.append(event_type)
        image_b64 = event_image_base64(event)
        if image_b64:
            self.last_image_b64 = image_b64
            if raw_event_type != "response.image_generation_call.partial_image" and not event.get("partial_image_b64"):
                self.last_final_image_b64 = image_b64
        text_delta = event_text_delta(event)
        if text_delta:
            self.text_chunks.append(text_delta)
        response_payload = event.get("response")
        self.saw_completed_response = self.saw_completed_response or raw_event_type == "response.completed" or (
            isinstance(response_payload, dict) and response_payload.get("status") == "completed"
        )
        if isinstance(response_payload, dict):
            self.completed_response = response_payload
            self.final_item_keys = set()
            output = response_payload.get("output")
            merged_output: list[Any] = []
            for index, item in enumerate(output if isinstance(output, list) else []):
                if isinstance(item, dict) and item.get("type") == "image_generation_call":
                    key = self._remember_item(item, index)
                    self.final_item_keys.add(key)
                    merged_output.append(self.image_items[key])
                else:
                    merged_output.append(item)
            if isinstance(output, list):
                self.completed_response = {**response_payload, "output": merged_output}
        event_item = event.get("item")
        if isinstance(event_item, dict) and event_item.get("type") == "image_generation_call":
            self._remember_item(event_item, event.get("output_index"))
        if raw_event_type in {"response.refusal.delta", "response.refusal.done"}:
            self.refusal_keys.add(f"{event.get('item_id', '')}:{event.get('content_index', 0)}")
        if isinstance(event_item, dict) and event_item.get("type") == "message":
            content = event_item.get("content")
            for index, part in enumerate(content if isinstance(content, list) else []):
                if isinstance(part, dict) and part.get("type") == "refusal":
                    self.refusal_keys.add(f"{event_item.get('id', '')}:{index}")
        is_image_event = raw_event_type.startswith("response.image_generation_call.")
        if is_image_event:
            phase = raw_event_type.rsplit(".", 1)[-1]
            if phase in {"generating", "in_progress", "completed", "failed", "incomplete", "cancelled", "canceled"}:
                item = {
                    "type": "image_generation_call",
                    "id": event.get("item_id"),
                    "status": phase,
                    **{key: event[key] for key in ("error", "result") if key in event},
                }
                if phase == "completed" and image_b64 and not event.get("partial_image_b64"):
                    item["result"] = image_b64
                self._remember_item(item, event.get("output_index"))
        try:
            if not is_image_event or isinstance(response_payload, dict):
                raise_for_response_error(
                    response_payload if isinstance(response_payload, dict) else event,
                    event_type=raw_event_type,
                )
        except APIError as exc:
            self.stream_error = exc
            if not isinstance(response_payload, dict):
                self.completed_response = {**event, "error": event.get("error") or event}
            self.stopped = True
            return False
        return True

    def finalize(self) -> dict[str, Any]:
        import time as _time

        completed_response = self.completed_response
        extra_items = [item for key, item in self.image_items.items() if key not in self.final_item_keys]
        if extra_items:
            output = completed_response.get("output")
            completed_response = {
                **completed_response,
                "output": [*(output if isinstance(output, list) else []), *extra_items],
            }
        if self.text_chunks and not isinstance(completed_response.get("output_text"), str):
            completed_response = {**completed_response, "output_text": "".join(self.text_chunks)}
        diagnostics = response_image_diagnostics(completed_response)
        if self.refusal_keys and not diagnostics["refusal_count"]:
            output = completed_response.get("output")
            completed_response = {
                **completed_response,
                "output": [
                    *(output if isinstance(output, list) else []),
                    {"type": "message", "content": [{"type": "refusal"} for _ in self.refusal_keys]},
                ],
            }
            diagnostics = response_image_diagnostics(completed_response)
        stream_error = self.stream_error
        if not stream_error:
            try:
                raise_for_image_response_error(completed_response)
            except APIError as exc:
                stream_error = exc
        last_image_b64 = self.last_final_image_b64 if self.saw_completed_response else self.last_image_b64
        if diagnostics["refusal_count"] or (
            completed_response.get("status") == "completed" and diagnostics["reason"] == "image_tool_unfinished"
        ):
            last_image_b64 = None
        has_image = bool(last_image_b64 or extract_response_image_item(completed_response))
        has_text = bool(self.text_chunks) or response_has_text(completed_response)
        response_status = diagnostics["response_status"]
        response_error = completed_response.get("error")
        response_error_code = (
            redact_sensitive_text(
                response_error.get("code") or response_error.get("type") or "",
                limit=120,
            )
            if isinstance(response_error, dict)
            and isinstance(response_error.get("code") or response_error.get("type") or "", str)
            else ""
        )

        no_image = self.expect_image and not has_image
        log_event(
            logger,
            logging.INFO if not stream_error and not no_image and (has_image or has_text) else logging.WARNING,
            (
                "upstream_responses_stream_error"
                if stream_error
                else "upstream_responses_stream_no_image"
                if no_image
                else "upstream_responses_stream_ok"
            ),
            url=self.url,
            elapsed_ms=round((_time.perf_counter() - self.started_at) * 1000, 1),
            events=self.event_count,
            event_types=self.event_types[-20:],
            response_status=response_status,
            response_id=diagnostics["response_id"],
            response_error_code=response_error_code,
            has_image=has_image,
            has_text=has_text,
            reason=diagnostics["reason"],
            image_call_statuses=[item["status"] for item in diagnostics["image_calls"]],
            image_error_codes=[item["error"].get("code", "") for item in diagnostics["image_calls"]],
            image_moderation_stages=[item["error"].get("moderation_stage", "") for item in diagnostics["image_calls"]],
            refusal_count=diagnostics["refusal_count"],
            text_chars=diagnostics["text_chars"],
        )
        if stream_error:
            raise stream_error
        tail_events = list(self.recent_events)
        if has_image:
            normalized = normalize_responses_image_payload(
                completed_response,
                fallback_b64=last_image_b64,
                events=tail_events,
            )
            if completed_response.get("output_text"):
                normalized["output_text"] = completed_response["output_text"]
            elif self.text_chunks:
                normalized["output_text"] = "".join(self.text_chunks)
            return normalized

        payload = dict(completed_response)
        payload["image_diagnostics"] = diagnostics
        if self.text_chunks and not isinstance(payload.get("output_text"), str):
            payload["output_text"] = "".join(self.text_chunks)
        payload["stream_events"] = tail_events
        return payload


def stream_events_to_image_payload(
    events: Iterable[dict[str, Any]],
    *,
    url: str,
    started_at: float,
    expect_image: bool = False,
) -> dict[str, Any]:
    assembler = _SseStreamAssembler(url=url, started_at=started_at, expect_image=expect_image)
    for event in events:
        if not assembler.feed(event):
            break
    return assembler.finalize()


_SSE_NEWLINE_RE = re.compile(r"\r\n|\r|\n")


async def consume_sse_stream_to_image_payload(
    byte_chunks: AsyncIterator[bytes],
    *,
    url: str,
    started_at: float,
    expect_image: bool = False,
) -> dict[str, Any]:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    assembler = _SseStreamAssembler(url=url, started_at=started_at, expect_image=expect_image)
    data_lines: list[str] = []
    event_name = ""
    dropped = 0
    pending = ""

    def flush_event() -> bool:
        nonlocal dropped, event_name
        name = event_name
        event_name = ""
        if not data_lines:
            return True
        data = "\n".join(data_lines).strip()
        data_lines.clear()
        if not data or data == "[DONE]":
            return True
        try:
            parsed = json.loads(data)
        except RecursionError as exc:
            raise APIError(
                502,
                "图片生成服务返回了无法解析的响应，请稍后再试。",
                "Responses SSE JSON 嵌套层级过深。",
                code="upstream_invalid_response",
            ) from exc
        except json.JSONDecodeError:
            dropped += 1
            return True
        if isinstance(parsed, dict):
            if name and not parsed.get("type"):
                parsed = {**parsed, "type": name}
            return assembler.feed(parsed)
        return True

    def process_line(line: str) -> bool:
        nonlocal event_name
        if not line:
            return flush_event()
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
        elif line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        return True

    async for chunk in byte_chunks:
        pending += decoder.decode(chunk, final=False)
        if not pending:
            continue
        # Hold back a trailing \r in case the next chunk starts with \n (\r\n split across chunks).
        usable_end = len(pending) - 1 if pending.endswith("\r") else len(pending)
        parts = _SSE_NEWLINE_RE.split(pending[:usable_end])
        tail = pending[usable_end:]
        pending = parts.pop() + tail
        for line in parts:
            if not process_line(line):
                break
        if assembler.stopped:
            break

    if not assembler.stopped:
        pending += decoder.decode(b"", final=True)
        for line in _SSE_NEWLINE_RE.split(pending):
            if not process_line(line):
                break
        if not assembler.stopped:
            flush_event()

    if dropped:
        log_event(
            logger,
            logging.WARNING,
            "responses_sse_events_dropped",
            dropped=dropped,
            parsed=assembler.event_count,
        )
    return assembler.finalize()

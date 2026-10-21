from __future__ import annotations

import json
from typing import Any

from ..errors import OUTPUT_IMAGE_POLICY_MESSAGE, APIError
from ..redaction import redact_sensitive_text

_IMAGE_FAILED_STATUSES = frozenset({"failed", "incomplete", "cancelled", "canceled"})
_IMAGE_DIAGNOSTIC_REASONS = frozenset({
    "", "partial_image_failure", "image_tool_failed", "response_refusal", "image_tool_unfinished", "no_image_output",
})


def sanitize_image_diagnostics(value: Any) -> dict[str, Any]:
    """Copy only bounded diagnostic fields; never trust provider-owned extras."""
    fields = {
        "response_id", "response_status", "image_call_count", "result_image_count", "image_calls",
        "refusal_count", "text_chars", "reason",
    }
    if not isinstance(value, dict) or not fields.intersection(value):
        return {}

    def safe_text(value: Any) -> str:
        return redact_sensitive_text(value, limit=120) if isinstance(value, str) else ""

    result: dict[str, Any] = {key: safe_text(value.get(key)) for key in ("response_id", "response_status")}
    for key in ("image_call_count", "result_image_count", "refusal_count", "text_chars"):
        count = value.get(key)
        result[key] = max(0, count) if isinstance(count, int) and not isinstance(count, bool) else 0
    reason = value.get("reason")
    result["reason"] = reason if isinstance(reason, str) and reason in _IMAGE_DIAGNOSTIC_REASONS else "no_image_output"
    calls = value.get("image_calls")
    result["image_calls"] = []
    for item in (calls[:20] if isinstance(calls, list) else []):
        if not isinstance(item, dict):
            continue
        error = item.get("error")
        safe_error = {
            key: safe_text(error[key]) for key in ("code", "type", "param") if key in error
        } if isinstance(error, dict) else {}
        stage = error.get("moderation_stage") if isinstance(error, dict) else None
        if isinstance(stage, str) and stage in {"input", "output"}:
            safe_error["moderation_stage"] = stage
        result["image_calls"].append({
            "id": safe_text(item.get("id")), "status": safe_text(item.get("status")),
            "has_result": item.get("has_result") is True,
            "error": safe_error,
        })
    return result


def response_image_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    output = payload.get("output")
    return [
        item for item in output if isinstance(item, dict) and item.get("type") == "image_generation_call"
    ] if isinstance(output, list) else []


def image_call_has_result(item: dict[str, Any]) -> bool:
    return (
        str(item.get("status") or "") not in _IMAGE_FAILED_STATUSES | {"in_progress", "generating"}
        and not item.get("error")
        and isinstance(item.get("result"), str)
        and bool(item["result"])
    )


def _image_moderation_stage(error: Any) -> str:
    details = error.get("moderation_details") if isinstance(error, dict) else None
    stage = details.get("moderation_stage") if isinstance(details, dict) else None
    return stage if isinstance(stage, str) and stage in {"input", "output"} else ""


def response_image_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    calls = response_image_calls(payload)
    summaries = []
    for item in calls[:20]:
        error = item.get("error")
        safe_error = {
            key: error[key] for key in ("code", "type", "param") if key in error
        } if isinstance(error, dict) else {}
        stage = _image_moderation_stage(error)
        if stage:
            safe_error["moderation_stage"] = stage
        summaries.append({
            "id": item.get("id"),
            "status": item.get("status"),
            "has_result": image_call_has_result(item),
            "error": safe_error,
        })
    output = payload.get("output")
    parts = [
        part for item in output if isinstance(item, dict) and isinstance(item.get("content"), list)
        for part in item["content"] if isinstance(part, dict)
    ] if isinstance(output, list) else []
    refusals = sum(part.get("type") == "refusal" for part in parts)
    text_chars = sum(len(str(part.get("text") or "")) for part in parts if part.get("type") in {"output_text", "text"})
    text_chars = max(text_chars, len(str(payload.get("output_text") or "")))
    result_count = sum(image_call_has_result(item) for item in calls)
    failed = any(item.get("error") or str(item.get("status") or "") in _IMAGE_FAILED_STATUSES for item in calls)
    unfinished = any(str(item.get("status") or "") in {"in_progress", "generating"} for item in calls)
    reason = (
        "partial_image_failure" if result_count and failed else
        "" if result_count else
        "image_tool_failed" if failed else
        "response_refusal" if refusals else
        "image_tool_unfinished" if unfinished else "no_image_output"
    )
    return sanitize_image_diagnostics({
        "response_id": payload.get("id"),
        "response_status": payload.get("status"),
        "image_call_count": len(calls), "result_image_count": result_count,
        "image_calls": summaries, "refusal_count": refusals, "text_chars": text_chars, "reason": reason,
    })


def raise_for_image_response_error(payload: dict[str, Any]) -> None:
    calls = response_image_calls(payload)
    # A failed candidate must not discard other completed, usable candidates.
    if any(image_call_has_result(item) for item in calls):
        return
    for item in calls:
        status = str(item.get("status") or "")
        if item.get("error") or status in _IMAGE_FAILED_STATUSES:
            try:
                raise_for_response_error({
                    "id": payload.get("id"), "image_call_id": item.get("id"),
                    "status": status if status in _IMAGE_FAILED_STATUSES else "failed",
                    "error": item.get("error"), "incomplete_details": item.get("incomplete_details"),
                })
            except APIError as exc:
                # Provider tool errors may echo private prompt/refusal text.
                # Use it for classification, but expose only structured facts.
                details = json.dumps(response_image_diagnostics({**payload, "output": [item]}), ensure_ascii=False)
                message = (
                    OUTPUT_IMAGE_POLICY_MESSAGE
                    if exc.code == "upstream_content_policy" and _image_moderation_stage(item.get("error")) == "output"
                    else exc.message
                )
                raise APIError(exc.status, message, details, code=exc.code) from None


def compact_log_text(value: str, limit: int = 300) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


def _serialize_error_details(value: Any, fallback: str) -> str | None:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except (RecursionError, TypeError, ValueError):
        return fallback.strip() or None


def extract_error_message(response_body: str) -> tuple[str, str | None]:
    message = response_body.strip() or "上游接口返回了错误"
    details: str | None = None

    try:
        parsed_body = json.loads(response_body)
    except (json.JSONDecodeError, RecursionError):
        return (
            redact_sensitive_text(message, limit=1000),
            redact_sensitive_text(response_body.strip(), limit=4000) or None,
        )

    if isinstance(parsed_body, dict):
        if parsed_body.get("cloudflare_error") is True and parsed_body.get("error_code") == 1010:
            message = "上游接口被 Cloudflare 拒绝访问: Error 1010"
            detail_text = str(
                parsed_body.get("detail")
                or "The site owner has blocked access based on your browser's signature."
            )
            ray_id = str(parsed_body.get("ray_id") or parsed_body.get("instance") or "").strip()
            zone = str(parsed_body.get("zone") or "").strip()
            owner_hint = str(parsed_body.get("what_you_should_do") or "").replace("**", "").strip()
            detail_lines = [
                detail_text,
                "这通常不是提示词、API Key 或本地页面的问题，而是上游站点的 Cloudflare 规则拦截了当前代理请求签名。",
            ]
            if owner_hint:
                detail_lines.append(owner_hint)
            if zone or ray_id:
                detail_lines.append(f"Zone: {zone or '-'}; Ray ID: {ray_id or '-'}")
            details = "\n".join(detail_lines)
            return message, redact_sensitive_text(details, limit=4000)

        error_block = parsed_body.get("error")
        if isinstance(error_block, dict):
            message = str(error_block.get("message") or message)
            details = _serialize_error_details(error_block, response_body)
        else:
            details = _serialize_error_details(parsed_body, response_body)
    else:
        details = _serialize_error_details(parsed_body, response_body)

    return redact_sensitive_text(message, limit=1000), redact_sensitive_text(details, limit=4000)


def classify_upstream_error(status: int, message: str, details: str | None = None) -> str:
    haystack = f"{message}\n{details or ''}".lower()
    if status == 429 or "rate limit" in haystack or "rate_limit" in haystack:
        return "upstream_rate_limited"
    if "invalid_mask_image_format" in _error_values(details):
        return "upstream_invalid_image_input"
    if _looks_like_content_policy_error(status, message, details):
        return "upstream_content_policy"
    if "cloudflare" in haystack or "error 1010" in haystack:
        return "upstream_blocked"
    return "upstream_error"


def _looks_like_content_policy_error(status: int, message: str, details: str | None) -> bool:
    explicit_values = _error_values(details)
    if any(
        value in {
            "content_policy",
            "content_policy_violation",
            "policy_violation",
            "safety_policy_violation",
            "moderation_blocked",
        }
        for value in explicit_values
    ):
        return True

    haystack = f"{message}\n{details or ''}".lower()
    explicit_phrases = (
        "content policy",
        "policy violation",
        "disallowed content",
        "disallowed prompt",
        "not allowed by",
        "violates policy",
    )
    if any(phrase in haystack for phrase in explicit_phrases):
        return True
    return status in {400, 403} and any(
        phrase in haystack for phrase in ("not allowed", "disallowed")
    )


def _error_values(details: str | None) -> set[str]:
    if not details:
        return set()
    try:
        parsed = json.loads(details)
    except (json.JSONDecodeError, RecursionError):
        return set()
    if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
        parsed = parsed["error"]
    if not isinstance(parsed, dict):
        return set()
    values = {
        str(parsed.get("code") or "").strip().lower(),
        str(parsed.get("type") or "").strip().lower(),
        str(parsed.get("param") or "").strip().lower(),
    }
    return {value for value in values if value}


def public_upstream_error_message(status: int, code: str, action: str) -> str:
    if code == "upstream_rate_limited":
        return "图片生成服务当前请求较多，请稍后再试。"
    if code == "upstream_invalid_image_input":
        return "上游不接受当前输入图或蒙版的格式/尺寸，请改用像素尺寸一致的标准 PNG 后重试。"
    if code == "upstream_content_policy":
        return "这次提示词没有通过上游内容审核，请调整描述后重试。"
    if code == "upstream_blocked":
        return "图片生成服务被上游临时拦截，请稍后再试或联系管理员。"
    if status in {502, 503, 504}:
        return f"{action}暂时不可用，请稍后再试。"
    return "图片生成服务返回了错误，请稍后再试。"


def raise_for_response_error(payload: dict[str, Any], *, event_type: str = "") -> None:
    """Reject explicit Responses failures before extracting images or text."""
    status = str(payload.get("status") or "").strip().lower()
    error = payload.get("error")
    failed_statuses = {"failed", "incomplete", "cancelled", "canceled"}
    if not error and status not in failed_statuses and event_type not in {
        "error", "response.failed", "response.incomplete", "response.cancelled", "response.canceled"
    }:
        return
    if event_type == "error" and not error:
        error = {key: payload[key] for key in ("code", "type", "message", "param") if key in payload}
    # Keep diagnostics small and exclude potentially large/private image and
    # text outputs. Public messages never include the provider's raw message.
    diagnostics = {
        "response_id": payload.get("id") or payload.get("response_id"),
        "image_call_id": payload.get("image_call_id"),
        "status": status,
        "event_type": event_type,
        "error": error,
        "incomplete_details": payload.get("incomplete_details"),
    }
    serialized = _serialize_error_details(diagnostics, "Responses request failed")
    code = classify_upstream_error(502, "", serialized)
    details = redact_sensitive_text(serialized, limit=4000)
    http_status = {
        "upstream_rate_limited": 429,
        "upstream_content_policy": 400,
        "upstream_invalid_image_input": 400,
    }.get(code, 502)
    message = public_upstream_error_message(http_status, code, "图片生成服务")
    if code == "upstream_error" and (status == "incomplete" or event_type == "response.incomplete"):
        message = "图片生成服务未能完成这次请求，请稍后再试。"
    raise APIError(http_status, message, details, code=code)


def upstream_api_error(
    status: int,
    message: str,
    details: str | None = None,
    *,
    code: str | None = None,
) -> APIError:
    safe_details = redact_sensitive_text(details, limit=4000)
    safe_message = redact_sensitive_text(message, limit=1000)
    resolved_code = code or classify_upstream_error(status, safe_message, safe_details)
    return APIError(status, safe_message, safe_details, code=resolved_code)


def coerce_error_payload(payload: Any, context: str) -> APIError:
    if isinstance(payload, dict):
        serialized = _serialize_error_details(payload, "")
        message, details = extract_error_message(serialized or "上游错误载荷无法序列化")
    else:
        message, details = extract_error_message(str(payload))
    return APIError(502, f"{context}: {message}", details, code="upstream_error")

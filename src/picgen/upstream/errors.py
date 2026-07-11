from __future__ import annotations

import json
from typing import Any

from ..errors import APIError
from ..redaction import redact_sensitive_text


def compact_log_text(value: str, limit: int = 300) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."


def extract_error_message(response_body: str) -> tuple[str, str | None]:
    message = response_body.strip() or "上游接口返回了错误"
    details: str | None = None

    try:
        parsed_body = json.loads(response_body)
    except json.JSONDecodeError:
        return message, response_body.strip() or None

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
            details = json.dumps(error_block, ensure_ascii=False, indent=2)
        else:
            details = json.dumps(parsed_body, ensure_ascii=False, indent=2)
    else:
        details = json.dumps(parsed_body, ensure_ascii=False, indent=2)

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
    except json.JSONDecodeError:
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
        message, details = extract_error_message(json.dumps(payload, ensure_ascii=False))
    else:
        message, details = extract_error_message(str(payload))
    return APIError(502, f"{context}: {message}", details, code="upstream_error")

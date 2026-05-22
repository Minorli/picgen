from __future__ import annotations

import json
from typing import Any

from ..errors import APIError


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
            return message, details

        error_block = parsed_body.get("error")
        if isinstance(error_block, dict):
            message = str(error_block.get("message") or message)
            details = json.dumps(error_block, ensure_ascii=False, indent=2)
        else:
            details = json.dumps(parsed_body, ensure_ascii=False, indent=2)
    else:
        details = json.dumps(parsed_body, ensure_ascii=False, indent=2)

    return message, details


def upstream_api_error(
    status: int,
    message: str,
    details: str | None = None,
    *,
    code: str | None = None,
) -> APIError:
    return APIError(status, message, details, code=code)


def coerce_error_payload(payload: Any, context: str) -> APIError:
    if isinstance(payload, dict):
        message, details = extract_error_message(json.dumps(payload, ensure_ascii=False))
    else:
        message, details = extract_error_message(str(payload))
    return APIError(502, f"{context}: {message}", details, code="upstream_error")

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings


@dataclass(frozen=True)
class NotificationResult:
    configured: bool
    sent: bool
    status: str
    error: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "sent": self.sent,
            "status": self.status,
            "error": self.error,
        }


async def send_bug_report_notification(
    *,
    settings: Settings,
    report: dict[str, Any],
    username: str,
) -> NotificationResult:
    webhook_url = settings.bug_report_webhook_url.strip()
    if not webhook_url:
        return NotificationResult(configured=False, sent=False, status="not_configured")

    content = _build_bug_report_content(report, username)
    try:
        async with httpx.AsyncClient(
            timeout=settings.bug_report_webhook_timeout_seconds,
            follow_redirects=False,
        ) as client:
            response = await _post_webhook(client, settings.bug_report_webhook_kind, webhook_url, report, content)
            response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network failures depend on deployment
        return NotificationResult(configured=True, sent=False, status="failed", error=str(exc)[:300])
    return NotificationResult(configured=True, sent=True, status="sent")


async def _post_webhook(
    client: httpx.AsyncClient,
    kind: str,
    webhook_url: str,
    report: dict[str, Any],
    content: str,
) -> httpx.Response:
    if kind == "wecom":
        return await client.post(
            webhook_url,
            json={
                "msgtype": "markdown",
                "markdown": {"content": content},
            },
        )
    if kind == "serverchan":
        return await client.post(
            webhook_url,
            data={
                "title": f"PicGen Bug 反馈 #{report.get('id', '')}",
                "desp": content,
            },
        )
    return await client.post(
        webhook_url,
        json={
            "type": "picgen_bug_report",
            "content": content,
            "report": report,
        },
    )


def _build_bug_report_content(report: dict[str, Any], username: str) -> str:
    title = _escape_markdown_text(str(report.get("title") or "PicGen Bug 反馈"))
    description = _escape_markdown_text(str(report.get("description") or ""))
    contact = _escape_markdown_text(str(report.get("contact") or ""))
    page_url = _escape_markdown_text(str(report.get("page_url") or ""))
    created_at = _escape_markdown_text(str(report.get("created_at") or ""))
    report_id = _escape_markdown_text(str(report.get("id") or ""))
    user_text = _escape_markdown_text(username)
    lines = [
        f"### PicGen Bug 反馈 #{report_id}",
        f"> 用户：{user_text}",
        f"> 标题：{title}",
        f"> 时间：{created_at}",
        "",
        description,
    ]
    if page_url:
        lines.append(f"\n页面：{page_url}")
    if contact:
        lines.append(f"\n联系方式：{contact}")
    return "\n".join(lines)[:5000]


def _escape_markdown_text(value: str) -> str:
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for char in "\\`*_{}[]()#+-.!|":
        escaped = escaped.replace(char, f"\\{char}")
    return escaped.strip()

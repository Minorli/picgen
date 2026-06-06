from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings
from .redaction import redact_sensitive_text


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


@dataclass(frozen=True)
class ErrorAlert:
    request_id: str
    method: str
    path: str
    status: int
    code: str
    client: str
    public_message: str
    technical_message: str
    details: str | None = None


def error_alert_notifications_enabled(settings: Settings) -> bool:
    return bool(
        settings.error_alert_telegram_bot_token.strip()
        and settings.error_alert_telegram_chat_id.strip()
    )


async def send_error_alert_notification(
    *,
    settings: Settings,
    alert: ErrorAlert,
) -> NotificationResult:
    token = settings.error_alert_telegram_bot_token.strip()
    chat_id = settings.error_alert_telegram_chat_id.strip()
    if not token or not chat_id:
        return NotificationResult(configured=False, sent=False, status="not_configured")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    content = build_error_alert_text(alert)
    try:
        async with httpx.AsyncClient(
            timeout=settings.error_alert_telegram_timeout_seconds,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": content,
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network failures depend on deployment
        return NotificationResult(configured=True, sent=False, status="failed", error=str(exc)[:300])
    return NotificationResult(configured=True, sent=True, status="sent")


def build_error_alert_text(alert: ErrorAlert) -> str:
    detail_text = redact_sensitive_text(alert.details, limit=1800)
    technical_message = redact_sensitive_text(alert.technical_message, limit=900)
    public_message = redact_sensitive_text(alert.public_message, limit=500)
    lines = [
        "PicGen 后台异常告警",
        f"Request ID: {alert.request_id or '-'}",
        f"HTTP: {alert.method} {alert.path}",
        f"Status: {alert.status}",
        f"Code: {alert.code or '-'}",
        f"Client: {alert.client or '-'}",
        f"User message: {public_message or '-'}",
        "",
        f"Technical: {technical_message or '-'}",
    ]
    if detail_text:
        lines.extend(["", "Details:", detail_text])
    return "\n".join(lines)[:3900]


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

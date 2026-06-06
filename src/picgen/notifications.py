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


@dataclass(frozen=True)
class GenerationSuccessAlert:
    request_id: str
    job_id: int
    user_id: int
    username: str
    method: str
    path: str
    mode: str
    model: str
    size: str
    prompt: str
    image_count: int
    candidate_count: int
    saved_bytes: int
    elapsed_ms: float
    logo_requested: bool
    logo_overlay_applied: bool
    saved_image_urls: list[str]
    generated_image_ids: list[int]


def error_alert_notifications_enabled(settings: Settings) -> bool:
    return bool(
        settings.error_alert_telegram_bot_token.strip()
        and settings.error_alert_telegram_chat_id.strip()
    )


def admin_notifications_enabled(settings: Settings) -> bool:
    return error_alert_notifications_enabled(settings) or bool(settings.bug_report_webhook_url.strip())


async def _send_telegram_message(
    *,
    settings: Settings,
    content: str,
) -> NotificationResult:
    token = settings.error_alert_telegram_bot_token.strip()
    chat_id = settings.error_alert_telegram_chat_id.strip()
    if not token or not chat_id:
        return NotificationResult(configured=False, sent=False, status="not_configured")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
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


async def send_error_alert_notification(
    *,
    settings: Settings,
    alert: ErrorAlert,
) -> NotificationResult:
    return await _send_telegram_message(settings=settings, content=build_error_alert_text(alert))


async def send_generation_success_notification(
    *,
    settings: Settings,
    alert: GenerationSuccessAlert,
) -> NotificationResult:
    return await _send_telegram_message(settings=settings, content=build_generation_success_alert_text(alert))


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


def build_generation_success_alert_text(alert: GenerationSuccessAlert) -> str:
    prompt = redact_sensitive_text(alert.prompt, limit=600)
    urls = [redact_sensitive_text(url, limit=300) for url in alert.saved_image_urls[:5] if url]
    image_ids = ", ".join(str(image_id) for image_id in alert.generated_image_ids[:10]) or "-"
    lines = [
        "PicGen 生图成功",
        f"用户：{alert.username or '-'} (#{alert.user_id})",
        f"任务：#{alert.job_id} / {alert.request_id or '-'}",
        f"接口：{alert.method} {alert.path}",
        f"模式：{alert.mode or '-'}",
        f"模型：{alert.model or '-'}",
        f"尺寸：{alert.size or '-'}",
        f"图片数：{alert.image_count}",
        f"候选数：{alert.candidate_count}",
        f"落盘：{_format_bytes(alert.saved_bytes)}",
        f"耗时：{alert.elapsed_ms / 1000:.1f}s",
        f"LOGO：请求={'是' if alert.logo_requested else '否'} / 成品={'是' if alert.logo_overlay_applied else '否'}",
        f"图片 ID：{image_ids}",
    ]
    if urls:
        lines.extend(["", "图片：", *urls])
    if prompt:
        lines.extend(["", "提示词：", prompt])
    return "\n".join(lines)[:3900]


def _format_bytes(value: int) -> str:
    size = max(0, int(value or 0))
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


async def send_bug_report_notification(
    *,
    settings: Settings,
    report: dict[str, Any],
    username: str,
) -> NotificationResult:
    content = _build_bug_report_content(report, username)
    if error_alert_notifications_enabled(settings):
        return await _send_telegram_message(settings=settings, content=content)

    webhook_url = settings.bug_report_webhook_url.strip()
    if not webhook_url:
        return NotificationResult(configured=False, sent=False, status="not_configured")

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


async def send_password_reset_request_notification(
    *,
    settings: Settings,
    request_info: dict[str, Any],
) -> NotificationResult:
    content = build_password_reset_request_notification_text(request_info)
    if error_alert_notifications_enabled(settings):
        return await _send_telegram_message(settings=settings, content=content)

    webhook_url = settings.bug_report_webhook_url.strip()
    if not webhook_url:
        return NotificationResult(configured=False, sent=False, status="not_configured")

    try:
        async with httpx.AsyncClient(
            timeout=settings.bug_report_webhook_timeout_seconds,
            follow_redirects=False,
        ) as client:
            response = await _post_admin_notification(
                client,
                settings.bug_report_webhook_kind,
                webhook_url,
                "PicGen 密码找回申请",
                content,
                "picgen_password_reset_request",
                request_info,
            )
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


async def _post_admin_notification(
    client: httpx.AsyncClient,
    kind: str,
    webhook_url: str,
    title: str,
    content: str,
    event_type: str,
    payload: dict[str, Any],
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
                "title": title,
                "desp": content,
            },
        )
    return await client.post(
        webhook_url,
        json={
            "type": event_type,
            "content": content,
            "payload": payload,
        },
    )


def build_password_reset_request_notification_text(request_info: dict[str, Any]) -> str:
    request_id = _escape_markdown_text(str(request_info.get("id") or ""))
    username = _escape_markdown_text(str(request_info.get("username") or ""))
    normalized = _escape_markdown_text(str(request_info.get("username_normalized") or ""))
    requested_ip = _escape_markdown_text(str(request_info.get("requested_ip") or ""))
    user_agent = _escape_markdown_text(str(request_info.get("user_agent") or ""))
    created_at = _escape_markdown_text(str(request_info.get("created_at") or ""))
    user_id = request_info.get("user_id")
    matched_user = bool(request_info.get("matched_user"))
    matched_text = f"是 (#{int(user_id)})" if matched_user and user_id else "否"
    lines = [
        f"### PicGen 密码找回申请 #{request_id}",
        f"> 账号：{username or '-'}",
        f"> 规范账号：{normalized or '-'}",
        f"> 匹配用户：{matched_text}",
        f"> 来源 IP：{requested_ip or '-'}",
        f"> 时间：{created_at or '-'}",
    ]
    if user_agent:
        lines.extend(["", f"User-Agent：{user_agent}"])
    return "\n".join(lines)[:5000]


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

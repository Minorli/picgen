from __future__ import annotations

import httpx

from picgen.config import Settings
from picgen.notifications import (
    ErrorAlert,
    GenerationSuccessAlert,
    _build_bug_report_content,
    _send_telegram_message,
    build_bug_report_telegram_text,
    build_error_alert_text,
    build_generation_success_alert_text,
    build_password_reset_request_notification_text,
    build_password_reset_request_telegram_text,
    send_bug_report_notification,
    send_password_reset_email,
    send_password_reset_request_notification,
    smtp_notifications_enabled,
)


def test_bug_report_markdown_escapes_entities_without_double_escape() -> None:
    content = _build_bug_report_content(
        {
            "id": 7,
            "title": "<按钮> & [坏了](https://evil.test)",
            "description": "# 标题\n*重点* <script>alert(1)</script> & 已复现",
            "contact": "wx: alice & bob",
            "page_url": "https://picgen.test/?a=1&b=<x>",
            "created_at": "2026-06-05T12:00:00+08:00",
        },
        "alice_admin",
    )

    assert "&lt;按钮&gt; &amp;" in content
    assert "&amp;lt;" not in content
    assert r"\[坏了\]\(https://evil\.test\)" in content
    assert r"\# 标题" in content
    assert r"&lt;script&gt;alert\(1\)&lt;/script&gt; &amp; 已复现" in content


def test_error_alert_text_redacts_sensitive_values_and_truncates() -> None:
    alert = ErrorAlert(
        request_id="req-123456",
        method="POST",
        path="/api/generate",
        status=429,
        code="upstream_rate_limited",
        client="172.16.0.50",
        public_message="图片生成服务当前请求较多，请稍后再试。",
        technical_message=(
            "Rate limit reached for gpt-image-2-codex in organization "
            "org-BOvpEHVcDPTe8h4lZnwMO5Ly with key sk-testsecret123456"
        ),
        details=(
            '{"api_key":"sk-anothersecret123456","authorization":"Bearer token123456",'
            '"url":"https://example.test/?token=very-secret"}'
            + "x" * 5000
        ),
    )

    content = build_error_alert_text(alert)

    assert content.startswith("【PicGen｜后台异常】429 upstream_rate_limited")
    assert "用户提示：" in content
    assert "技术信息：" in content
    assert "org-BOvpEHVcDPTe8h4lZnwMO5Ly" not in content
    assert "sk-testsecret123456" not in content
    assert "sk-anothersecret123456" not in content
    assert "Bearer token123456" not in content
    assert "very-secret" not in content
    assert "org-***" in content
    assert len(content) <= 3900


def test_generation_success_alert_text_is_detailed_and_redacted() -> None:
    alert = GenerationSuccessAlert(
        request_id="req-ok-123",
        job_id=42,
        user_id=7,
        username="alice",
        method="POST",
        path="/api/generate",
        mode="generate",
        model="gpt-image-2",
        size="1088x2240",
        prompt="生成一张旅行海报，api_key=sk-secret123456",
        image_count=2,
        candidate_count=2,
        saved_bytes=4096,
        elapsed_ms=1234.5,
        logo_requested=True,
        logo_overlay_applied=False,
        saved_image_urls=["files/outputs/20260606/alice-generate.png"],
        generated_image_ids=[101, 102],
    )

    content = build_generation_success_alert_text(alert)

    assert content.startswith("【PicGen｜生图成功】alice #42")
    assert "用户：alice (#7)" in content
    assert "任务：#42 / req-ok-123" in content
    assert "模型：gpt-image-2" in content
    assert "尺寸：1088x2240" in content
    assert "图片数：2" in content
    assert "LOGO：请求=是 / 成品=否" in content
    assert "files/outputs/20260606/alice-generate.png" not in content
    assert "sk-secret123456" not in content
    assert "api_key=***" not in content
    assert "生成一张旅行海报" not in content
    assert len(content) <= 3900


def test_final_image_success_alert_text_has_distinct_title() -> None:
    alert = GenerationSuccessAlert(
        request_id="req-final-123",
        job_id=42,
        user_id=7,
        username="alice",
        method="POST",
        path="/api/final-images",
        mode="itinerary",
        model="gpt-image-2",
        size="",
        prompt="生成全球旅行路线图",
        image_count=1,
        candidate_count=1,
        saved_bytes=4096,
        elapsed_ms=456.7,
        logo_requested=True,
        logo_overlay_applied=True,
        saved_image_urls=["files/outputs/20260608/alice-itinerary-logo.png"],
        generated_image_ids=[101],
    )

    content = build_generation_success_alert_text(alert)

    assert content.startswith("【PicGen｜LOGO 成品已保存】alice #42")
    assert "接口：POST /api/final-images" in content
    assert "模式：itinerary" in content
    assert "LOGO：请求=是 / 成品=是" in content
    assert "files/outputs/20260608/alice-itinerary-logo.png" not in content


def test_password_reset_email_uses_smtp_without_leaking_secret(settings_factory, monkeypatch) -> None:
    sent_messages = []
    logins = []

    class FakeSMTP:
        def __init__(self, host, port, *, timeout, context):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.context = context

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def login(self, username, password):
            logins.append((username, password))

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr("picgen.notifications.smtplib.SMTP_SSL", FakeSMTP)
    settings = settings_factory(
        smtp_host="smtpdm.aliyun.com",
        smtp_port=465,
        smtp_username="noreply@example.com",
        smtp_password="mail-secret",
        smtp_from_email="noreply@example.com",
        smtp_from_name="PicGen 测试",
    )

    assert smtp_notifications_enabled(settings) is True
    result = send_password_reset_email(
        settings=settings,
        to_email="alice@example.com",
        username="alice",
        reset_url="https://picgen.example.com/?reset_token=token-123",
        expires_minutes=30,
    )

    assert result.sent is True
    assert logins == [("noreply@example.com", "mail-secret")]
    assert len(sent_messages) == 1
    message = sent_messages[0]
    assert message["To"] == "alice@example.com"
    assert message["Subject"] == "PicGen 密码重置"
    body = message.get_content()
    assert "https://picgen.example.com/?reset_token=token-123" in body
    assert "30 分钟内有效" in body
    assert "mail-secret" not in body


def test_password_reset_request_notification_text_is_admin_friendly_and_escaped() -> None:
    content = build_password_reset_request_notification_text(
        {
            "id": 9,
            "username": "alice",
            "username_normalized": "alice",
            "user_id": 3,
            "matched_user": True,
            "requested_ip": "172.16.0.50",
            "user_agent": "Browser <script> & bot",
            "created_at": "2026-06-06T20:00:00+08:00",
        }
    )

    assert "PicGen 密码找回申请" in content
    assert "#9" in content
    assert "账号：alice" in content
    assert "匹配用户：是 (#3)" in content
    assert r"172\.16\.0\.50" in content
    assert "&lt;script&gt; &amp; bot" in content


def test_admin_telegram_text_has_clear_categories_and_titles() -> None:
    bug_text = build_bug_report_telegram_text(
        {
            "id": 7,
            "title": "下载按钮没有反应",
            "description": "点击下载后没有保存图片，也没有错误提示。",
            "contact": "wechat: alice",
            "page_url": "https://picgen.test/#resultPanel",
            "created_at": "2026-06-06T20:00:00+08:00",
        },
        "alice",
    )
    reset_text = build_password_reset_request_telegram_text(
        {
            "id": 9,
            "username": "alice",
            "username_normalized": "alice",
            "matched_user": True,
            "user_id": 3,
            "requested_ip": "172.16.0.50",
            "user_agent": "Browser <script> & bot",
            "created_at": "2026-06-06T20:01:00+08:00",
        }
    )

    assert bug_text.startswith("【PicGen｜Bug 反馈】#7 下载按钮没有反应")
    assert "标题：下载按钮没有反应" in bug_text
    assert "用户：alice" in bug_text
    assert "描述：点击下载后没有保存图片，也没有错误提示。" in bug_text
    assert "###" not in bug_text
    assert "\n>" not in bug_text

    assert reset_text.startswith("【PicGen｜找回密码】#9 alice")
    assert "账号：alice" in reset_text
    assert "匹配：是（用户 #3）" in reset_text
    assert "来源：172.16.0.50" in reset_text
    assert "Browser <script> & bot" in reset_text
    assert "###" not in reset_text
    assert "\n>" not in reset_text


def test_telegram_notification_timeout_default_is_not_too_aggressive() -> None:
    settings = Settings(_env_file=None)

    assert settings.error_alert_telegram_timeout_seconds == 15.0


async def test_telegram_notification_failure_keeps_diagnostic_error(settings_factory, monkeypatch) -> None:
    settings = settings_factory(
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-100123456",
        error_alert_telegram_timeout_seconds=15,
    )

    class _BrokenAsyncClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, *args, **kwargs):
            raise httpx.ConnectTimeout("")

    monkeypatch.setattr(httpx, "AsyncClient", _BrokenAsyncClient)

    result = await _send_telegram_message(settings=settings, content="hello")

    assert result.configured is True
    assert result.sent is False
    assert result.status == "failed"
    assert "ConnectTimeout" in result.error
    assert result.error.strip()


async def test_admin_notifications_use_telegram_when_configured(settings_factory, respx_mock) -> None:
    settings = settings_factory(
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-100123456",
    )
    route = respx_mock.post("https://api.telegram.org/bot123:abc/sendMessage").respond(200, json={"ok": True})

    bug_result = await send_bug_report_notification(
        settings=settings,
        username="alice",
        report={
            "id": 7,
            "title": "下载按钮没有反应",
            "description": "点击下载后没有保存图片。",
            "created_at": "2026-06-06T20:00:00+08:00",
        },
    )
    reset_result = await send_password_reset_request_notification(
        settings=settings,
        request_info={
            "id": 9,
            "username": "alice",
            "username_normalized": "alice",
            "matched_user": True,
            "user_id": 3,
            "created_at": "2026-06-06T20:00:00+08:00",
        },
    )

    assert bug_result.sent is True
    assert reset_result.sent is True
    assert route.call_count == 2
    first_payload = route.calls[0].request.content.decode()
    second_payload = route.calls[1].request.content.decode()
    assert "-100123456" in first_payload
    assert "【PicGen｜Bug 反馈】#7 下载按钮没有反应" in first_payload
    assert "【PicGen｜找回密码】#9 alice" in second_payload

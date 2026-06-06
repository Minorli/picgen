from __future__ import annotations

from picgen.notifications import ErrorAlert, _build_bug_report_content, build_error_alert_text


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

    assert "PicGen 后台异常告警" in content
    assert "org-BOvpEHVcDPTe8h4lZnwMO5Ly" not in content
    assert "sk-testsecret123456" not in content
    assert "sk-anothersecret123456" not in content
    assert "Bearer token123456" not in content
    assert "very-secret" not in content
    assert "org-***" in content
    assert len(content) <= 3900

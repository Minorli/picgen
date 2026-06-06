from __future__ import annotations

from picgen.notifications import _build_bug_report_content


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

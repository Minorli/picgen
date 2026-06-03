from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_logo_guidance_preserves_required_text_lines() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    logo_b64 = (ROOT_DIR / "static" / "6renyou.png.b64").read_text(encoding="ascii")
    assert "6 人游定制旅行" in app_js
    assert "Friends & Family" in app_js
    assert "friends & Family" not in app_js
    assert "不能删减、改写、翻译、替换大小写或改变这些文字内容" in app_js
    assert "左侧图标原本的几种绿色必须保持不变" in app_js
    assert "只能调整右侧两行文字的颜色" in app_js
    assert "整体 LOGO 面积要小一些" in app_js
    assert "6renyou.png.b64" in app_js
    assert logo_b64.startswith("iVBORw0KGgo")


def test_generate_sample_count_ui_is_bounded_and_not_sent_with_logo() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")

    assert 'id="generateSampleCountInput"' in index_html
    assert 'max="3"' in index_html
    assert "getGenerateSampleCount" in app_js
    assert "生成数量必须在 1 到 3 之间" in app_js
    assert "logoRequested || referenceImages.length ? 1 : getGenerateSampleCount()" in app_js
    assert "sample_count: sampleCount" in app_js

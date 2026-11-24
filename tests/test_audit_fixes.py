from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from picgen.auth import AuthStore
from picgen.errors import APIError
from picgen.itinerary_map import _project_stops, render_itinerary_control_png
from picgen.logging_config import JsonFormatter, get_logger, log_event
from picgen.main import create_app
from picgen.notifications import send_password_reset_email
from picgen.redaction import redact_sensitive_text
from picgen.restricted_destinations import values_contain_restricted_destination
from picgen.routes import _resolve_itinerary_id, _text_fidelity_passed
from picgen.schemas import UserProfileRequest
from picgen.storage import sanitize_filename
from picgen.upstream.payload import validate_url
from picgen.upstream.responses import consume_sse_stream_to_image_payload

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_restricted_destination_blocks_unicode_evasion_and_clause_smuggling() -> None:
    assert values_contain_restricted_destination(["梵\u200b蒂\u200b冈夜景海报"]) is True
    assert values_contain_restricted_destination(["Ｖａｔｉｃａｎ 街景摄影"]) is True
    assert values_contain_restricted_destination(["不得出现圣座，去梵蒂冈博物馆"]) is True
    assert values_contain_restricted_destination(["硬性目的地限制：梵蒂冈圣彼得广场海报"]) is True
    assert values_contain_restricted_destination(["本次罗马行程不得出现梵蒂冈，不要出现西斯廷。"]) is False


def test_redaction_masks_basic_auth_url_credentials_and_webhooks() -> None:
    raw = (
        "Authorization: Basic dXNlcjpzZWNyZXQ= "
        "url=https://admin:supersecret@example.com/v1 "
        "x-api-key: sk-custom-secret-token "
        "https://sctapi.ftqq.com/SCT123456abcdef.send "
        "https://open.feishu.cn/open-apis/bot/v2/hook/99887766-5544-3322-1100"
    )
    redacted = redact_sensitive_text(raw, limit=1000)

    assert "dXNlcjpzZWNyZXQ=" not in redacted
    assert "supersecret" not in redacted
    assert "sk-custom-secret-token" not in redacted
    assert "SCT123456abcdef" not in redacted
    assert "99887766-5544-3322-1100" not in redacted


def test_json_logger_prevents_reserved_key_collision_and_redacts_nested_secrets() -> None:
    logger = get_logger("picgen.test.audit")
    formatter = JsonFormatter()
    record = logger.makeRecord(
        name="picgen.test.audit",
        level=logging.INFO,
        fn=__file__,
        lno=1,
        msg="audit_event",
        args=(),
        exc_info=None,
    )
    record.fields = {
        "msg": "custom-field-should-not-collide",
        "nested": {"Authorization": "Bearer secret-token-value"},
    }
    payload = json.loads(formatter.format(record))

    assert payload["msg"] == "audit_event"
    assert payload["field_msg"] == "custom-field-should-not-collide"
    assert "secret-token-value" not in json.dumps(payload)
    log_event(logger, logging.INFO, "audit_smoke", msg="safe")


def test_sanitize_filename_rejects_dot_only_and_control_characters() -> None:
    assert sanitize_filename("...") == "image.png"
    assert sanitize_filename(".") == "image.png"
    cleaned = sanitize_filename("poster\x00\x1f-name.png")
    assert "\x00" not in cleaned
    assert "\x1f" not in cleaned


def test_email_validation_blocks_multi_recipient_injection(settings_factory) -> None:
    with pytest.raises(ValidationError):
        UserProfileRequest(email="alice@example.com, attacker@evil.example")
    with pytest.raises(ValidationError):
        UserProfileRequest(email="Alice <alice@example.com>")

    settings = settings_factory(
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_username="noreply@example.com",
        smtp_password="secret",
        smtp_from_email="noreply@example.com",
    )
    result = send_password_reset_email(
        settings=settings,
        to_email="alice@example.com, attacker@evil.example",
        username="alice",
        reset_url="https://picgen.example.com/?reset_token=abc",
        expires_minutes=30,
    )
    assert result.sent is False
    assert result.status == "failed"


def test_changing_profile_email_revokes_pending_password_reset_tokens(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.sqlite3")
    user = store.create_user("alice", "ValidPass123!")
    store.update_user_profile(
        user_id=user.id,
        username="alice",
        current_password="",
        display_name="Alice",
        wechat="",
        phone_country_code="+86",
        phone="",
        email="old@example.com",
        company="6renyou",
        department="PD & OPS",
        team="",
        job_title="",
        note="",
    )
    reset_info = store.request_password_reset("alice")
    token = str(reset_info["reset_token"])
    assert token

    store.update_user_profile(
        user_id=user.id,
        username="alice",
        current_password="",
        display_name="Alice",
        wechat="",
        phone_country_code="+86",
        phone="",
        email="new@example.com",
        company="6renyou",
        department="PD & OPS",
        team="",
        job_title="",
        note="",
    )

    assert store.reset_password_with_token(token=token, password="NewValidPass123!") is None


def test_itinerary_id_regex_ignores_english_words_and_fidelity_checks_fail_first() -> None:
    assert _resolve_itinerary_id(explicit_id=None, prompt="A cozy cabin idea in Idaho, ideal lighting") == ""
    assert _resolve_itinerary_id(explicit_id=None, prompt="行程ID：396396 北欧峡湾") == "396396"
    assert _resolve_itinerary_id(explicit_id=None, prompt="海报编号 ID: 202607A") == "202607A"

    assert _text_fidelity_passed("虽然主标题清晰，但副标题缺失。\n结论：不通过") is False
    assert _text_fidelity_passed("逐字核对一致。\n结论：通过") is True


def test_request_id_sanitization_and_local_anonymous_endpoints(settings_factory) -> None:
    settings = settings_factory(auth_enabled=False)
    app = create_app(settings)
    with TestClient(app) as client:
        injected = client.get("/api/health", headers={"X-Request-ID": "bad\r\nid\x00value"})
        assert injected.status_code == 200
        assert injected.headers["X-Request-ID"] != "bad\r\nid\x00value"
        assert re.fullmatch(r"[A-Za-z0-9._-]{8,64}", injected.headers["X-Request-ID"])

        usage = client.get("/api/usage")
        assert usage.status_code == 200
        assert usage.json()["current_user"] is None

        overflow = client.get(f"/api/generated-images/{1 << 80}")
        assert overflow.status_code == 422


def test_frontend_phone_photo_size_clamping_url_sanitization_and_itinerary_stops() -> None:
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")

    def extract_fn(name: str) -> str:
        start = re.search(rf"^function {name}\(", app_js, re.MULTILINE)
        assert start is not None, name
        end = re.search(r"^(?:async )?function |^const state = \{", app_js[start.end() :], re.MULTILINE)
        assert end is not None, name
        return app_js[start.start() : start.end() + end.start()]

    snippets = "\n".join(
        [
            extract_fn("simpleEditSourceSize"),
            extract_fn("isItineraryInstructionSection"),
            extract_fn("isItineraryInstructionRow"),
            extract_fn("cleanItineraryStopName"),
            extract_fn("parseItineraryTextStops"),
        ]
    )
    script = f"""
import {{
  classifyReviewPanelTone,
  formatHumanDurationMs,
  sanitizeDownloadHref,
}} from './static/url-safety.mjs';
import {{
  extractSimpleVisibleTextItems,
  resolveSimpleScenarioBadge,
}} from './static/simple-preview.mjs';
import {{
  countPendingPasswordResets,
  filterAdminUsers,
  formatAdminUserOptionLabel,
}} from './static/admin-console.mjs';

const window = {{ location: {{ origin: "https://picgen.example.com" }} }};
const state = {{ editImage: null }};
{snippets}
const stops = parseItineraryTextStops([
  "Day 1：斯德哥尔摩 → 基律纳冰酒店；交通：飞机；入住：冰酒店",
  "第二天：上海交通大学 → 文化活动中心；重点：校园人文漫步",
].join("\\n"));
const previewItems = extractSimpleVisibleTextItems(
  {{
    id: "travel-poster-premium",
    scene_card: {{
      default_size: "1088x2240",
      submit: {{ kind: "generate" }},
      fields: [
        {{ name: "title", label: "主标题", kind: "text" }},
        {{ name: "highlights", label: "亮点", kind: "list" }},
        {{ name: "atmosphere", label: "画面氛围", kind: "chips" }},
      ],
    }},
  }},
  {{
    title: "金秋北疆·喀纳斯",
    highlights: ["禾木晨雾木屋", "赛里木湖环湖包车", ""],
    atmosphere: ["高级旅行"],
  }},
);
const users = [
  {{ id: 1, username: "admin", display_name: "主理人", company: "6renyou", department: "PD & OPS", role: "admin" }},
  {{
    id: 12,
    username: "linnea",
    display_name: "林奈",
    company: "6renyou",
    department: "Bespoke Travel",
    role: "user",
  }},
];
console.log(JSON.stringify({{
  iphone4k: simpleEditSourceSize({{ width: 4032, height: 3024 }}),
  normal: simpleEditSourceSize({{ width: 1088, height: 2240 }}),
  panorama: simpleEditSourceSize({{ width: 1000, height: 4500 }}),
  jsHref: sanitizeDownloadHref("javascript:alert(1)", "https://picgen.example.com"),
  protoRelativeHref: sanitizeDownloadHref("//evil.example/a.png", "https://picgen.example.com"),
  htmlDataHref: sanitizeDownloadHref("data:text/html;base64,PHNjcmlwdD4=", "https://picgen.example.com"),
  pngDataHref: sanitizeDownloadHref("data:image/png;base64,AAAA", "https://picgen.example.com"),
  localFileHref: sanitizeDownloadHref("/files/outputs/20260712/a.png", "https://picgen.example.com"),
  stopNames: stops.map((item) => item.name),
  durationShort: formatHumanDurationMs(14231.4),
  durationLong: formatHumanDurationMs(125400),
  tonePass: classifyReviewPanelTone("低风险", "未发现明显侵权标志"),
  toneStructuredPass: classifyReviewPanelTone("文字通过", "结论：通过\\n缺失或疑似错误：无\\n残留旧文字：无"),
  toneWarn: classifyReviewPanelTone("不通过", "发现 1 处错字"),
  tonePending: classifyReviewPanelTone("等待检查", "准备中"),
  previewItems,
  posterBadge: resolveSimpleScenarioBadge({{
    id: "travel-poster-premium",
    scene_card: {{ submit: {{ kind: "generate" }} }},
  }}),
  editBadge: resolveSimpleScenarioBadge({{ id: "image-edit", scene_card: {{ submit: {{ kind: "edit" }} }} }}),
  filteredByDept: filterAdminUsers(users, "bespoke").map((u) => u.id),
  filteredById: filterAdminUsers(users, "#12").map((u) => u.id),
  optionLabel: formatAdminUserOptionLabel(users[1]),
  pendingResets: countPendingPasswordResets([{{ id: 1 }}, {{ id: 2 }}]),
}}));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    w_str, h_str = result["iphone4k"].split("x")
    w, h = int(w_str), int(h_str)
    assert w <= 3840 and h <= 3840
    assert w * h <= 8_294_400
    assert abs((w / h) - (4032 / 3024)) < 0.01
    assert result["normal"] == "1088x2240"
    assert result["panorama"] == "auto"
    assert result["jsHref"] == ""
    assert result["protoRelativeHref"] == ""
    assert result["htmlDataHref"] == ""
    assert result["pngDataHref"] == "data:image/png;base64,AAAA"
    assert result["localFileHref"] == "/files/outputs/20260712/a.png"
    assert result["stopNames"] == ["斯德哥尔摩", "基律纳冰酒店", "上海交通大学", "文化活动中心"]
    assert result["durationShort"] == "14.2s"
    assert result["durationLong"] == "2分 5秒"
    assert result["tonePass"] == "pass"
    assert result["toneStructuredPass"] == "pass"
    assert result["toneWarn"] == "warn"
    assert result["tonePending"] == "pending"
    assert len(result["previewItems"]) == 3
    assert result["previewItems"][0] == {"label": "主标题", "text": "金秋北疆·喀纳斯"}
    assert result["posterBadge"] == "9:19 手机海报"
    assert result["editBadge"] == "保持原图比例"
    assert result["filteredByDept"] == [12]
    assert result["filteredById"] == [12]
    assert "林奈 (@linnea)" in result["optionLabel"]
    assert "(ID #12)" in result["optionLabel"]
    assert result["pendingResets"] == 2


def test_logo_placement_avoids_very_dark_backgrounds_and_icons_svg_is_valid() -> None:
    icons_svg = (ROOT_DIR / "static" / "icons.svg").read_text(encoding="utf-8")
    assert 'stroke-width="none"' not in icons_svg

    script = """
import { calculateLogoPlacementScore, chooseLogoPlacement } from './static/logo-placement.mjs';
const placements = [
  { x: 42, y: 42, width: 174, height: 54 },
  { x: 42, y: 120, width: 174, height: 54 },
];
const ctx = {
  canvas: { width: 1088, height: 2240 },
  getImageData: (_originX, originY, width, height) => {
    const data = new Uint8ClampedArray(width * height * 4);
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const absoluteY = originY + y;
        const value = absoluteY < 105 ? 12 : 168;
        const idx = (y * width + x) * 4;
        data[idx] = value;
        data[idx + 1] = value;
        data[idx + 2] = value;
        data[idx + 3] = 255;
      }
    }
    return { data };
  },
};
const scored = placements.map((placement) => ({
  placement,
  score: calculateLogoPlacementScore(ctx, ctx.canvas, placement),
}));
console.log(JSON.stringify({ scored, chosen: chooseLogoPlacement(scored) }));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    assert result["scored"][0]["score"] > result["scored"][1]["score"] + 2
    assert result["chosen"] == {"x": 42, "y": 120, "width": 174, "height": 54}


def test_itinerary_pil_rasterizer_speed_and_largest_gap_antimeridian_unwrap() -> None:
    stops = [
        {"date": "D1", "name": "London", "lat": 51.5074, "lng": -0.1278, "status": "ok"},
        {"date": "D3", "name": "Tokyo", "lat": 35.6762, "lng": 139.6503, "status": "ok"},
        {"date": "D6", "name": "Honolulu", "lat": 21.3069, "lng": -157.8583, "status": "ok"},
    ]
    projected = _project_stops(stops, width=1792, height=1792)
    xs = [float(pt["x"]) for pt in projected]
    assert xs[0] < xs[1] < xs[2], f"Expected West->East order London < Tokyo < Honolulu, got {xs}"

    t0 = time.perf_counter()
    png_bytes = render_itinerary_control_png({"stops": stops}, width=1792, height=1792)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 1500, f"Expected fast C-accelerated PIL rasterizer, took {elapsed_ms:.1f}ms"
    with Image.open(io.BytesIO(png_bytes)) as img:
        assert img.size == (1792, 1792)
        assert img.mode == "RGB"


def test_ssrf_blocks_cloud_metadata_and_link_local_endpoints() -> None:
    for blocked in (
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://0.0.0.0:8000/v1/images/generations",
        "http://[fe80::1]/v1/images/generations",
    ):
        with pytest.raises(APIError):
            validate_url(blocked, "生成接口 URL")


def test_incremental_sse_consumer_streams_final_image_without_buffering_partials() -> None:
    huge_partial = "A" * 200_000
    chunks = [
        (
            "event: response.image_generation_call.partial_image\n"
            f'data: {{"type":"response.image_generation_call.partial_image","partial_image_b64":"{huge_partial}"}}\n\n'
        ).encode(),
        b"event: response.output_item.done\n",
        (
            b'data: {"type":"response.output_item.done",'
            b'"item":{"type":"image_generation_call","result":"iVBORw0KGgo="}}\n\n'
        ),
        b"data: [DONE]\n\n",
    ]

    async def byte_stream():
        for chunk in chunks:
            yield chunk

    payload = asyncio.run(
        consume_sse_stream_to_image_payload(
            byte_stream(),
            url="https://sub.tidba.com/v1/responses",
            started_at=time.perf_counter(),
            expect_image=True,
        )
    )
    assert payload["data"][0]["b64_json"] == "iVBORw0KGgo="
    assert huge_partial[:128] not in json.dumps(payload)


def test_same_origin_csrf_middleware_and_session_last_seen_throttling(settings_factory) -> None:
    settings = settings_factory(auth_enabled=True)
    app = create_app(settings)
    store: AuthStore = app.state.auth_store
    user = store.create_user("csrf_tester", "ValidPass123!")
    _, session = store.authenticate_and_create_session("csrf_tester", "ValidPass123!", days=7)
    token = session.token

    first_resolved = store.user_for_session(token)
    assert first_resolved is not None and first_resolved.id == user.id
    with store._connect() as conn:
        first_seen = conn.execute("SELECT last_seen_at FROM sessions").fetchone()["last_seen_at"]
    second_resolved = store.user_for_session(token)
    assert second_resolved is not None and second_resolved.id == user.id
    with store._connect() as conn:
        second_seen = conn.execute("SELECT last_seen_at FROM sessions").fetchone()["last_seen_at"]
    assert second_seen == first_seen

    with TestClient(app) as client:
        client.cookies.set("picgen_session", token)
        cross_origin = client.post(
            "/api/auth/logout",
            headers={"Origin": "https://evil-attacker.example"},
        )
        assert cross_origin.status_code == 403
        assert cross_origin.json()["code"] == "csrf_rejected"

        same_origin = client.post(
            "/api/auth/logout",
            headers={"Origin": "http://testserver"},
        )
        assert same_origin.status_code == 200


def test_ui_ux_phase2_dom_and_simple_mode_inline_preview_contracts() -> None:
    index_html = (ROOT_DIR / "static" / "index.html").read_text(encoding="utf-8")
    app_js = (ROOT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    styles_css = (ROOT_DIR / "static" / "styles.css").read_text(encoding="utf-8")

    for required_id in (
        "accountMenuWrap",
        "accountMenuTrigger",
        "accountDropdownMenu",
        "openAdminConsoleButton",
        "railAssetTabs",
        "simpleTextPreviewCard",
        "simpleTextPreviewList",
        "editTargetSizeBadge",
        "adminConsoleModal",
        "adminOrgUserSelect",
        "adminUserSearchInput",
    ):
        assert f'id="{required_id}"' in index_html

    confirm_fn = app_js[
        app_js.index("async function confirmPromptBeforeRun") : app_js.index("function updateGenerateSampleCountUI")
    ]
    assert 'if (state.uiMode === "simple")' in confirm_fn
    assert ".admin-console-dialog" in styles_css
    assert ".account-dropdown-menu" in styles_css
    assert ".simple-text-preview" in styles_css

    topbar_block = re.search(r"(?m)^\.app-topbar\s*\{([^}]+)\}", styles_css)
    assert topbar_block is not None
    topbar_body = topbar_block.group(1)
    assert "position: relative;" in topbar_body
    topbar_z = re.search(r"z-index:\s*(\d+)\s*;", topbar_body)
    assert topbar_z is not None and 20 <= int(topbar_z.group(1)) < 50
    assert ".account-dropdown-menu.align-left" in styles_css
    assert "syncAccountDropdownAlignment" in app_js


from __future__ import annotations

import base64
import json
import math
import re
import sqlite3
from io import BytesIO
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.types import Scope

from picgen.errors import APIError
from picgen.itinerary_map import build_itinerary_map_plan, project_itinerary_points, render_itinerary_map_svg
from picgen.main import create_app
from picgen.middleware import BodySizeLimitMiddleware
from picgen.notifications import NotificationResult
from picgen.routes import _with_timing
from picgen.upstream import parse_sse_json_events, stream_events_to_image_payload

TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"


def png_b64_with_dimensions(width: int, height: int) -> str:
    image = bytearray(base64.b64decode(TINY_PNG_B64))
    image[16:20] = width.to_bytes(4, "big")
    image[20:24] = height.to_bytes(4, "big")
    return base64.b64encode(image).decode("ascii")


def valid_png_b64(width: int, height: int, color: tuple[int, int, int] = (60, 120, 220)) -> str:
    output = BytesIO()
    Image.new("RGB", (width, height), color).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def test_health_endpoint_reports_ok(make_client):
    client, _, _ = make_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_ready_endpoint_reports_dependencies(make_client):
    client, _, _ = make_client()
    response = client.get("/api/ready")
    assert response.status_code == 200
    payload = response.json()
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    version_line = next(line for line in pyproject.splitlines() if line.startswith("version = "))
    expected_version = version_line.split('"', 2)[1]
    assert payload["ok"] is True
    assert payload["storage_writable"] is True
    assert payload["upstream_client_ready"] is True
    assert payload["version"] == expected_version


def test_config_reports_api_key_presence_without_leaking_value(make_client, settings_factory):
    settings = settings_factory(
        default_api_key="sk-secret",
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-100123456",
        smtp_host="smtpdm.aliyun.com",
        smtp_username="noreply@example.com",
        smtp_password="mail-secret",
        smtp_from_email="noreply@example.com",
        public_base_url="https://picgen.example.com",
        map_provider="mapbox",
        mapbox_token="map-secret-token",
    )
    client, _, _ = make_client(settings=settings)
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["has_default_api_key"] is True
    assert payload["responses_url"] == "https://sub.tidba.com/v1/responses"
    assert payload["default_responses_model"] == "gpt-5.6-sol"
    assert payload["default_size"] == "1088x2240"
    assert "sk-secret" not in response.text
    assert "123:abc" not in response.text
    assert "-100123456" not in response.text
    assert payload["max_image_bytes"] > 0
    assert payload["upstream_timeout_seconds"] > 0
    assert payload["error_alert_notifications_enabled"] is True
    assert payload["bug_report_notifications_enabled"] is True
    assert payload["password_reset_email_enabled"] is True
    assert payload["map_provider"] == "mapbox"
    assert payload["map_geocoding_enabled"] is True
    assert "mail-secret" not in response.text
    assert "map-secret-token" not in response.text


def test_config_disables_password_reset_email_without_public_base_url(make_client, settings_factory):
    settings = settings_factory(
        smtp_host="smtpdm.aliyun.com",
        smtp_username="noreply@example.com",
        smtp_password="mail-secret",
        smtp_from_email="noreply@example.com",
        public_base_url="",
    )
    client, _, _ = make_client(settings=settings)

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["password_reset_email_enabled"] is False


def test_config_reports_default_geocoder_enabled(make_client):
    client, _, _ = make_client()
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["map_provider"] == "nominatim"
    assert payload["map_geocoding_enabled"] is True


def test_config_reports_custom_responses_url(make_client, settings_factory):
    settings = settings_factory(default_responses_url="https://sub.tidba.com/v1/responses")
    client, _, _ = make_client(settings=settings)
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json()["responses_url"] == "https://sub.tidba.com/v1/responses"


def test_recipes_endpoint_requires_login_and_lists_prompt_recipes(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password="correct horse battery admin")
    client, _, _ = make_client(settings=settings)

    anonymous = client.get("/api/recipes")
    assert anonymous.status_code == 401

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200
    response = client.get("/api/recipes")

    assert response.status_code == 200
    recipes = response.json()["recipes"]
    assert {recipe["id"] for recipe in recipes} >= {
        "travel-poster-premium",
        "hotel-texture",
        "route-map-comic",
    }
    travel_recipe = next(recipe for recipe in recipes if recipe["id"] == "travel-poster-premium")
    assert travel_recipe["mode"] == "generate"
    assert travel_recipe["prompt_suffix"]
    assert "recommended_keywords" in travel_recipe


def test_recipes_endpoint_allows_no_auth_mode(make_client, settings_factory):
    settings = settings_factory(auth_enabled=False)
    client, _, _ = make_client(settings=settings)

    response = client.get("/api/recipes")

    assert response.status_code == 200
    assert {recipe["id"] for recipe in response.json()["recipes"]} >= {
        "travel-poster-premium",
        "hotel-texture",
        "route-map-comic",
    }


def test_removed_prompt_detour_endpoints_are_not_exposed(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password="correct horse battery admin")
    client, _, _ = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    for path in ("/api/prompt/optimize", "/api/prompt/repetition-check", "/api/poster-layout/render"):
        assert not any(
            route.path == path and "POST" in (getattr(route, "methods", None) or set())
            for route in client.app.routes
        )
        response = client.post(path, json={"prompt": "柏林博物馆旅行海报", "title": "柏林博物馆旅行海报"})
        assert response.status_code in {404, 405}


def test_success_templates_endpoint_lists_current_users_good_feedback(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200
    prompt = "京都红叶高级旅行海报，酒店质感，色彩克制"
    generated = client.post("/api/generate", json={"prompt": prompt, "model": "gpt-image-2"})
    assert generated.status_code == 200
    good = client.post(
        "/api/feedback",
        json={
            "rating": "good",
            "reason": "这个版式可以复用",
            "prompt": prompt,
            "mode": "generate",
            "model": "gpt-image-2",
            "generated_image_id": generated.json()["generated_image_id"],
        },
    )
    assert good.status_code == 200
    bad = client.post(
        "/api/feedback",
        json={
            "rating": "bad",
            "reason": "不要作为模板",
            "prompt": "失败提示词",
            "mode": "generate",
            "model": "gpt-image-2",
            "generated_image_id": generated.json()["generated_image_id"],
        },
    )
    assert bad.status_code == 200

    response = client.get("/api/success-templates")

    assert response.status_code == 200
    templates = response.json()["templates"]
    assert len(templates) == 1
    assert templates[0]["prompt"] == prompt
    assert templates[0]["title"] == "这个版式可以复用"
    assert templates[0]["source"] == "good_feedback"
    assert "失败提示词" not in response.text


def test_request_id_is_round_tripped(make_client):
    client, _, _ = make_client()
    response = client.get("/api/health", headers={"X-Request-ID": "abc1234567"})
    assert response.headers["x-request-id"] == "abc1234567"


def test_request_id_is_generated_when_missing(make_client):
    client, _, _ = make_client()
    response = client.get("/api/health")
    rid = response.headers.get("x-request-id", "")
    assert 8 <= len(rid) <= 64


def test_unhandled_500_keeps_request_id_in_response(settings_factory):
    settings = settings_factory(static_dir=Path("/tmp/picgen-missing-static"))
    app = create_app(settings)

    @app.get("/api/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/boom", headers={"X-Request-ID": "rid-unhandled-500"})

    assert response.status_code == 500
    assert response.headers["x-request-id"] == "rid-unhandled-500"
    assert response.json()["request_id"] == "rid-unhandled-500"


def test_security_headers_are_set(make_client):
    client, _, _ = make_client()
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_generate_requires_prompt_before_api_key(make_client):
    client, _, _ = make_client()
    response = client.post("/api/generate", json={"api_key": "sk-test"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "生成提示词不能为空"
    assert body["code"] == "validation_error"


def test_generate_defaults_to_one_candidate_without_sample_count(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_count"] == 1
    assert payload["candidate_count"] == 1
    # Persisted images are served from the saved file URL; the heavy inline data
    # URL is dropped to keep the response small.
    assert payload["saved_image_url"].startswith("files/outputs/")
    assert payload["image_data_url"] is None
    assert payload["images"][0]["image_data_url"] is None

    upstream_payload = fake.run_json.await_args.args[2]
    assert "n" not in upstream_payload
    assert upstream_payload["quality"] == "high"
    assert "硬性目的地限制" in upstream_payload["prompt"]
    assert "Vatican City" in upstream_payload["prompt"]


def test_generate_normalizes_mismatched_poster_size_from_upstream(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {
        "data": [{"b64_json": valid_png_b64(10, 20)}],
        "created": 1,
    }

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成一张 6 人游竖版旅行海报",
            "model": "gpt-image-2",
            "size": "20x40",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["size"] == "20x40"
    assert payload["requested_size"] == "20x40"
    assert payload["saved_image_width"] == 20
    assert payload["saved_image_height"] == 40
    assert payload["actual_size"] == "20x40"
    assert payload["upstream_actual_size"] == "10x20"
    assert payload["image_size_normalized"] is True
    assert payload["size_mismatch"] is False
    assert payload["images"][0]["saved_image_width"] == 20
    assert payload["images"][0]["saved_image_height"] == 40
    assert payload["images"][0]["actual_size"] == "20x40"
    assert payload["images"][0]["upstream_actual_size"] == "10x20"
    assert payload["images"][0]["image_size_normalized"] is True
    assert payload["images"][0]["size_mismatch"] is False
    assert payload["saved_image_url"].startswith("files/outputs/")


def test_generate_normalizes_default_poster_size_when_size_omitted(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test", default_size="20x40")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {
        "data": [{"b64_json": valid_png_b64(10, 20)}],
        "created": 1,
    }

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成一张 6 人游竖版旅行海报",
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved_image_width"] == 20
    assert payload["saved_image_height"] == 40
    assert payload["upstream_actual_size"] == "10x20"
    assert payload["image_size_normalized"] is True


def test_generate_rejects_oversized_exact_canvas(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成一张超大海报",
            "model": "gpt-image-2",
            "size": "99999x99999",
        },
    )

    assert response.status_code == 400
    assert fake.run_json.await_count == 0
    assert "尺寸" in response.json()["error"]


def test_generate_rejects_restricted_destination_without_upstream_call(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)

    response = client.post(
        "/api/generate",
        json={
            "prompt": "罗马高端旅行海报，包含梵蒂冈博物馆和圣彼得广场",
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "restricted_destination"
    assert "受限目的地" in body["error"]
    assert "梵蒂冈" not in body["error"]
    assert fake.run_json.await_count == 0


def test_generate_allows_restricted_destination_exclusion_text(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/generate",
        json={
            "prompt": (
                "柏林博物馆旅行海报，现代杂志风。"
                "不得出现、标注或暗示 Vatican City、Holy See、梵蒂冈、圣座。"
            ),
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 200
    assert fake.run_json.await_count == 1
    upstream_prompt = fake.run_json.await_args.args[2]["prompt"]
    assert upstream_prompt.startswith("柏林博物馆旅行海报")
    assert "不得出现、标注或暗示 Vatican City" in upstream_prompt
    assert "硬性目的地限制" in upstream_prompt


def test_generate_sends_text_heavy_poster_prompt_to_ai_upstream(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/generate",
        json={
            "prompt": (
                "柏林博物馆必去榜 10家不去真的会后悔\n"
                "01 新博物馆 纳芙蒂蒂半身像\n"
                "02 佩加蒙博物馆 巴比伦伊什塔尔城门\n"
                "03 博德博物馆 雕塑和拜占庭艺术\n"
                "04 老国家美术馆 德国浪漫主义绘画"
            ),
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 200
    assert fake.run_json.await_count == 1
    upstream_prompt = fake.run_json.await_args.args[2]["prompt"]
    assert "柏林博物馆必去榜" in upstream_prompt
    assert "04 老国家美术馆" in upstream_prompt
    assert "硬性目的地限制" in upstream_prompt


def test_generate_rejects_legacy_program_layout_background_prompt(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)

    response = client.post(
        "/api/generate",
        json={
            "prompt": (
                "为一张小红书封面「柏林博物馆必去榜」生成无文字背景底图，"
                "用于后续程序排版中文标题、副标题、双栏榜单卡片、编号、馆名和推荐语。"
                "整体留白充足，不生成任何可读文字、字母、数字、表格、编号、标签、LOGO 或招牌。"
            ),
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "legacy_layout_background_prompt"
    assert "旧程序排版背景底图提示词" in body["error"]
    assert fake.run_json.await_count == 0


def test_itinerary_map_plan_rejects_restricted_destination_text_and_coordinates(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password="correct horse battery admin")
    client, _, _ = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeuser", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    text_response = client.post(
        "/api/itinerary-map/plan",
        json={
            "title": "意大利路线",
            "subtitle": "9/1 - 9/5",
            "stops": [
                {"date": "9/1", "name": "罗马", "lat": 41.9028, "lng": 12.4964},
                {"date": "9/2", "name": "Vatican City", "lat": 41.9029, "lng": 12.4534},
            ],
        },
    )
    coord_response = client.post(
        "/api/itinerary-map/plan",
        json={
            "title": "意大利路线",
            "subtitle": "9/1 - 9/5",
            "stops": [
                {"date": "9/1", "name": "罗马", "lat": 41.9028, "lng": 12.4964},
                {"date": "9/2", "name": "无名地点", "lat": 41.9029, "lng": 12.4534},
            ],
        },
    )

    assert text_response.status_code == 400
    assert text_response.json()["code"] == "restricted_destination"
    assert coord_response.status_code == 400
    assert coord_response.json()["code"] == "restricted_destination"


def test_generate_records_free_prompt_lineage_without_rewriting(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, resolved_settings = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    prompt = "一张完全由专业用户自己控制的精确提示词，不要套模板"
    response = client.post(
        "/api/generate",
        json={
            "prompt": prompt,
            "model": "gpt-image-2",
            "prompt_mode": "free",
            "original_prompt": prompt,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["prompt"] == prompt
    assert payload["prompt_mode"] == "free"
    assert payload["original_prompt"] == prompt
    assert payload["effective_prompt"] == prompt
    upstream_payload = fake.run_json.await_args.args[2]
    assert upstream_payload["prompt"].startswith(prompt)
    assert "硬性目的地限制" in upstream_payload["prompt"]

    detail_response = client.get(f"/api/generated-images/{payload['generated_image_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["image"]
    assert detail["lineage"]["prompt_mode"] == "free"
    assert detail["lineage"]["original_prompt"] == prompt
    assert detail["lineage"]["effective_prompt"] == prompt
    assert detail["metadata"]["prompt_mode"] == "free"

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT prompt, original_prompt, prompt_mode, recipe_id
            FROM generation_jobs
            WHERE id = ?
            """,
            (payload["generation_job_id"],),
        ).fetchone()
    assert row["prompt"] == prompt
    assert row["original_prompt"] == prompt
    assert row["prompt_mode"] == "free"
    assert row["recipe_id"] == ""


def test_generate_adds_itinerary_id_badge_from_explicit_field_or_prompt(
    make_client,
    settings_factory,
):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    explicit_response = client.post(
        "/api/generate",
        json={
            "prompt": "小小国宝守护记，和大熊猫交个朋友",
            "model": "gpt-image-2",
            "itinerary_id": "396396",
        },
    )
    assert explicit_response.status_code == 200
    explicit_payload = fake.run_json.await_args.args[2]
    assert "行程 ID：396396" in explicit_payload["prompt"]
    assert "右上角" in explicit_payload["prompt"]
    assert "左上角 LOGO" in explicit_payload["prompt"]

    prompt_response = client.post(
        "/api/generate",
        json={
            "prompt": "行程ID: 778899\n亲子研学海报，远观熊猫",
            "model": "gpt-image-2",
        },
    )
    assert prompt_response.status_code == 200
    prompt_payload = fake.run_json.await_args.args[2]
    assert "行程 ID：778899" in prompt_payload["prompt"]
    assert "右上角" in prompt_payload["prompt"]


def test_generate_records_recipe_lineage_and_detail_is_owner_scoped(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    first_register = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert first_register.status_code == 200

    original_prompt = "京都高端红叶私家团，面向家庭客户，真实目的地质感"
    effective_prompt = f"{original_prompt}\n\n配方辅助：高级旅行商业海报；真实目的地氛围；色彩克制。"
    response = client.post(
        "/api/generate",
        json={
            "prompt": effective_prompt,
            "original_prompt": original_prompt,
            "prompt_mode": "recipe",
            "recipe_id": "travel-poster-premium",
            "recipe_version": "2026-06-08",
            "model": "gpt-image-2",
        },
    )
    assert response.status_code == 200
    generated = response.json()
    assert generated["prompt_mode"] == "recipe"
    assert generated["original_prompt"] == original_prompt
    assert generated["effective_prompt"] == effective_prompt
    assert generated["recipe"]["id"] == "travel-poster-premium"

    client.post("/api/auth/logout")
    second_register = client.post(
        "/api/auth/register",
        json={"username": "bob", "password": "correct horse battery"},
    )
    assert second_register.status_code == 200
    forbidden = client.get(f"/api/generated-images/{generated['generated_image_id']}")
    assert forbidden.status_code == 404

    client.post("/api/auth/logout")
    login = client.post("/api/auth/login", json={"username": "alice", "password": "correct horse battery"})
    assert login.status_code == 200
    detail_response = client.get(f"/api/generated-images/{generated['generated_image_id']}")
    assert detail_response.status_code == 200
    lineage = detail_response.json()["image"]["lineage"]
    assert lineage["prompt_mode"] == "recipe"
    assert lineage["recipe_id"] == "travel-poster-premium"
    assert lineage["recipe_version"] == "2026-06-08"
    assert lineage["original_prompt"] == original_prompt
    assert lineage["effective_prompt"] == effective_prompt


def test_edit_records_source_image_and_lists_version_chain(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, resolved_settings = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": png_b64_with_dimensions(1088, 2240)}], "created": 1}
    fake.run_multipart.return_value = {"data": [{"b64_json": png_b64_with_dimensions(1088, 2240)}], "created": 2}

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200
    original = client.post(
        "/api/generate",
        json={"prompt": "法国意大利瑞士高端路线海报", "model": "gpt-image-2"},
    )
    assert original.status_code == 200
    original_id = original.json()["generated_image_id"]

    edited = client.post(
        "/api/edit",
        json={
            "prompt": "改成更温柔的羊皮纸地图风格",
            "model": "gpt-image-2",
            "source_generated_image_id": original_id,
            "image": {
                "name": "source.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )
    assert edited.status_code == 200
    edited_id = edited.json()["generated_image_id"]
    assert edited_id != original_id

    versions_response = client.get(f"/api/generated-images/{edited_id}/versions")
    assert versions_response.status_code == 200
    payload = versions_response.json()
    assert payload["current_generated_image_id"] == edited_id
    assert [item["generated_image_id"] for item in payload["versions"]] == [original_id, edited_id]
    assert payload["versions"][0]["source_generated_image_id"] is None
    assert payload["versions"][0]["version_depth"] == 0
    assert payload["versions"][1]["source_generated_image_id"] == original_id
    assert payload["versions"][1]["version_depth"] == 1
    assert payload["versions"][1]["lineage"]["effective_prompt"] == "改成更温柔的羊皮纸地图风格"

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT source_generated_image_id FROM generated_images WHERE id = ?",
            (edited_id,),
        ).fetchone()
    assert row["source_generated_image_id"] == original_id

    client.post("/api/auth/logout")
    bob = client.post(
        "/api/auth/register",
        json={"username": "bob", "password": "correct horse battery"},
    )
    assert bob.status_code == 200
    forbidden = client.get(f"/api/generated-images/{edited_id}/versions")
    assert forbidden.status_code == 404


def test_edit_records_source_image_and_requested_size_in_job_metadata(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, resolved_settings = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": png_b64_with_dimensions(1088, 2240)}], "created": 1}
    fake.run_multipart.return_value = {"data": [{"b64_json": png_b64_with_dimensions(1088, 2240)}], "created": 2}

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200
    original = client.post(
        "/api/generate",
        json={"prompt": "西班牙味觉地图", "model": "gpt-image-2", "size": "1088x2240"},
    )
    assert original.status_code == 200
    original_id = original.json()["generated_image_id"]

    edited = client.post(
        "/api/edit",
        json={
            "prompt": "把“铁帆鱿鱼”改成“铁煎章鱼”，其他不要动",
            "model": "gpt-image-2",
            "size": "1088x2240",
            "quality": "high",
            "source_generated_image_id": original_id,
            "image": {
                "name": "source.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )
    assert edited.status_code == 200
    payload = edited.json()
    assert payload["source_generated_image_id"] == original_id
    assert payload["requested_size"] == "1088x2240"

    upstream_fields = fake.run_multipart.await_args.args[2]
    assert upstream_fields["size"] == "1088x2240"
    assert upstream_fields["quality"] == "high"

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        image_row = conn.execute(
            "SELECT source_generated_image_id FROM generated_images WHERE id = ?",
            (payload["generated_image_id"],),
        ).fetchone()
        job_row = conn.execute(
            "SELECT mode, size FROM generation_jobs WHERE id = ?",
            (payload["generation_job_id"],),
        ).fetchone()

    assert image_row["source_generated_image_id"] == original_id
    assert job_row["mode"] == "edit"
    assert job_row["size"] == "1088x2240"


def test_generate_rejects_unknown_prompt_recipe_without_upstream_call(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/generate",
        json={
            "prompt": "高级旅行海报",
            "original_prompt": "高级旅行海报",
            "prompt_mode": "recipe",
            "recipe_id": "not-a-real-recipe",
            "recipe_version": "2026-06-08",
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    fake.run_json.assert_not_awaited()

    jobs_response = client.get("/api/jobs")
    assert jobs_response.status_code == 200
    job = jobs_response.json()["jobs"][0]
    assert job["status"] == "failed"
    assert job["prompt_mode"] == "recipe"
    assert job["recipe_id"] == ""


def test_generation_jobs_endpoint_lists_current_user_jobs_only(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {
        "data": [{"b64_json": png_b64_with_dimensions(1088, 2240)}],
        "created": 1,
    }

    alice_register = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert alice_register.status_code == 200
    alice_generate = client.post(
        "/api/generate",
        json={
            "prompt": "京都红叶高级海报",
            "original_prompt": "京都红叶高级海报",
            "prompt_mode": "recipe",
            "recipe_id": "travel-poster-premium",
            "recipe_version": "2026-06-08",
            "model": "gpt-image-2",
            "size": "1088x2240",
        },
    )
    assert alice_generate.status_code == 200

    jobs_response = client.get("/api/jobs")
    assert jobs_response.status_code == 200
    jobs = jobs_response.json()["jobs"]
    assert len(jobs) == 1
    assert jobs[0]["prompt_mode"] == "recipe"
    assert jobs[0]["recipe_id"] == "travel-poster-premium"
    assert jobs[0]["first_generated_image_id"] == alice_generate.json()["generated_image_id"]
    assert jobs[0]["first_saved_image_url"].startswith("files/outputs/")

    client.post("/api/auth/logout")
    bob_register = client.post(
        "/api/auth/register",
        json={"username": "bob", "password": "correct horse battery"},
    )
    assert bob_register.status_code == 200
    bob_jobs = client.get("/api/jobs")
    assert bob_jobs.status_code == 200
    assert bob_jobs.json()["jobs"] == []


def test_generate_preserves_itinerary_mode_in_response_and_database(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, fake, resolved_settings = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/generate",
        json={
            "prompt": "生成新疆行程地图，必须保持地点真实相对位置",
            "model": "gpt-image-2",
            "mode": "itinerary",
            "size": "1792x1792",
            "logo_requested": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "itinerary"
    assert payload["saved_image_name"].startswith("routeplanner-itinerary-")

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        job = conn.execute("SELECT * FROM generation_jobs").fetchone()
        image = conn.execute("SELECT * FROM generated_images").fetchone()

    assert job["mode"] == "itinerary"
    assert job["transport"] == "images-generate"
    assert job["logo_requested"] == 1
    assert image["mode"] == "itinerary"
    assert image["saved_image_name"].startswith("routeplanner-itinerary-")


def test_itinerary_map_plan_requires_coordinates_before_rendering(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        nominatim_url="",
    )
    client, _, _ = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/plan",
        json={
            "title": "多彩新疆游",
            "subtitle": "5/12 - 5/24",
            "stops": [
                {"date": "5/12", "name": "乌鲁木齐", "lat": 43.8256, "lng": 87.6168},
                {"date": "5/13", "name": "赛里木湖"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "needs_confirmation"
    assert payload["stops"][1]["status"] == "needs_coordinates"
    assert "缺少坐标" in payload["warnings"][0]


def test_itinerary_map_render_saves_integrated_ai_artwork_with_geometry_control(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, resolved = make_client(settings=settings)
    (resolved.static_dir / "6renyou.png").write_bytes(base64.b64decode(TINY_PNG_B64))
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    fake.run_file_upload.return_value = {"id": "file_itinerary_control"}
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "日本纵贯路线",
            "subtitle": "9/5 - 9/19",
            "size": "1792x1792",
            "model": "gpt-image-2",
            "stops": [
                {"date": "9/5", "name": "札幌", "lat": 43.0618, "lng": 141.3545, "transport": "抵达"},
                {"date": "9/12", "name": "东京", "lat": 35.6762, "lng": 139.6503, "transport": "火车"},
                {"date": "9/17", "name": "鹿儿岛", "lat": 31.5966, "lng": 130.5571, "transport": "火车"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "itinerary"
    assert payload["transport"] == "responses-itinerary-artwork"
    assert payload["generated_image_id"] > 0
    assert payload["saved_image_url"].startswith("files/outputs/")
    assert payload["saved_image_mime"] == "image/svg+xml"
    assert payload["logo_requested"] is True
    assert payload["logo_overlay_applied"] is False
    assert payload["artwork"]["generated"] is True
    assert payload["artwork"]["mode"] == "ai_background_program_overlay"
    assert payload["size"] == "1792x1792"
    assert payload["requested_size"] == "1792x1792"
    assert payload["composition"]["orientation"] == "square"
    assert payload["composition"]["adjusted"] is False
    assert "手动选择" in payload["composition"]["message"]
    saved = Path(payload["saved_image_path"])
    assert saved.is_file()
    assert saved.is_relative_to(resolved.outputs_dir)
    svg = saved.read_text(encoding="utf-8")
    assert 'data-layer="ai-stylized-map-background"' in svg
    assert 'data-layer="program-route"' in svg
    assert 'data-layer="program-labels"' in svg
    assert "data:image/png;base64," in svg
    assert "札幌" in svg
    assert "东京" in svg
    assert "鹿儿岛" in svg
    fake.run_file_upload.assert_awaited_once()
    assert fake.run_file_upload.await_args.args[2]["filename"] == "itinerary-geometry-control.png"
    assert fake.run_file_upload.await_args.args[2]["content_type"] == "image/png"
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["tools"][0]["size"] == "1792x1792"
    content = upstream_payload["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert "高级漫画旅行路线图底图" in content[0]["text"]
    assert "古典欧洲航海羊皮纸地图" in content[0]["text"]
    assert "不要复刻任何游戏或影视 IP" in content[0]["text"]
    assert "最终路线、编号圆点、日期牌和地点文字会由程序覆盖" in content[0]["text"]
    assert "几何位置锁定" in content[0]["text"]
    assert "像描图纸一样" in content[0]["text"]
    assert "锁定像素坐标" in content[0]["text"]
    assert "编号与站点对应如下" in content[0]["text"]
    assert "01. 9/5｜札幌" in content[0]["text"]
    assert "02. 9/12｜东京" in content[0]["text"]
    assert "03. 9/17｜鹿儿岛" in content[0]["text"]
    assert "不要绘制任何编号圆点" in content[0]["text"]
    assert "不要绘制 LOGO" in content[0]["text"]
    assert "不要生成路线图例" in content[0]["text"]
    assert "Legend" in content[0]["text"]
    assert "线型说明框" in content[0]["text"]
    assert "硬性目的地限制" in content[0]["text"]
    assert "Vatican City" in content[0]["text"]
    assert content[1] == {"type": "input_image", "file_id": "file_itinerary_control"}

    with sqlite3.connect(resolved.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        job = conn.execute(
            "SELECT * FROM generation_jobs WHERE endpoint_path = ?",
            ("/api/itinerary-map/render",),
        ).fetchone()
        image = conn.execute("SELECT * FROM generated_images WHERE id = ?", (payload["generated_image_id"],)).fetchone()
    assert job is not None
    assert job["transport"] == "responses-itinerary-artwork"
    assert job["mode"] == "itinerary"
    assert image is not None
    assert image["saved_image_mime"] == "image/svg+xml"

    file_response = client.get(payload["saved_image_url"])
    assert file_response.status_code == 200
    assert file_response.text.startswith("<svg")


def test_itinerary_map_render_reports_error_when_artwork_returns_text_without_image(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, resolved = make_client(settings=settings)
    (resolved.static_dir / "6renyou.png").write_bytes(base64.b64decode(TINY_PNG_B64))
    fake.run_file_upload.return_value = {"id": "file_itinerary_control"}
    fake.run_responses.return_value = {
        "output_text": "I cannot generate the final image in this response.",
        "stream_events": [{"type": "response.output_text.delta", "delta": "no image"}],
    }
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "欧洲漫画路线",
            "subtitle": "6/1 - 6/8",
            "size": "1792x1792",
            "stops": [
                {"date": "D1", "name": "巴黎", "lat": 48.8566, "lng": 2.3522, "transport": "火车"},
                {"date": "D2", "name": "罗马", "lat": 41.9028, "lng": 12.4964, "transport": "飞机"},
            ],
        },
    )

    assert response.status_code == 502
    payload = response.json()
    assert payload["code"] == "upstream_no_image"
    assert "路线图 AI 底图这次没有生成成功" in payload["error"]
    assert "I cannot generate" not in response.text
    assert fake.run_responses.await_count == 1
    assert not list(resolved.outputs_dir.rglob("*.svg"))


def test_itinerary_map_render_manual_portrait_size_is_not_overridden_by_auto_square(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, resolved = make_client(settings=settings)
    (resolved.static_dir / "6renyou.png").write_bytes(base64.b64decode(TINY_PNG_B64))
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    fake.run_file_upload.return_value = {"id": "file_itinerary_control"}
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "均衡路线手动竖版",
            "subtitle": "8/1 - 8/3",
            "size": "1088x2240",
            "stops": [
                {"date": "8/1", "name": "A", "lat": 30.0, "lng": 120.0, "transport": "抵达"},
                {"date": "8/2", "name": "B", "lat": 32.0, "lng": 122.0, "transport": "自驾"},
                {"date": "8/3", "name": "C", "lat": 31.0, "lng": 121.0, "transport": "活动"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["size"] == "1088x2240"
    assert payload["requested_size"] == "1088x2240"
    assert payload["composition"]["orientation"] == "portrait"
    assert payload["composition"]["adjusted"] is False
    assert "手动选择" in payload["composition"]["message"]
    assert "不会自动改写手动尺寸" in payload["composition"]["message"]
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["tools"][0]["size"] == "1088x2240"


def test_itinerary_map_render_auto_size_selects_landscape_for_wide_route(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, resolved = make_client(settings=settings)
    (resolved.static_dir / "6renyou.png").write_bytes(base64.b64decode(TINY_PNG_B64))
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    fake.run_file_upload.return_value = {"id": "file_itinerary_control"}
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "东西横跨路线",
            "subtitle": "7/1 - 7/3",
            "size": "auto",
            "stops": [
                {"date": "7/1", "name": "里斯本", "lat": 38.7223, "lng": -9.1393, "transport": "抵达"},
                {"date": "7/2", "name": "马德里", "lat": 40.4168, "lng": -3.7038, "transport": "火车"},
                {"date": "7/3", "name": "巴塞罗那", "lat": 41.3874, "lng": 2.1686, "transport": "火车"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["size"] == "1920x1088"
    assert payload["requested_size"] == "auto"
    assert payload["composition"]["orientation"] == "landscape"
    assert payload["composition"]["adjusted"] is True
    assert "东西跨度" in payload["composition"]["message"]
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["tools"][0]["size"] == "1920x1088"


def test_itinerary_map_render_auto_size_keeps_square_for_balanced_route(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, resolved = make_client(settings=settings)
    (resolved.static_dir / "6renyou.png").write_bytes(base64.b64decode(TINY_PNG_B64))
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    fake.run_file_upload.return_value = {"id": "file_itinerary_control"}
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "均衡路线",
            "subtitle": "8/1 - 8/3",
            "size": "auto",
            "stops": [
                {"date": "8/1", "name": "A", "lat": 30.0, "lng": 120.0, "transport": "抵达"},
                {"date": "8/2", "name": "B", "lat": 32.0, "lng": 122.0, "transport": "自驾"},
                {"date": "8/3", "name": "C", "lat": 31.0, "lng": 121.0, "transport": "活动"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["size"] == "1792x1792"
    assert payload["requested_size"] == "auto"
    assert payload["composition"]["orientation"] == "square"
    assert payload["composition"]["adjusted"] is False
    assert "方图" in payload["composition"]["message"]
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["tools"][0]["size"] == "1792x1792"


def test_itinerary_map_render_inlines_style_reference_when_file_upload_fallbacks(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, resolved = make_client(settings=settings)
    (resolved.static_dir / "6renyou.png").write_bytes(base64.b64decode(TINY_PNG_B64))
    style_reference = resolved.static_dir / "itinerary-style-reference.jpg"
    style_reference.write_bytes(base64.b64decode(TINY_PNG_B64) + (b"x" * (900 * 1024)))
    fake.run_file_upload.side_effect = APIError(404, "Files 上传接口不可用")
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "多彩路线图",
            "subtitle": "6/1 - 6/3",
            "size": "1792x1792",
            "stops": [
                {"date": "6/1", "name": "A 城", "lat": 31.2304, "lng": 121.4737, "transport": "抵达"},
                {"date": "6/2", "name": "B 山", "lat": 30.2741, "lng": 120.1551, "transport": "包车"},
                {"date": "6/3", "name": "C 湖", "lat": 29.8683, "lng": 121.5440, "transport": "自驾"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["artwork"]["generated"] is True
    assert fake.run_file_upload.await_count == 1
    assert fake.run_file_upload.await_args.args[2]["filename"] == "itinerary-style-reference.jpg"
    upstream_payload = fake.run_responses.await_args.args[2]
    content = upstream_payload["input"][0]["content"]
    assert len(content) == 3
    assert content[0]["type"] == "input_text"
    assert "第一张输入图只是风格参考" in content[0]["text"]
    assert "第二张输入图是程序按真实经纬度投影出来的硬性地理控制稿" in content[0]["text"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert content[2]["type"] == "input_image"
    assert content[2]["image_url"].startswith("data:image/png;base64,")


def test_itinerary_map_render_succeeds_without_ai_background(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password="correct horse battery admin", default_api_key="")
    client, fake, _ = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "全球旅行路线图",
            "subtitle": "D1 - D2",
            "stops": [
                {"date": "D1", "name": "城市 A", "lat": 35.6812, "lng": 139.7671},
                {"date": "D2", "name": "城市 B", "lat": 34.6937, "lng": 135.5023},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved_image_mime"] == "image/svg+xml"
    assert payload["background_image"]["generated"] is False
    fake.run_json.assert_not_awaited()


def test_itinerary_map_render_fails_when_artwork_payload_is_invalid(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.return_value = {"id": "file_itinerary_control"}
    fake.run_responses.return_value = {"data": [{"b64_json": "not-base64"}], "created": 1}
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "全球旅行路线图",
            "subtitle": "D1 - D2",
            "stops": [
                {"date": "D1", "name": "城市 A", "lat": 35.6812, "lng": 139.7671},
                {"date": "D2", "name": "城市 B", "lat": 34.6937, "lng": 135.5023},
            ],
        },
    )

    assert response.status_code == 502
    payload = response.json()
    assert payload["code"] == "upstream_error"
    assert "图片生成服务暂时不可用" in payload["error"]
    assert "上游返回的图片格式无效" in payload["details"]


def test_itinerary_map_render_respects_logo_toggle(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password="correct horse battery admin", default_api_key="")
    client, _, resolved = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "全球旅行路线图",
            "subtitle": "D1 - D2",
            "logo_requested": False,
            "stops": [
                {"date": "D1", "name": "城市 A", "lat": 35.6812, "lng": 139.7671},
                {"date": "D2", "name": "城市 B", "lat": 34.6937, "lng": 135.5023},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["logo_requested"] is False
    assert payload["logo_overlay_applied"] is False
    svg = Path(payload["saved_image_path"]).read_text(encoding="utf-8")
    assert 'data-layer="program-logo"' not in svg
    with sqlite3.connect(resolved.resolved_auth_db_path) as conn:
        job = conn.execute(
            "SELECT logo_requested FROM generation_jobs WHERE endpoint_path = ?",
            ("/api/itinerary-map/render",),
        ).fetchone()
    assert job is not None
    assert job[0] == 0


def test_itinerary_map_render_uses_ai_approximate_coordinates_when_geocoder_fails(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
        nominatim_url="",
    )
    client, fake, resolved = make_client(settings=settings)
    fake.run_responses.return_value = {
        "output_text": (
            "["
            '{"index":0,"name":"巴黎","lat":48.8566,"lng":2.3522,"confidence":0.72,'
            '"note":"Paris city center approximate"},'
            '{"index":1,"name":"罗马","lat":41.9028,"lng":12.4964,"confidence":0.72,'
            '"note":"Rome city center approximate"}'
            "]"
        )
    }
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "欧洲漫画路线",
            "subtitle": "6/1 - 6/8",
            "generate_background": False,
            "stops": [
                {"date": "D1", "name": "巴黎", "transport": "火车"},
                {"date": "D2", "name": "罗马", "transport": "飞机"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved_image_mime"] == "image/svg+xml"
    assert payload["plan"]["status"] == "ready"
    assert payload["plan"]["stops"][0]["coordinate_source"] == "ai_approximate"
    assert payload["plan"]["stops"][0]["approximate"] is True
    assert payload["plan"]["stops"][0]["lat"] == 48.8566
    assert payload["plan"]["stops"][1]["lng"] == 12.4964
    fake.run_responses.assert_awaited_once()
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["model"] == "gpt-5.6-sol"
    assert upstream_payload["reasoning"]["effort"] == "max"
    assert "可解析 JSON" in upstream_payload["instructions"]
    assert "经纬度" in upstream_payload["instructions"]
    prompt_text = upstream_payload["input"][0]["content"][0]["text"]
    assert "大概经纬度" in prompt_text
    assert "只返回 JSON" in prompt_text
    assert "巴黎" in prompt_text
    assert "罗马" in prompt_text
    fake.run_json.assert_not_awaited()

    svg = Path(payload["saved_image_path"]).read_text(encoding="utf-8")
    assert "欧洲漫画路线" in svg
    assert "巴黎" in svg
    assert "罗马" in svg
    assert Path(payload["saved_image_path"]).is_relative_to(resolved.outputs_dir)


def test_itinerary_map_plan_uses_configured_mapbox_geocoder(make_client, settings_factory, respx_mock):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        map_provider="mapbox",
        mapbox_token="mapbox-test-token",
    )
    client, _, _ = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200
    respx_mock.get("https://api.mapbox.com/geocoding/v5/mapbox.places/城市%20A.json").respond(
        200,
        json={
            "features": [
                {
                    "text": "城市 A",
                    "place_name": "城市 A, Country",
                    "center": [139.7671, 35.6812],
                    "relevance": 0.99,
                }
            ]
        },
    )

    response = client.post(
        "/api/itinerary-map/plan",
        json={
            "title": "全球旅行路线图",
            "subtitle": "D1 - D2",
            "stops": [
                {"date": "D1", "name": "城市 A", "transport": "火车"},
                {"date": "D2", "name": "城市 B", "lat": 34.6937, "lng": 135.5023, "transport": "自驾"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["stops"][0]["geocoded"] is True
    assert payload["stops"][0]["lat"] == 35.6812


def test_itinerary_map_plan_uses_default_nominatim_geocoder(make_client, settings_factory, respx_mock):
    settings = settings_factory(auth_enabled=True, admin_password="correct horse battery admin")
    client, _, _ = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200
    respx_mock.get("https://nominatim.openstreetmap.org/search").respond(
        200,
        json=[
            {
                "name": "城市 A",
                "display_name": "城市 A, Country",
                "lat": "35.6812",
                "lon": "139.7671",
                "importance": 0.8,
                "place_rank": 16,
            }
        ],
    )

    response = client.post(
        "/api/itinerary-map/plan",
        json={
            "title": "全球旅行路线图",
            "subtitle": "D1 - D2",
            "stops": [
                {"date": "D1", "name": "城市 A", "transport": "火车"},
                {"date": "D2", "name": "城市 B", "lat": 34.6937, "lng": 135.5023, "transport": "自驾"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["stops"][0]["geocoded"] is True
    assert payload["stops"][0]["lat"] == 35.6812


def test_itinerary_map_render_requires_subtitle_date(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password="correct horse battery admin")
    client, _, _ = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200

    response = client.post(
        "/api/itinerary-map/render",
        json={
            "title": "全球旅行路线图",
            "subtitle": "",
            "stops": [
                {"date": "D1", "name": "城市 A", "lat": 35.6812, "lng": 139.7671},
                {"date": "D2", "name": "城市 B", "lat": 34.6937, "lng": 135.5023},
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert "副标题日期" in response.json()["error"]


def test_itinerary_projection_spreads_same_place_stops_for_readability():
    plan = build_itinerary_map_plan(
        title="同城多站路线",
        subtitle="D1 - D4",
        stops=[
            {"date": "D1", "name": "日内瓦", "lat": 46.2044, "lng": 6.1432},
            {"date": "D2", "name": "日内瓦湖", "lat": 46.2045, "lng": 6.1431},
            {"date": "D3", "name": "第戎", "lat": 47.3220, "lng": 5.0415},
            {"date": "D4", "name": "勃艮第第戎", "lat": 47.3221, "lng": 5.0414},
        ],
    )

    points = project_itinerary_points(plan, width=1088, height=2240)

    assert len(points) == 4
    assert math.hypot(points[0]["x"] - points[1]["x"], points[0]["y"] - points[1]["y"]) >= 30
    assert math.hypot(points[2]["x"] - points[3]["x"], points[2]["y"] - points[3]["y"]) >= 30

    svg = render_itinerary_map_svg(plan, width=1088, height=2240)
    assert 'data-layer="program-route"' in svg
    assert 'class="route-dot-index">4</text>' in svg
    assert "日内瓦湖" in svg
    assert "勃艮第第戎" in svg


def test_itinerary_map_svg_uses_soft_route_style_and_country_labels():
    plan = build_itinerary_map_plan(
        title="欧洲旅行路线图",
        subtitle="9/5 - 9/17",
        stops=[
            {"date": "9/5", "name": "罗马", "lat": 41.9028, "lng": 12.4964},
            {"date": "9/7", "name": "佛罗伦萨", "lat": 43.7696, "lng": 11.2558},
            {"date": "9/12", "name": "苏黎世", "lat": 47.3769, "lng": 8.5417},
            {"date": "9/16", "name": "日内瓦蒙特勒洛桑", "country": "瑞士/法国", "lat": 46.4312, "lng": 6.9107},
            {"date": "9/17", "name": "巴黎", "country": "法国", "lat": 48.8566, "lng": 2.3522},
        ],
    )

    points_before = project_itinerary_points(plan, width=1792, height=1792)
    svg = render_itinerary_map_svg(plan, background_image_url=f"data:image/png;base64,{TINY_PNG_B64}")
    points_after = project_itinerary_points(plan, width=1792, height=1792)

    assert points_after == points_before
    assert 'data-layer="program-country-labels"' in svg
    assert "意大利" in svg
    assert "瑞士" in svg
    assert "法国" in svg
    assert "瑞士/法国" not in svg
    assert "日内瓦蒙特勒洛桑" in svg
    assert "stroke:#7f5f45;stroke-width:3.8" in svg
    assert "stroke:#bd2f2f" not in svg
    assert "stroke-width:13" not in svg
    assert ".route-line.transfer{stroke-width:3.2;opacity:.62}" in svg
    assert ".route-line.transfer{stroke-width:3.2;stroke-dasharray" not in svg
    assert 'class="callout-scroll"' in svg
    assert 'class="callout-card"' not in svg
    assert 'data-layer="program-title"' in svg
    assert 'id="titleBrushRough"' in svg
    assert "@font-face{font-family:'PicGenRouteTitle'" in svg
    assert "data:font/ttf;base64," in svg
    assert "ZCOOL XiaoWei" in svg
    assert 'class="title-wash"' in svg
    assert 'class="title-brush"' in svg
    assert 'class="title-gold-edge"' in svg
    assert 'id="titleInk"' in svg
    assert "font-family:'PicGenRouteTitle'" in svg


def test_itinerary_country_labels_stay_inside_portrait_canvas():
    plan = build_itinerary_map_plan(
        title="欧洲文化路线",
        subtitle="9/5 - 9/12",
        stops=[
            {"date": "9/5", "name": "柏林", "country": "德国", "lat": 52.52, "lng": 13.405},
            {"date": "9/7", "name": "德累斯顿", "country": "德国", "lat": 51.0504, "lng": 13.7373},
            {"date": "9/9", "name": "布拉格", "country": "捷克", "lat": 50.0755, "lng": 14.4378},
            {"date": "9/11", "name": "维也纳", "country": "奥地利", "lat": 48.2082, "lng": 16.3738},
        ],
    )

    svg = render_itinerary_map_svg(plan, width=1088, height=2240)
    match = re.search(r'<text x="([0-9.]+)" y="([0-9.]+)"[^>]*>奥地利</text>', svg)

    assert match is not None
    assert float(match.group(1)) <= 900


def test_generate_ignores_unrecognized_client_mode(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, fake, resolved_settings = make_client(settings=settings)
    register_response = client.post(
        "/api/auth/register",
        json={"username": "posteruser", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/generate",
        json={
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
            "mode": "unexpected-mode",
        },
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "generate"
    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        job = conn.execute("SELECT * FROM generation_jobs").fetchone()
        image = conn.execute("SELECT * FROM generated_images").fetchone()
    assert job["mode"] == "generate"
    assert image["mode"] == "generate"


def test_authenticated_generation_sends_success_telegram_alert(
    make_client,
    settings_factory,
    monkeypatch,
):
    alerts = []

    async def _fake_send_generation_success_notification(**kwargs):
        alerts.append(kwargs["alert"])
        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr(
        "picgen.routes.send_generation_success_notification",
        _fake_send_generation_success_notification,
    )
    settings = settings_factory(
        auth_enabled=True,
        default_api_key="sk-test",
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-100123456",
    )
    client, fake, _ = make_client(settings=settings)
    register = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register.status_code == 200
    fake.run_json.return_value = {
        "data": [{"b64_json": png_b64_with_dimensions(1088, 2240)}],
        "created": 1,
    }

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
            "size": "1088x2240",
            "logo_requested": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert alerts
    alert = alerts[0]
    assert alert.username == "alice"
    assert alert.job_id == payload["generation_job_id"]
    assert alert.generated_image_ids == [payload["generated_image_id"]]
    assert alert.saved_image_urls == [payload["saved_image_url"]]
    assert alert.logo_requested is False
    assert alert.image_count == 1


def test_logo_requested_generation_defers_telegram_alert_until_final_image(
    make_client,
    settings_factory,
    monkeypatch,
):
    alerts = []

    async def _fake_send_generation_success_notification(**kwargs):
        alerts.append(kwargs["alert"])
        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr(
        "picgen.routes.send_generation_success_notification",
        _fake_send_generation_success_notification,
    )
    settings = settings_factory(
        auth_enabled=True,
        default_api_key="sk-test",
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-100123456",
    )
    client, fake, _ = make_client(settings=settings)
    register = client.post(
        "/api/auth/register",
        json={"username": "routeplanner", "password": "correct horse battery"},
    )
    assert register.status_code == 200
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/generate",
        json={
            "prompt": "生成全球旅行路线图，地点相对位置必须真实",
            "model": "gpt-image-2",
            "mode": "itinerary",
            "size": "1792x1792",
            "logo_requested": True,
        },
    )

    assert response.status_code == 200
    assert alerts == []


def test_generate_accepts_three_candidates(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {
        "data": [
            {"b64_json": TINY_PNG_B64, "revised_prompt": "candidate 1"},
            {"b64_json": TINY_PNG_B64, "revised_prompt": "candidate 2"},
            {"b64_json": TINY_PNG_B64, "revised_prompt": "candidate 3"},
        ],
        "created": 1,
    }

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成三张旅行海报",
            "model": "gpt-image-2",
            "sample_count": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_count"] == 3
    assert payload["candidate_count"] == 3
    assert len(payload["images"]) == 3

    upstream_payload = fake.run_json.await_args.args[2]
    assert upstream_payload["n"] == 3


def test_generate_fans_out_when_upstream_returns_fewer_candidates(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.side_effect = [
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 1},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 2},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 3},
    ]

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成三张旅行海报",
            "model": "gpt-image-2",
            "sample_count": 3,
        },
    )

    assert response.status_code == 200
    assert response.json()["candidate_count"] == 3
    assert fake.run_json.await_count == 3
    assert fake.run_json.await_args_list[0].args[2]["n"] == 3
    assert "n" not in fake.run_json.await_args_list[1].args[2]


def test_generate_retries_without_sample_count_after_502(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.side_effect = [
        APIError(502, "Upstream request failed", code="upstream_error"),
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 1},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 2},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 3},
    ]

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成三张旅行海报",
            "model": "gpt-image-2",
            "sample_count": 3,
        },
    )

    assert response.status_code == 200
    assert response.json()["candidate_count"] == 3
    assert fake.run_json.await_count == 4
    assert fake.run_json.await_args_list[0].args[2]["n"] == 3
    assert "n" not in fake.run_json.await_args_list[1].args[2]


def test_generate_does_not_retry_on_content_moderation_400(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.side_effect = [
        APIError(400, "Your prompt is not allowed by the content policy", code="upstream_error"),
    ]

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成两张海报",
            "model": "gpt-image-2",
            "sample_count": 2,
        },
    )

    # The bare " n" inside "is not allowed" must NOT be read as a sample-count
    # error: the 400 should surface unchanged with no extra fallback call.
    assert response.status_code == 400
    assert fake.run_json.await_count == 1


def test_generate_upstream_rate_limit_returns_friendly_redacted_error(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.side_effect = [
        APIError(
            429,
            "Rate limit reached for gpt-image-2-codex in organization org-BOvpEHVcDPTe8h4lZnwMO5Ly",
            '{"error":{"message":"Rate limit reached","type":"rate_limit_error","api_key":"sk-secret"}}',
            code="upstream_rate_limited",
        ),
    ]

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 429
    payload = response.json()
    assert payload["code"] == "upstream_rate_limited"
    assert "图片生成服务当前请求较多" in payload["error"]
    assert "Rate limit reached" not in payload["error"]
    assert "org-BOvpEHVcDPTe8h4lZnwMO5Ly" not in response.text
    assert "sk-secret" not in response.text


def test_generate_upstream_error_mentions_backend_alert_when_telegram_configured(
    make_client,
    settings_factory,
    monkeypatch,
):
    alerts = []

    async def _fake_send_error_alert_notification(**kwargs):
        alerts.append(kwargs["alert"])
        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr(
        "picgen.main.send_error_alert_notification",
        _fake_send_error_alert_notification,
    )
    settings = settings_factory(
        default_api_key="sk-test",
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-100123456",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.side_effect = [
        APIError(
            504,
            "图片生成服务响应超时，请稍后再试。",
            "生成接口超时：上游接口超过 1200 秒没有返回。",
            code="upstream_timeout",
        ),
    ]

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 504
    assert "后台已收到告警" in response.json()["error"]
    assert alerts
    assert alerts[0].code == "upstream_timeout"


def test_generate_upstream_safety_infra_error_is_not_misclassified_as_content_policy(
    make_client,
    settings_factory,
    monkeypatch,
):
    alerts = []

    async def _fake_send_error_alert_notification(**kwargs):
        alerts.append(kwargs["alert"])
        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr(
        "picgen.main.send_error_alert_notification",
        _fake_send_error_alert_notification,
    )
    settings = settings_factory(
        default_api_key="sk-test",
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-100123456",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.side_effect = [
        APIError(
            502,
            "upstream safety gateway not allowed request forwarding",
            json.dumps(
                {
                    "error": {
                        "message": "safety gateway not allowed request forwarding",
                        "type": "server_error",
                        "code": "server_error",
                    }
                }
            ),
            code="upstream_error",
        ),
    ]

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 502
    payload = response.json()
    assert "图片生成服务暂时不可用" in payload["error"]
    assert "未通过上游内容审核" not in payload["error"]
    assert "后台已收到告警" in payload["error"]
    assert alerts


def test_generate_fanout_tolerates_partial_failure(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.side_effect = [
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 1},
        APIError(502, "transient blip", code="upstream_error"),
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 3},
    ]

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成三张海报",
            "model": "gpt-image-2",
            "sample_count": 3,
        },
    )

    assert response.status_code == 200
    # Initial image plus one successful top-up; the failed concurrent call is tolerated.
    assert response.json()["candidate_count"] == 2
    assert fake.run_json.await_count == 3


def test_generate_rejects_more_than_three_candidates(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成四张旅行海报",
            "model": "gpt-image-2",
            "sample_count": 4,
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    fake.run_json.assert_not_awaited()


def test_edit_requires_image_payload(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, _, _ = make_client(settings=settings)
    response = client.post("/api/edit", json={"prompt": "换成水彩风格"})
    assert response.status_code == 400
    assert response.json()["error"] == "缺少 image 文件"


def test_edit_uses_images_api_and_preserves_mode(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.return_value = {
        "data": [{"b64_json": png_b64_with_dimensions(1024, 1024)}],
        "created": 99,
    }

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "把背景改成纯白",
            "model": "gpt-image-2",
            "mode": "reference",
            "size": "1024x1024",
            "quality": "high",
            "output_format": "png",
            "image": {
                "name": "ref.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "reference"
    assert payload["model"] == "gpt-image-2"
    assert payload["saved_image_url"].startswith("files/outputs/")
    assert payload["raw_response"]["data"][0]["b64_json"].startswith("[omitted ")
    assert TINY_PNG_B64 not in str(payload["raw_response"])

    fake.run_multipart.assert_awaited_once()
    upstream_args = fake.run_multipart.await_args.args
    # signature: (url, api_key, fields, files, user_agent)
    assert upstream_args[0] == "https://api.openai.com/v1/images/edits"
    fields = upstream_args[2]
    assert fields["model"] == "gpt-image-2"
    assert fields["prompt"].startswith("把背景改成纯白")
    assert "硬性目的地限制" in fields["prompt"]
    assert fields["size"] == "1024x1024"
    assert fields["quality"] == "high"
    assert fields["output_format"] == "png"
    files = upstream_args[3]
    assert len(files) == 1
    assert files[0]["field_name"] == "image"
    assert files[0]["filename"] == "ref.png"


def test_edit_accepts_ordered_reference_images_and_returns_candidates(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.return_value = {
        "data": [
            {"b64_json": TINY_PNG_B64, "revised_prompt": "candidate 1"},
            {"b64_json": TINY_PNG_B64, "revised_prompt": "candidate 2"},
            {"b64_json": TINY_PNG_B64, "revised_prompt": "candidate 3"},
        ],
        "created": 100,
    }

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "把素材做成模板风格",
            "model": "gpt-image-2",
            "mode": "reference",
            "sample_count": 3,
            "images": [
                {
                    "name": "style.png",
                    "type": "image/png",
                    "role": "style_template",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
                {
                    "name": "material.png",
                    "type": "image/png",
                    "role": "material",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_count"] == 3
    assert payload["candidate_count"] == 3
    assert len(payload["images"]) == 3
    assert payload["source_image_names"] == ["style.png", "material.png"]
    assert payload["source_image_roles"] == ["style_template", "material"]
    assert payload["saved_image_url"] == payload["images"][0]["saved_image_url"]

    upstream_args = fake.run_multipart.await_args.args
    fields = upstream_args[2]
    assert fields["n"] == 3
    files = upstream_args[3]
    assert [part["field_name"] for part in files] == ["image", "image"]
    assert [part["filename"] for part in files] == ["style.png", "material.png"]
    assert [part["role"] for part in files] == ["style_template", "material"]


def test_edit_fans_out_when_upstream_returns_fewer_candidates(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.side_effect = [
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 1},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 2},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 3},
    ]

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "生成三张候选",
            "model": "gpt-image-2",
            "sample_count": 3,
            "images": [
                {
                    "name": "style.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
                {
                    "name": "material.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["candidate_count"] == 3
    assert fake.run_multipart.await_count == 3
    first_fields = fake.run_multipart.await_args_list[0].args[2]
    second_fields = fake.run_multipart.await_args_list[1].args[2]
    assert first_fields["n"] == 3
    assert "n" not in second_fields


def test_edit_retries_without_sample_count_after_502(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.side_effect = [
        APIError(502, "Upstream request failed", code="upstream_error"),
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 1},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 2},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 3},
    ]

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "生成三张候选",
            "model": "gpt-image-2",
            "sample_count": 3,
            "images": [
                {
                    "name": "style.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
                {
                    "name": "material.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["candidate_count"] == 3
    assert fake.run_multipart.await_count == 4
    assert fake.run_multipart.await_args_list[0].args[2]["n"] == 3
    assert "n" not in fake.run_multipart.await_args_list[1].args[2]


def test_edit_passes_mask_and_options(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 0}

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "去掉文字",
            "model": "gpt-image-2",
            "mode": "edit",
            "output_format": "webp",
            "output_compression": 80,
            "image": {
                "name": "src.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
            "mask": {
                "name": "mask.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 200
    upstream_args = fake.run_multipart.await_args.args
    fields = upstream_args[2]
    assert fields["output_format"] == "webp"
    assert fields["output_compression"] == 80
    files = upstream_args[3]
    field_names = sorted(part["field_name"] for part in files)
    assert field_names == ["image", "mask"]


def test_responses_image_requires_prompt(make_client):
    client, _, _ = make_client()
    response = client.post("/api/responses-image", json={"api_key": "sk-test"})
    assert response.status_code == 400
    assert response.json()["error"] == "Responses 图像提示词不能为空"


def test_responses_image_old_client_legacy_model_is_normalized(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_responses.return_value = {
        "data": [{"b64_json": TINY_PNG_B64}],
        "created": 1,
    }

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "生成一张小图",
            "model": "gpt-5.5",
            "mode": "generate",
        },
    )

    assert response.status_code == 200
    assert response.json()["model"] == "gpt-5.6-sol"
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["model"] == "gpt-5.6-sol"
    assert upstream_payload["reasoning"] == {"effort": "max"}


def test_responses_image_saves_streamed_image(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_responses.return_value = {
        "data": [{"b64_json": TINY_PNG_B64}],
        "created": 1,
        "response_id": "resp_test",
        "stream_events": [{"type": "response.image_generation_call.partial_image"}],
    }
    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/responses",
            "prompt": "生成一张小图",
            "model": "gpt-5.5",
            "responses_model_storage_version": 3,
            "mode": "reference",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "reference"
    assert payload["model"] == "gpt-5.5"
    assert payload["saved_image_url"].startswith("files/outputs/")
    assert (Path(payload["saved_image_path"])).is_file()
    fake.run_responses.assert_awaited_once()
    upstream_payload = fake.run_responses.await_args.args[2]
    assert "图像生成助手" in upstream_payload["instructions"]
    assert upstream_payload["stream"] is True
    assert "reasoning" not in upstream_payload
    assert upstream_payload["tools"] == [{"type": "image_generation", "size": "1088x2240", "quality": "high"}]


def test_responses_image_uploads_input_file_and_uses_file_id(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.return_value = {"id": "file_test_input"}
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "基于这张图重新打光",
            "model": "gpt-5.5",
            "mode": "edit",
            "image": {
                "name": "source.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["files_endpoint_url"] == "https://sub.tidba.com/v1/files"
    assert payload["source_file_id"] == "file_test_input"
    fake.run_file_upload.assert_awaited_once()
    assert fake.run_file_upload.await_args.args[0] == "https://sub.tidba.com/v1/files"
    assert fake.run_file_upload.await_args.args[2]["filename"] == "source.png"
    upstream_payload = fake.run_responses.await_args.args[2]
    content = upstream_payload["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert content[0]["text"].startswith("基于这张图重新打光")
    assert "硬性目的地限制" in content[0]["text"]
    assert content[1:] == [{"type": "input_image", "file_id": "file_test_input"}]
    assert "data:image/png;base64" not in str(upstream_payload)


def test_responses_image_uploads_ordered_reference_images(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.side_effect = [{"id": "file_style"}, {"id": "file_material"}]
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "把素材做成模板风格",
            "model": "gpt-5.5",
            "mode": "reference",
            "sample_count": 3,
            "images": [
                {
                    "name": "style.png",
                    "type": "image/png",
                    "role": "style_template",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
                {
                    "name": "material.png",
                    "type": "image/png",
                    "role": "material",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_file_ids"] == ["file_style", "file_material"]
    assert payload["source_image_names"] == ["style.png", "material.png"]
    assert fake.run_file_upload.await_count == 2

    uploaded = [call.args[2]["filename"] for call in fake.run_file_upload.await_args_list]
    assert uploaded == ["style.png", "material.png"]
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["tools"][0]["n"] == 3
    content = upstream_payload["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert content[0]["text"].startswith("把素材做成模板风格")
    assert "硬性目的地限制" in content[0]["text"]
    assert content[1:] == [
        {"type": "input_image", "file_id": "file_style"},
        {"type": "input_image", "file_id": "file_material"},
    ]


def test_responses_image_records_reference_source_generation_id(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-test",
    )
    client, fake, resolved_settings = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": png_b64_with_dimensions(1088, 2240)}], "created": 1}
    fake.run_file_upload.return_value = {"id": "file_source"}
    fake.run_responses.return_value = {"data": [{"b64_json": png_b64_with_dimensions(1088, 2240)}], "created": 2}

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register_response.status_code == 200
    original = client.post(
        "/api/generate",
        json={"prompt": "西班牙味觉地图", "model": "gpt-image-2", "size": "1088x2240"},
    )
    assert original.status_code == 200
    original_id = original.json()["generated_image_id"]

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "把这张图改成更清晰的美食路线海报",
            "model": "gpt-5.5",
            "mode": "reference",
            "size": "1088x2240",
            "quality": "high",
            "source_generated_image_id": original_id,
            "images": [
                {
                    "name": "source.png",
                    "type": "image/png",
                    "role": "source_image",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_generated_image_id"] == original_id
    assert payload["requested_size"] == "1088x2240"
    assert payload["images"][0]["source_generated_image_id"] == original_id

    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["tools"][0]["size"] == "1088x2240"
    assert upstream_payload["tools"][0]["quality"] == "high"

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        image_row = conn.execute(
            "SELECT source_generated_image_id FROM generated_images WHERE id = ?",
            (payload["generated_image_id"],),
        ).fetchone()
        job_row = conn.execute(
            "SELECT mode, size FROM generation_jobs WHERE id = ?",
            (payload["generation_job_id"],),
        ).fetchone()

    assert image_row["source_generated_image_id"] == original_id
    assert job_row["mode"] == "reference"
    assert job_row["size"] == "1088x2240"


def test_responses_image_normalizes_mismatched_poster_size_from_upstream(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_responses.return_value = {
        "data": [{"b64_json": valid_png_b64(10, 20)}],
        "created": 1,
    }

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "生成严格尺寸海报",
            "model": "gpt-5.5",
            "mode": "generate",
            "size": "20x40",
            "quality": "high",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["size"] == "20x40"
    assert payload["requested_size"] == "20x40"
    assert payload["saved_image_width"] == 20
    assert payload["saved_image_height"] == 40
    assert payload["actual_size"] == "20x40"
    assert payload["upstream_actual_size"] == "10x20"
    assert payload["image_size_normalized"] is True
    assert payload["size_mismatch"] is False
    assert payload["images"][0]["saved_image_width"] == 20
    assert payload["images"][0]["saved_image_height"] == 40
    assert payload["images"][0]["actual_size"] == "20x40"
    assert payload["images"][0]["upstream_actual_size"] == "10x20"
    assert payload["images"][0]["image_size_normalized"] is True
    assert payload["images"][0]["size_mismatch"] is False
    assert payload["saved_image_url"].startswith("files/outputs/")


def test_responses_image_normalizes_default_poster_size_when_size_omitted(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test", default_size="20x40")
    client, fake, _ = make_client(settings=settings)
    fake.run_responses.return_value = {
        "data": [{"b64_json": valid_png_b64(10, 20)}],
        "created": 1,
    }

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "生成严格尺寸海报",
            "model": "gpt-5.6-sol",
            "mode": "generate",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved_image_width"] == 20
    assert payload["saved_image_height"] == 40
    assert payload["upstream_actual_size"] == "10x20"
    assert payload["image_size_normalized"] is True


def test_copyright_risk_uses_gpt55_and_inline_images(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_responses.return_value = {
        "output_text": "风险等级：低\n可能风险点：含有活动标识，商用前确认授权。",
    }

    response = client.post(
        "/api/copyright-risk",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/responses",
            "prompt": "生成一张活动图",
            "images": [
                {
                    "name": "result.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "gpt-5.6-sol"
    assert "风险等级：低" in payload["risk_text"]
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["model"] == "gpt-5.6-sol"
    assert upstream_payload["reasoning"]["effort"] == "max"
    assert "版权" in upstream_payload["instructions"]
    assert "中文" in upstream_payload["instructions"]
    content = upstream_payload["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert "版权与商标风险审查助手" in content[0]["text"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")


def test_text_fidelity_check_uses_required_and_forbidden_phrases(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_responses.return_value = {
        "output_text": (
            "结论：不通过\n"
            "缺失或疑似错误：铁煎章鱼\n"
            "残留旧文字：铁帆鱿鱼"
        ),
    }

    response = client.post(
        "/api/text-fidelity",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/responses",
            "prompt": "把“铁帆鱿鱼”改成“铁煎章鱼”，把“11日从头吃到尾”改成“舌尖盛宴”",
            "text_contract": {
                "required": ["舌尖盛宴", "铁煎章鱼"],
                "forbidden": ["铁帆鱿鱼", "11日从头吃到尾"],
            },
            "images": [
                {
                    "name": "result.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "gpt-5.6-sol"
    assert payload["passed"] is False
    assert "铁煎章鱼" in payload["fidelity_text"]
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["reasoning"]["effort"] == "max"
    assert "文字一致性验收助手" in upstream_payload["instructions"]
    content = upstream_payload["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert "必须出现：舌尖盛宴" in content[0]["text"]
    assert "必须出现：铁煎章鱼" in content[0]["text"]
    assert "不得出现：铁帆鱿鱼" in content[0]["text"]
    assert "不得出现：11日从头吃到尾" in content[0]["text"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")


def test_edit_accepts_logo_reference_and_prompt_guidance(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": ("生成海报\n\n6 人游 LOGO 合成要求：请把参考图中的 6 人游 LOGO 作为公司官方标识整合进最终画面。"),
            "model": "gpt-image-2",
            "mode": "generate-with-logo",
            "images": [
                {
                    "name": "6renyou.png",
                    "type": "image/png",
                    "role": "brand_logo",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "generate-with-logo"
    assert payload["source_image_names"] == ["6renyou.png"]
    assert payload["source_image_roles"] == ["brand_logo"]
    upstream_args = fake.run_multipart.await_args.args
    fields = upstream_args[2]
    assert "6 人游 LOGO 合成要求" in fields["prompt"]
    assert "硬性目的地限制" in fields["prompt"]
    files = upstream_args[3]
    assert len(files) == 1
    assert files[0]["filename"] == "6renyou.png"
    assert files[0]["role"] == "brand_logo"


def test_logo_reference_generation_keeps_single_candidate_by_default(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "生成海报并自然合成 6 人游 LOGO",
            "model": "gpt-image-2",
            "mode": "reference-with-logo",
            "logo_requested": True,
            "images": [
                {
                    "name": "6renyou.png",
                    "type": "image/png",
                    "role": "brand_logo",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_count"] == 1
    assert payload["logo_requested"] is True
    fields = fake.run_multipart.await_args.args[2]
    assert "n" not in fields


def test_responses_image_accepts_logo_reference_and_preserves_order(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.side_effect = [{"id": "file_source"}, {"id": "file_logo"}]
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "在现有图片中自然加入 6 人游 LOGO",
            "model": "gpt-5.5",
            "mode": "edit-with-logo",
            "images": [
                {
                    "name": "source.png",
                    "type": "image/png",
                    "role": "source_image",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
                {
                    "name": "6renyou.png",
                    "type": "image/png",
                    "role": "brand_logo",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_image_names"] == ["source.png", "6renyou.png"]
    assert payload["source_image_roles"] == ["source_image", "brand_logo"]
    assert payload["source_file_ids"] == ["file_source", "file_logo"]
    upstream_payload = fake.run_responses.await_args.args[2]
    content = upstream_payload["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert content[0]["text"].startswith("在现有图片中自然加入 6 人游 LOGO")
    assert "硬性目的地限制" in content[0]["text"]
    assert content[1:] == [
        {"type": "input_image", "file_id": "file_source"},
        {"type": "input_image", "file_id": "file_logo"},
    ]


def test_logo_compose_endpoint_is_removed(make_client):
    client, _, _ = make_client()
    response = client.post("/api/logo-compose", json={})
    assert response.status_code in {404, 405}


def test_final_image_upload_requires_auth(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True)
    client, _, _ = make_client(settings=settings)

    response = client.post(
        "/api/final-images",
        json={
            "generated_image_id": 1,
            "image": {
                "name": "result-logo.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_responses_image_can_fallback_to_inline_after_file_upload_error(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.side_effect = APIError(502, "Files 上传接口在接收文件时断开连接")
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "基于这张图重新打光",
            "model": "gpt-5.5",
            "allow_inline_fallback": True,
            "image": {
                "name": "source-upload.jpg",
                "type": "image/jpeg",
                "data_url": f"data:image/jpeg;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_upload_fallback"] is True
    assert payload["source_file_id"] is None
    upstream_payload = fake.run_responses.await_args.args[2]
    content = upstream_payload["input"][0]["content"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")


def test_responses_image_falls_back_to_inline_by_default_after_file_upload_error(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.side_effect = APIError(502, "Files 上传接口在接收文件时断开连接")
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "基于这张图重新打光",
            "model": "gpt-5.5",
            "image": {
                "name": "source-upload.jpg",
                "type": "image/jpeg",
                "data_url": f"data:image/jpeg;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["file_upload_fallback"] is True
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,")


def test_responses_image_can_disable_inline_fallback(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.side_effect = APIError(502, "Files 上传接口在接收文件时断开连接")

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "基于这张图重新打光",
            "model": "gpt-5.5",
            "allow_inline_fallback": False,
            "image": {
                "name": "source-upload.jpg",
                "type": "image/jpeg",
                "data_url": f"data:image/jpeg;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 502
    payload = response.json()
    assert payload["error"].startswith("图片生成服务暂时不可用")
    assert "Files 上传接口在接收文件时断开连接" in (payload["details"] or "")
    fake.run_responses.assert_not_called()


def test_payload_size_limit_blocks_oversized_request(make_client, settings_factory):
    settings = settings_factory(max_request_body_bytes=1024, default_api_key="sk-test")
    client, _, _ = make_client(settings=settings)
    big_payload = {"prompt": "a" * 2048}
    response = client.post("/api/generate", json=big_payload)
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_payload_size_limit_counts_streamed_body_without_content_length():
    async def drain_app(scope, receive, send):
        while True:
            message = await receive()
            if message["type"] != "http.request" or not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    app = BodySizeLimitMiddleware(drain_app, max_bytes=1024)
    messages = [
        {"type": "http.request", "body": b"a" * 800, "more_body": True},
        {"type": "http.request", "body": b"b" * 800, "more_body": False},
    ]
    sent: list[dict[str, object]] = []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/generate",
        "raw_path": b"/api/generate",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "root_path": "",
    }

    async def receive() -> dict[str, object]:
        return messages.pop(0)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    import anyio

    anyio.run(app, scope, receive, send)

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 413


def test_payload_size_limit_streams_through_with_valid_content_length():
    received: dict[str, object] = {}

    async def echo_app(scope, receive, send):
        message = await receive()
        received["body"] = message.get("body")
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    body = b'{"prompt":"hi"}'
    app = BodySizeLimitMiddleware(echo_app, max_bytes=1024)
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    sent: list[dict[str, object]] = []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/generate",
        "raw_path": b"/api/generate",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "root_path": "",
    }

    async def receive() -> dict[str, object]:
        return messages.pop(0)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    import anyio

    anyio.run(app, scope, receive, send)

    # The body is forwarded untouched (fast path, no buffering/replay).
    assert received["body"] == body
    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 204


def test_rate_limit_returns_429(make_client, settings_factory):
    settings = settings_factory(rate_limit_per_minute=2, rate_limit_burst=2)
    client, _, _ = make_client(settings=settings)
    # generate endpoint -> still validation 400, but counts toward rate limit
    client.post("/api/generate", json={})
    client.post("/api/generate", json={})
    response = client.post("/api/generate", json={})
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert "Retry-After" in response.headers


def test_proxy_auth_token_enforced(make_client, settings_factory):
    settings = settings_factory(proxy_auth_token="topsecret")
    client, _, _ = make_client(settings=settings)
    response = client.post("/api/generate", json={"prompt": "x"})
    assert response.status_code == 401
    response2 = client.post(
        "/api/generate",
        json={"prompt": "x"},
        headers={"X-Proxy-Token": "topsecret"},
    )
    # missing api_key but past auth
    assert response2.status_code in {400}
    health_response = client.get("/api/health")
    assert health_response.status_code == 200  # health is allowlisted


def test_with_timing_cancels_handler_when_client_disconnects(settings_factory):
    class DisconnectedRequest:
        async def is_disconnected(self) -> bool:
            return True

    cancelled = False

    async def slow_handler(_body, _settings, _client, _user):
        nonlocal cancelled
        try:
            await anyio.sleep(10)
        finally:
            cancelled = True

    async def run_check():
        with pytest.raises(APIError) as exc_info:
            await _with_timing(
                "/api/generate",
                slow_handler,
                {},
                settings_factory(default_api_key="sk-test"),
                object(),
                request=DisconnectedRequest(),
            )
        assert exc_info.value.status == 499
        assert exc_info.value.code == "client_cancelled"

    anyio.run(run_check)
    assert cancelled is True


def test_responses_sse_parser_keeps_partial_image() -> None:
    body = (
        "event: response.image_generation_call.partial_image\n"
        f'data: {{"type":"response.image_generation_call.partial_image","partial_image_b64":"{TINY_PNG_B64}"}}\n\n'
        "data: [DONE]\n\n"
    )

    events = parse_sse_json_events(body)
    payload = stream_events_to_image_payload(events, url="https://api.openai.com/v1/responses", started_at=0)

    assert len(events) == 1
    assert payload["data"][0]["b64_json"] == TINY_PNG_B64


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": " "},
        {"prompt": "x" * 32_001},
    ],
)
def test_generate_validation_errors(make_client, settings_factory, payload):
    settings = settings_factory(default_api_key="sk-test")
    client, _, _ = make_client(settings=settings)
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 400

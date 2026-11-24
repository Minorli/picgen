from __future__ import annotations

import json
from types import SimpleNamespace

from picgen.logging_config import reset_request_id, set_request_id
from picgen.notifications import build_generation_success_alert_text
from picgen.routes import _build_final_image_success_alert


def test_final_notification_uses_generation_context_and_separate_save_timing():
    image = {
        "id": 471, "job_id": 474, "mode": "generate", "model": "gpt-6-astra",
        "saved_image_url": "files/final.png", "saved_image_width": 1088, "saved_image_height": 2240,
        "saved_image_bytes": 5440611, "logo_requested": True, "logo_overlay_applied": True,
        "lineage": {
            "request_id": "original-generation-id", "endpoint_path": "/api/image-jobs",
            "elapsed_ms": 132720.1, "size": "1088x2240", "transport": "responses-image",
            "sample_count": 3, "image_count": 2,
        },
        "metadata": {"image_model": "gpt-image-2.5-sunburst"},
    }
    token = set_request_id("final-save-id")
    try:
        alert = _build_final_image_success_alert(
            image=image, user=SimpleNamespace(id=56, username="jiaqi"), elapsed_ms=3700.0
        )
    finally:
        reset_request_id(token)
    content = build_generation_success_alert_text(alert)
    assert "任务：#474 / original-generation-id" in content
    assert "保存请求：final-save-id" in content
    assert "生成接口：POST /api/image-jobs" in content
    assert "生图耗时：132.7s" in content
    assert "成品保存耗时：3.7s" in content
    assert "成品尺寸：1088x2240" in content
    assert "请求尺寸：1088x2240" in content
    assert "主模型：gpt-6-astra" in content
    assert "图像模型（请求）：gpt-image-2.5-sunburst" in content
    assert "任务出图：2 张（请求 3 张）" in content
    assert "本次成品：1 张" in content


def test_legacy_final_notification_does_not_invent_generation_time_or_model():
    alert = _build_final_image_success_alert(
        image={
            "id": 471, "job_id": 474, "model": "gpt-6-astra", "saved_image_url": "files/final.png",
            "saved_image_width": 1088, "saved_image_height": 2240,
            "lineage": {"transport": "responses-image"},
        },
        user=SimpleNamespace(id=56, username="jiaqi"), elapsed_ms=3700.0,
    )
    content = build_generation_success_alert_text(alert)
    assert "生图耗时：未记录" in content
    assert "图像模型（请求）：未记录" in content
    assert "成品保存耗时：3.7s" in content


def test_final_notification_route_preserves_original_context(make_client, settings_factory, monkeypatch):
    import sqlite3

    from test_api import TINY_PNG_B64

    from picgen.notifications import NotificationResult

    alerts = []

    async def capture(**kwargs):
        alerts.append(kwargs["alert"])
        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr("picgen.routes.send_generation_success_notification", capture)
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/register", json={"username": "context-user", "password": "correct horse battery"}
    ).status_code == 200
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}]}
    generated = client.post("/api/image-jobs", json={
        "prompt": "a lake", "size": "1088x2240", "logo_requested": True,
    }, headers={"X-Request-ID": "original-generation-id"})
    assert generated.status_code == 200
    result = generated.json()
    with sqlite3.connect(settings.resolved_auth_db_path) as c:
        c.execute("UPDATE generation_jobs SET elapsed_ms=132720.1 WHERE id=?", (result["generation_job_id"],))
    assert alerts == []
    for _ in range(2):
        final = client.post("/api/final-images", json={
            "generated_image_id": result["generated_image_id"], "logo_overlay_applied": True,
            "image": {"name": "final.png", "type": "image/png", "data_url": f"data:image/png;base64,{TINY_PNG_B64}"},
        }, headers={"X-Request-ID": "final-save-id"})
        assert final.status_code == 200
    assert len(alerts) == 1
    content = build_generation_success_alert_text(alerts[0])
    assert "任务：#" in content and "original-generation-id" in content
    assert "保存请求：final-save-id" in content
    assert "生图耗时：132.7s" in content
    assert "请求尺寸：1088x2240" in content
    assert "成品尺寸：1x1" in content
    assert "图像模型（请求）：gpt-image-2.5-sunburst" in content
    with sqlite3.connect(settings.resolved_auth_db_path) as c:
        metadata = json.loads(c.execute("SELECT metadata_json FROM generated_image_metadata").fetchone()[0])
    assert metadata["image_model"] == "gpt-image-2.5-sunburst"

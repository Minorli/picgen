from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from picgen.errors import APIError
from picgen.main import create_app
from picgen.notifications import NotificationResult


@pytest.mark.parametrize("domain_error", [False, True])
def test_internal_error_hides_implementation_details(settings_factory, monkeypatch, domain_error):
    alerts = []

    async def capture_alert(**kwargs):
        alerts.append(kwargs["alert"])
        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr("picgen.main.send_error_alert_notification", capture_alert)
    settings = settings_factory(
        static_dir="/nonexistent-picgen-test-static",
        error_alert_telegram_bot_token="123:test",
        error_alert_telegram_chat_id="-123",
    )
    app = create_app(settings)

    @app.get("/api/boom")
    async def boom():
        message = "failed to read /srv/private/database.sqlite3 password=private-secret"
        if domain_error:
            raise APIError(500, message, message, code="internal_error")
        raise RuntimeError(message)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/boom")
    assert response.status_code == 500
    assert response.json()["details"] is None
    assert "/srv/private" not in response.text
    assert "private-secret" not in response.text
    assert alerts
    assert "/srv/private" in alerts[0].technical_message
    assert "private-secret" not in alerts[0].technical_message


def test_connect_timeout_keeps_specific_user_message(settings_factory):
    app = create_app(settings_factory(static_dir="/nonexistent-picgen-test-static"))

    @app.get("/api/connect-timeout")
    async def timeout():
        raise APIError(504, "连接图片生成服务超时，请稍后再试。", code="upstream_timeout")

    with TestClient(app) as client:
        response = client.get("/api/connect-timeout")
    assert response.status_code == 504
    assert response.json()["error"].startswith("连接图片生成服务超时")

from __future__ import annotations

import json

import pytest

from picgen.errors import APIError
from picgen.main import _base_operational_message

_PRIVATE = "PRIVATE_PROMPT_OR_REFUSAL_MARKER"


def _generate(client):
    return client.post("/api/generate", json={
        "prompt": "生成测试图片", "model": "gpt-image-2", "size": "1024x1024",
    }, headers={"X-Request-ID": "safe-no-image-request"})


@pytest.mark.parametrize("typed_refusal", [False, True])
def test_no_image_api_reports_facts_without_echoing_provider_text(make_client, settings_factory, typed_refusal):
    client, fake, _ = make_client(settings=settings_factory(default_api_key="sk-test", size_mismatch_max_retries=2))
    part = (
        {"type": "refusal", "refusal": _PRIVATE}
        if typed_refusal else {"type": "output_text", "text": f"{_PRIVATE} content policy not allowed"}
    )
    fake.run_json.return_value = {
        "id": "resp_safe123", "status": "completed", "instructions": _PRIVATE,
        "api_key": "sk-secret123456", "output": [{"type": "message", "content": [part]}],
    }

    response = _generate(client)

    assert response.status_code == 502
    payload = response.json()
    assert payload["code"] == "upstream_no_image"
    assert payload["request_id"] == "safe-no-image-request"
    assert _PRIVATE not in response.text
    assert "sk-secret123456" not in response.text
    assert "内容审核" not in payload["error"]
    assert "手动重试" in payload["error"]
    diagnostics = json.loads(payload["details"])
    assert diagnostics["response_id"] == "resp_safe123"
    assert diagnostics["reason"] == ("response_refusal" if typed_refusal else "no_image_output")
    assert ("拒绝" in payload["error"]) is typed_refusal
    assert fake.run_json.await_count == 1
    fake.run_responses.assert_not_awaited()


def test_normalized_no_image_diagnostics_are_allowlisted_and_recorded_in_history(make_client, settings_factory):
    client, fake, _ = make_client(settings=settings_factory(default_api_key="sk-test", auth_enabled=True))
    registered = client.post("/api/auth/register", json={"username": "alice", "password": "secure test password"})
    assert registered.status_code == 200
    fake.run_json.return_value = {
        "data": [], "output_text": _PRIVATE,
        "image_diagnostics": {
            "response_id": "resp_safe123", "response_status": "completed", "reason": "image_tool_unfinished",
            "image_call_count": 1, "result_image_count": 0, "refusal_count": 0, "text_chars": 30,
            "image_calls": [{"id": "img_safe123", "status": "generating", "has_result": False,
                             "error": {"code": "server_error", "message": _PRIVATE}, "prompt": _PRIVATE}],
            "prompt": _PRIVATE, "instructions": _PRIVATE, "unknown_field": _PRIVATE,
        },
    }

    response = _generate(client)

    assert response.status_code == 502
    payload = response.json()
    assert "生图步骤未完成" in payload["error"]
    assert _PRIVATE not in response.text
    diagnostics = json.loads(payload["details"])
    assert diagnostics["reason"] == "image_tool_unfinished"
    assert diagnostics["response_id"] == "resp_safe123"
    assert "message" not in diagnostics["image_calls"][0]["error"]
    job = client.get("/api/jobs?limit=1").json()["jobs"][0]
    assert job["status"] == "failed"
    assert job["error_code"] == "upstream_no_image"
    assert "生图步骤未完成" in job["error_message"]
    assert _PRIVATE not in job["error_message"]
    assert fake.run_json.await_count == 1


def test_unknown_diagnostic_fields_cannot_become_error_details(make_client, settings_factory):
    client, fake, _ = make_client(settings=settings_factory(default_api_key="sk-test"))
    fake.run_json.return_value = {
        "id": "resp_safe123", "status": "completed", "output_text": _PRIVATE,
        "image_diagnostics": {"reason": _PRIVATE, "password": _PRIVATE},
    }
    response = _generate(client)
    assert response.status_code == 502
    assert _PRIVATE not in response.text
    diagnostics = json.loads(response.json()["details"])
    assert diagnostics["reason"] == "no_image_output"
    assert diagnostics["response_id"] == "resp_safe123"


def test_unrecognized_no_image_exception_message_is_not_trusted():
    message = _base_operational_message(APIError(502, _PRIVATE, code="upstream_no_image"))
    assert _PRIVATE not in message


def test_no_image_admin_alert_contains_safe_diagnostics_only(make_client, settings_factory, monkeypatch):
    from picgen.notifications import NotificationResult

    alerts = []

    async def capture_alert(**kwargs):
        alerts.append(kwargs["alert"])
        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr("picgen.main.send_error_alert_notification", capture_alert)
    client, fake, _ = make_client(settings=settings_factory(
        default_api_key="sk-test", error_alert_telegram_bot_token="123:test", error_alert_telegram_chat_id="-123",
    ))
    fake.run_json.return_value = {
        "id": "resp_safe123", "status": "completed", "output_text": _PRIVATE, "instructions": _PRIVATE,
    }
    response = _generate(client)
    assert response.status_code == 502
    assert len(alerts) == 1
    assert alerts[0].code == "upstream_no_image"
    assert alerts[0].request_id == "safe-no-image-request"
    assert json.loads(alerts[0].details)["response_id"] == "resp_safe123"
    assert _PRIVATE not in repr(alerts[0])

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from picgen.notifications import _send_telegram_message


@pytest.fixture()
def telegram_settings(settings_factory):
    return settings_factory(error_alert_telegram_bot_token="123:test", error_alert_telegram_chat_id="-123")


@pytest.mark.parametrize("payload", [{"ok": False, "description": "Forbidden"}, {}, []])
async def test_telegram_requires_explicit_success(telegram_settings, respx_mock, payload):
    route = respx_mock.post("https://api.telegram.org/bot123:test/sendMessage").respond(200, json=payload)
    result = await _send_telegram_message(settings=telegram_settings, content="test")
    assert not result.sent
    assert result.status == "failed"
    assert route.call_count == 1


@pytest.mark.parametrize("status", [200, 429])
async def test_telegram_retries_rate_limit_after_server_delay(telegram_settings, respx_mock, monkeypatch, status):
    route = respx_mock.post("https://api.telegram.org/bot123:test/sendMessage").mock(side_effect=[
        httpx.Response(status, json={"ok": False, "error_code": 429, "parameters": {"retry_after": 4}}),
        httpx.Response(200, json={"ok": True}),
    ])
    sleep = AsyncMock()
    monkeypatch.setattr("picgen.notifications.asyncio.sleep", sleep)
    result = await _send_telegram_message(settings=telegram_settings, content="test")
    assert result.sent
    assert route.call_count == 2
    sleep.assert_awaited_once_with(4)


async def test_telegram_long_rate_limit_does_not_retry_prematurely(telegram_settings, respx_mock, monkeypatch):
    route = respx_mock.post("https://api.telegram.org/bot123:test/sendMessage").respond(
        429, json={"ok": False, "error_code": 429, "parameters": {"retry_after": 3600}},
    )
    sleep = AsyncMock()
    monkeypatch.setattr("picgen.notifications.asyncio.sleep", sleep)
    result = await _send_telegram_message(settings=telegram_settings, content="test")
    assert not result.sent
    assert route.call_count == 1
    sleep.assert_not_awaited()


async def test_telegram_logs_success_without_message_or_credentials(telegram_settings, respx_mock, monkeypatch):
    respx_mock.post("https://api.telegram.org/bot123:test/sendMessage").respond(200, json={"ok": True})
    events = []
    monkeypatch.setattr("picgen.notifications.log_event", lambda *args, **kwargs: events.append((args, kwargs)))
    result = await _send_telegram_message(settings=telegram_settings, content="private task prompt")
    assert result.sent
    assert any(args[2] == "telegram_notification_sent" for args, fields in events)
    assert "private task prompt" not in repr(events)
    assert "123:test" not in repr(events)

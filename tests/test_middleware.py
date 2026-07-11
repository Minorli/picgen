from __future__ import annotations

import asyncio
from collections import deque

import pytest

from picgen.main import _retention_loop
from picgen.middleware import RateLimitMiddleware, _single_message_receive


def _dummy_app(scope, receive, send):  # pragma: no cover - never invoked in these tests
    raise AssertionError("ASGI app should not be called")


def test_rate_limit_sweep_drops_idle_clients() -> None:
    mw = RateLimitMiddleware(_dummy_app, per_minute=10, burst=5)
    now = 1000.0
    # "old" was last seen well outside both windows; "recent" is still active.
    mw._minute_buckets["old"] = deque([now - 120.0])
    mw._burst_buckets["old"] = deque([now - 120.0])
    mw._minute_buckets["recent"] = deque([now - 1.0])
    mw._burst_buckets["recent"] = deque([now - 1.0])

    mw._sweep_idle(now)

    assert "old" not in mw._minute_buckets
    assert "old" not in mw._burst_buckets
    assert "recent" in mw._minute_buckets
    assert "recent" in mw._burst_buckets


async def test_replayed_disconnect_remains_disconnected() -> None:
    message = {"type": "http.disconnect"}
    receive = _single_message_receive(message)

    assert await receive() == message
    assert await receive() == message


async def test_retention_loop_noop_when_disabled(settings_factory) -> None:
    settings = settings_factory(auth_enabled=False, storage_retention_days=0)
    # Returns immediately instead of entering the sleep loop.
    await asyncio.wait_for(_retention_loop(settings), timeout=1.0)


async def test_retention_loop_runs_a_pass_when_enabled(monkeypatch, settings_factory) -> None:
    settings = settings_factory(storage_retention_days=7)
    calls: list[tuple[object, int]] = []

    def fake_prune(outputs_dir: object, retention_days: int) -> int:
        calls.append((outputs_dir, retention_days))
        return 0

    async def stop_after_first(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr("picgen.main.prune_old_outputs", fake_prune)
    monkeypatch.setattr("picgen.main.asyncio.sleep", stop_after_first)

    with pytest.raises(asyncio.CancelledError):
        await _retention_loop(settings)

    assert len(calls) == 1
    assert calls[0][1] == 7


async def test_retention_loop_prunes_expired_sessions_when_auth_enabled(monkeypatch, settings_factory) -> None:
    settings = settings_factory(auth_enabled=True, storage_retention_days=0)
    calls: list[str] = []

    class FakeAuthStore:
        def prune_expired_sessions(self) -> int:
            calls.append("sessions")
            return 2

    async def stop_after_first(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr("picgen.main.get_auth_store", lambda: FakeAuthStore())
    monkeypatch.setattr("picgen.main.asyncio.sleep", stop_after_first)

    with pytest.raises(asyncio.CancelledError):
        await _retention_loop(settings)

    assert calls == ["sessions"]

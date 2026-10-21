from __future__ import annotations

import sqlite3

from picgen.auth import AuthStore

_PASSWORD = "original secure password"
_NEW_PASSWORD = "replacement secure password"


def test_password_change_revokes_pending_reset_token_and_other_sessions(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    user = store.create_user("alice", _PASSWORD)
    current = store.create_session(user.id, days=1)
    other = store.create_session(user.id, days=1)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE users SET email = ? WHERE id = ?", ("alice@example.test", user.id))
    reset = store.request_password_reset(user.username)
    assert reset["reset_token"]

    store.change_user_password(
        user_id=user.id,
        current_password=_PASSWORD,
        new_password=_NEW_PASSWORD,
        current_session_token=current.token,
    )

    assert store.reset_password_with_token(token=reset["reset_token"], password="stolen token password") is None
    assert store.authenticate(user.username, _NEW_PASSWORD).id == user.id
    assert store.user_for_session(current.token) is not None
    assert store.user_for_session(other.token) is None
    assert store.list_password_reset_requests(status="pending") == []


def test_bootstrap_password_rotation_revokes_previous_sessions_and_reset_token(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    user = store.ensure_admin_user("admin", _PASSWORD)
    session = store.create_session(user.id, days=1)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE users SET email = ? WHERE id = ?", ("alice@example.test", user.id))
    reset = store.request_password_reset(user.username)
    assert reset["reset_token"]

    store.ensure_admin_user("admin", _NEW_PASSWORD)

    assert store.user_for_session(session.token) is None
    assert store.reset_password_with_token(token=reset["reset_token"], password="stolen token password") is None
    assert store.authenticate(user.username, _NEW_PASSWORD).id == user.id


def test_bootstrap_same_password_preserves_valid_sessions(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    user = store.ensure_admin_user("admin", _PASSWORD)
    session = store.create_session(user.id, days=1)

    store.ensure_admin_user("admin", _PASSWORD)

    assert store.user_for_session(session.token) is not None


def test_reset_token_is_consumed_once_across_workers(tmp_path, monkeypatch):
    import threading

    import picgen.auth as auth_module

    first_store = AuthStore(tmp_path / "auth.sqlite3")
    user = first_store.create_user("alice", _PASSWORD)
    with sqlite3.connect(first_store.db_path) as conn:
        conn.execute("UPDATE users SET email = ? WHERE id = ?", ("alice@example.test", user.id))
    token = first_store.request_password_reset(user.username)["reset_token"]
    second_store = AuthStore(first_store.db_path)
    second_store.initialize()
    first_validating = threading.Event()
    release_first = threading.Event()
    second_attempting = threading.Event()
    second_finished = threading.Event()
    real_parse = auth_module._parse_datetime_text
    real_connect = second_store._raw_connect
    results = []
    errors = []

    def pause_first_validation(value):
        parsed = real_parse(value)
        if threading.current_thread().name == "first-reset":
            first_validating.set()
            assert release_first.wait(timeout=5)
        return parsed

    def traced_connect():
        conn = real_connect()
        conn.set_trace_callback(lambda statement: second_attempting.set())
        return conn

    def reset(store, finished=None):
        try:
            results.append(store.reset_password_with_token(token=token, password=_NEW_PASSWORD))
        except Exception as exc:
            errors.append(exc)
        finally:
            if finished is not None:
                finished.set()

    monkeypatch.setattr(auth_module, "_parse_datetime_text", pause_first_validation)
    monkeypatch.setattr(second_store, "_raw_connect", traced_connect)
    first = threading.Thread(target=reset, args=(first_store,), name="first-reset")
    second = threading.Thread(target=reset, args=(second_store, second_finished), name="second-reset")
    first.start()
    try:
        assert first_validating.wait(timeout=5)
        second.start()
        assert second_attempting.wait(timeout=5)
        # An unprotected second worker consumes the token while the first is
        # paused; a transactional worker waits until the first commits.
        second_finished.wait(timeout=0.3)
    finally:
        release_first.set()
        first.join(timeout=5)
        if second.ident is not None:
            second.join(timeout=5)
    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert len(results) == 2
    assert sum(result is not None for result in results) == 1

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient
from test_api import TINY_PNG_B64

ADMIN_PASSWORD = "correct horse battery admin"
USER_PASSWORD = "correct horse battery"


def test_auth_required_blocks_generation(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)

    response = client.post(
        "/api/generate",
        json={
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
        },
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    fake.run_json.assert_not_awaited()


def test_ensure_columns_tolerates_duplicate_column_race():
    import sqlite3

    from picgen.auth import _ensure_columns

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class FakeConnection:
        def __init__(self):
            self.columns = {"id"}

        def execute(self, sql):
            if sql == "PRAGMA table_info(password_reset_requests)":
                return FakeResult([{"name": name} for name in sorted(self.columns)])
            if sql.startswith("ALTER TABLE password_reset_requests ADD COLUMN token_hash"):
                self.columns.add("token_hash")
                raise sqlite3.OperationalError("duplicate column name: token_hash")
            raise AssertionError(sql)

    conn = FakeConnection()
    _ensure_columns(conn, "password_reset_requests", {"token_hash": "TEXT"})

    assert "token_hash" in conn.columns


def test_bootstrap_admin_login_and_open_registration(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password=ADMIN_PASSWORD)
    client, _, _ = make_client(settings=settings)

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert register_response.status_code == 200
    assert "picgen_session=" in register_response.headers["set-cookie"]
    registered = register_response.json()["user"]
    assert registered["username"] == "alice"
    assert registered["role"] == "user"
    assert registered["is_admin"] is False
    assert registered["company"] == "6renyou"
    assert registered["department"] == "PD & OPS"

    duplicate = client.post(
        "/api/auth/register",
        json={"username": "Alice", "password": "another password"},
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["code"] == "user_exists"

    client.post("/api/auth/logout")

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    assert "picgen_session=" in login.headers["set-cookie"]
    assert login.json()["user"]["username"] == "admin"
    assert login.json()["user"]["role"] == "admin"
    assert login.json()["user"]["is_admin"] is True

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "admin"


def test_open_registration_rejects_reserved_usernames(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password=ADMIN_PASSWORD)
    client, _, _ = make_client(settings=settings)

    response = client.post(
        "/api/auth/register",
        json={"username": "admin", "password": USER_PASSWORD},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "reserved_username"


def test_login_failures_lock_account_temporarily(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True)
    client, _, _ = make_client(settings=settings)

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert register_response.status_code == 200
    client.post("/api/auth/logout")

    for _ in range(5):
        failed = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong password"},
        )
        assert failed.status_code == 400
        assert failed.json()["code"] == "invalid_credentials"

    locked = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert locked.status_code == 429
    assert locked.json()["code"] == "account_locked"


def test_login_lockout_resets_after_window_expires(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True)
    client, _, resolved_settings = make_client(settings=settings)

    register = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert register.status_code == 200
    client.post("/api/auth/logout")

    for _ in range(5):
        assert (
            client.post(
                "/api/auth/login",
                json={"username": "alice", "password": "wrong password"},
            ).status_code
            == 400
        )
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "alice", "password": USER_PASSWORD},
        ).status_code
        == 429
    )

    # Simulate the 15-minute lock window elapsing.
    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.execute(
            "UPDATE users SET locked_until = ? WHERE username_normalized = ?",
            ("2000-01-01T00:00:00+00:00", "alice"),
        )
        conn.commit()

    # A single wrong attempt after expiry must not instantly re-lock the account:
    # the failure counter starts fresh, so the correct password then succeeds.
    wrong_after_expiry = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "still wrong"},
    )
    assert wrong_after_expiry.status_code == 400
    assert wrong_after_expiry.json()["code"] == "invalid_credentials"

    success = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert success.status_code == 200


def test_verify_password_rejects_corrupt_hashes_without_raising():
    from picgen.auth import hash_password, verify_password

    stored = hash_password("correct horse battery")
    assert verify_password("correct horse battery", stored) is True
    assert verify_password("nope", stored) is False
    for corrupt in (
        "",
        "garbage",
        "x$y$z",
        "pbkdf2_sha256$notanint$abcd$abcd",
        "pbkdf2_sha256$0$abcd$abcd",  # zero iterations would crash pbkdf2_hmac if unguarded
        "pbkdf2_sha256$600000$zzzz$zzzz",  # non-hex salt/digest
        "scrypt$1$ab$cd",  # unknown algorithm
    ):
        assert verify_password("anything", corrupt) is False


def test_password_reset_request_is_admin_assisted_and_non_enumerating(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password=ADMIN_PASSWORD)
    client, _, resolved_settings = make_client(settings=settings)

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert register_response.status_code == 200
    alice_id = register_response.json()["user"]["id"]
    alice_cookie = register_response.headers["set-cookie"].split(";", 1)[0]

    first_request = client.post(
        "/api/password-reset-requests",
        json={"username": "alice"},
        headers={"user-agent": "pytest-browser"},
    )
    unknown_request = client.post(
        "/api/password-reset-requests",
        json={"username": "missing-user"},
    )
    duplicate_request = client.post(
        "/api/password-reset-requests",
        json={"username": "Alice"},
    )
    assert first_request.status_code == 200
    assert unknown_request.status_code == 200
    assert duplicate_request.status_code == 200
    assert first_request.json() == unknown_request.json() == duplicate_request.json()
    assert "exists" not in first_request.json()
    assert "user" not in first_request.json()

    user_list = client.get("/api/admin/password-reset-requests")
    assert user_list.status_code == 403
    assert user_list.json()["code"] == "forbidden"

    admin_client = TestClient(client.app)
    admin_login = admin_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert admin_login.status_code == 200

    admin_list = admin_client.get("/api/admin/password-reset-requests")
    assert admin_list.status_code == 200
    requests = admin_list.json()["requests"]
    assert sorted((item["username_normalized"], item["status"]) for item in requests) == [
        ("alice", "pending"),
        ("missing-user", "pending"),
    ]
    alice_request = next(item for item in requests if item["username_normalized"] == "alice")
    missing_request = next(item for item in requests if item["username_normalized"] == "missing-user")
    assert alice_request["user_id"] == alice_id
    assert alice_request["matched_user"] is True
    assert missing_request["user_id"] is None
    assert missing_request["matched_user"] is False

    reset_response = admin_client.put(
        f"/api/admin/users/{alice_id}/password",
        json={"password": "new correct horse battery"},
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["status"] == "ok"
    assert reset_response.json()["user"]["id"] == alice_id

    revoked = client.get("/api/me", headers={"cookie": alice_cookie})
    assert revoked.status_code == 401
    assert revoked.json()["code"] == "unauthorized"

    old_password = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert old_password.status_code == 400
    assert old_password.json()["code"] == "invalid_credentials"

    new_password = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "new correct horse battery"},
    )
    assert new_password.status_code == 200

    import sqlite3

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        sessions = conn.execute("SELECT COUNT(*) AS count FROM sessions WHERE user_id = ?", (alice_id,)).fetchone()
        assert sessions["count"] == 1
        user = conn.execute(
            """
            SELECT failed_login_count, locked_until, password_changed_at
            FROM users
            WHERE id = ?
            """,
            (alice_id,),
        ).fetchone()
        assert user["failed_login_count"] == 0
        assert user["locked_until"] is None
        assert user["password_changed_at"]
        rows = conn.execute(
            """
            SELECT username_normalized, status, resolved_at, resolved_by_user_id
            FROM password_reset_requests
            ORDER BY username_normalized
            """
        ).fetchall()
        assert [(row["username_normalized"], row["status"]) for row in rows] == [
            ("alice", "resolved"),
            ("missing-user", "pending"),
        ]
        assert rows[0]["resolved_at"]
        assert rows[0]["resolved_by_user_id"] == admin_login.json()["user"]["id"]


def test_password_reset_request_notifies_admin_without_enumerating(
    make_client,
    settings_factory,
    monkeypatch,
):
    notifications = []

    async def _fake_send_password_reset_request_notification(**kwargs):
        notifications.append(kwargs["request_info"])
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr(
        "picgen.routes.send_password_reset_request_notification",
        _fake_send_password_reset_request_notification,
    )
    settings = settings_factory(
        auth_enabled=True,
        bug_report_webhook_url="https://example.invalid/webhook",
    )
    client, _, _ = make_client(settings=settings)

    response = client.post(
        "/api/password-reset-requests",
        json={"username": "alice"},
        headers={"user-agent": "pytest-browser"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "如果账号存在且已填写邮箱，会收到重置邮件；否则管理员会看到找回申请。",
    }
    assert len(notifications) == 1
    request_info = notifications[0]
    assert request_info["username"] == "alice"
    assert request_info["username_normalized"] == "alice"
    assert request_info["matched_user"] is False
    assert request_info["user_id"] is None


def test_password_reset_request_notifies_admin_via_telegram_when_webhook_missing(
    make_client,
    settings_factory,
    monkeypatch,
):
    notifications = []

    async def _fake_send_password_reset_request_notification(**kwargs):
        notifications.append(kwargs)
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr(
        "picgen.routes.send_password_reset_request_notification",
        _fake_send_password_reset_request_notification,
    )
    settings = settings_factory(
        auth_enabled=True,
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-100123456",
    )
    client, _, _ = make_client(settings=settings)

    response = client.post("/api/password-reset-requests", json={"username": "alice"})

    assert response.status_code == 200
    assert len(notifications) == 1
    assert notifications[0]["settings"].error_alert_telegram_chat_id == "-100123456"
    assert notifications[0]["request_info"]["username_normalized"] == "alice"


def test_password_reset_email_token_allows_self_service_reset(
    make_client,
    settings_factory,
    monkeypatch,
):
    sent_emails = []
    admin_notifications = []

    def _fake_send_password_reset_email(**kwargs):
        sent_emails.append(kwargs)
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    async def _fake_send_password_reset_request_notification(**kwargs):
        admin_notifications.append(kwargs)
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr("picgen.routes.send_password_reset_email", _fake_send_password_reset_email)
    monkeypatch.setattr(
        "picgen.routes.send_password_reset_request_notification",
        _fake_send_password_reset_request_notification,
    )
    settings = settings_factory(
        auth_enabled=True,
        public_base_url="https://picgen.example.com",
        smtp_host="smtpdm.aliyun.com",
        smtp_username="noreply@example.com",
        smtp_password="mail-secret",
        smtp_from_email="noreply@example.com",
        password_reset_token_minutes=45,
    )
    client, _, _ = make_client(settings=settings)

    register = client.post("/api/auth/register", json={"username": "alice", "password": USER_PASSWORD})
    assert register.status_code == 200
    update_profile = client.put(
        "/api/me/profile",
        json={
            "username": "alice",
            "display_name": "Alice",
            "email": "alice@example.com",
            "company": "6renyou",
            "department": "PD & OPS",
        },
    )
    assert update_profile.status_code == 200
    client.post("/api/auth/logout")

    request = client.post("/api/password-reset-requests", json={"username": "Alice"})
    assert request.status_code == 200
    assert request.json() == {
        "status": "ok",
        "message": "如果账号存在且已填写邮箱，会收到重置邮件；否则管理员会看到找回申请。",
    }
    assert len(sent_emails) == 1
    assert admin_notifications == []
    email = sent_emails[0]
    assert email["to_email"] == "alice@example.com"
    assert email["username"] == "alice"
    assert email["expires_minutes"] == 45
    assert email["reset_url"].startswith("https://picgen.example.com/?reset_token=")
    token = email["reset_url"].split("reset_token=", 1)[1]

    reset = client.post(
        "/api/password-reset/confirm",
        json={"token": token, "password": "fresh correct horse battery"},
    )
    assert reset.status_code == 200
    assert reset.json()["message"] == "密码已重置，请使用新密码登录。"

    reused = client.post(
        "/api/password-reset/confirm",
        json={"token": token, "password": "another correct horse battery"},
    )
    assert reused.status_code == 400
    assert reused.json()["code"] == "invalid_reset_token"

    old_login = client.post("/api/auth/login", json={"username": "alice", "password": USER_PASSWORD})
    assert old_login.status_code == 400
    new_login = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "fresh correct horse battery"},
    )
    assert new_login.status_code == 200


def test_password_reset_without_email_keeps_admin_fallback(
    make_client,
    settings_factory,
    monkeypatch,
):
    sent_emails = []
    admin_notifications = []

    def _fake_send_password_reset_email(**kwargs):
        sent_emails.append(kwargs)
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    async def _fake_send_password_reset_request_notification(**kwargs):
        admin_notifications.append(kwargs["request_info"])
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr("picgen.routes.send_password_reset_email", _fake_send_password_reset_email)
    monkeypatch.setattr(
        "picgen.routes.send_password_reset_request_notification",
        _fake_send_password_reset_request_notification,
    )
    settings = settings_factory(
        auth_enabled=True,
        smtp_host="smtpdm.aliyun.com",
        smtp_username="noreply@example.com",
        smtp_password="mail-secret",
        smtp_from_email="noreply@example.com",
    )
    client, _, _ = make_client(settings=settings)
    register = client.post("/api/auth/register", json={"username": "alice", "password": USER_PASSWORD})
    assert register.status_code == 200
    client.post("/api/auth/logout")

    response = client.post("/api/password-reset-requests", json={"username": "alice"})

    assert response.status_code == 200
    assert sent_emails == []
    assert len(admin_notifications) == 1
    assert admin_notifications[0]["email_available"] is False
    assert admin_notifications[0]["reset_token"] == ""


def test_password_reset_email_requires_public_base_url_to_avoid_host_poisoning(
    make_client,
    settings_factory,
    monkeypatch,
):
    sent_emails = []
    admin_notifications = []

    def _fake_send_password_reset_email(**kwargs):
        sent_emails.append(kwargs)
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    async def _fake_send_password_reset_request_notification(**kwargs):
        admin_notifications.append(kwargs["request_info"])
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr("picgen.routes.send_password_reset_email", _fake_send_password_reset_email)
    monkeypatch.setattr(
        "picgen.routes.send_password_reset_request_notification",
        _fake_send_password_reset_request_notification,
    )
    settings = settings_factory(
        auth_enabled=True,
        smtp_host="smtpdm.aliyun.com",
        smtp_username="noreply@example.com",
        smtp_password="mail-secret",
        smtp_from_email="noreply@example.com",
    )
    client, _, _ = make_client(settings=settings)
    register = client.post("/api/auth/register", json={"username": "alice", "password": USER_PASSWORD})
    assert register.status_code == 200
    update_profile = client.put(
        "/api/me/profile",
        json={
            "username": "alice",
            "display_name": "Alice",
            "email": "alice@example.com",
            "company": "6renyou",
            "department": "PD & OPS",
        },
    )
    assert update_profile.status_code == 200
    client.post("/api/auth/logout")

    response = client.post(
        "/api/password-reset-requests",
        json={"username": "alice"},
        headers={"host": "evil.example"},
    )

    assert response.status_code == 200
    assert sent_emails == []
    assert len(admin_notifications) == 1
    assert admin_notifications[0]["email_available"] is False
    assert admin_notifications[0]["reset_token"] == ""


def test_password_reset_request_suppresses_recent_duplicate_email(
    make_client,
    settings_factory,
    monkeypatch,
):
    sent_emails = []
    admin_notifications = []

    def _fake_send_password_reset_email(**kwargs):
        sent_emails.append(kwargs)
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    async def _fake_send_password_reset_request_notification(**kwargs):
        admin_notifications.append(kwargs["request_info"])
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr("picgen.routes.send_password_reset_email", _fake_send_password_reset_email)
    monkeypatch.setattr(
        "picgen.routes.send_password_reset_request_notification",
        _fake_send_password_reset_request_notification,
    )
    settings = settings_factory(
        auth_enabled=True,
        public_base_url="https://picgen.example.com",
        smtp_host="smtpdm.aliyun.com",
        smtp_username="noreply@example.com",
        smtp_password="mail-secret",
        smtp_from_email="noreply@example.com",
    )
    client, _, _ = make_client(settings=settings)
    register = client.post("/api/auth/register", json={"username": "alice", "password": USER_PASSWORD})
    assert register.status_code == 200
    update_profile = client.put(
        "/api/me/profile",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "company": "6renyou",
            "department": "PD & OPS",
        },
    )
    assert update_profile.status_code == 200
    client.post("/api/auth/logout")

    first = client.post("/api/password-reset-requests", json={"username": "alice"})
    second = client.post("/api/password-reset-requests", json={"username": "alice"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(sent_emails) == 1
    assert admin_notifications == []


def test_password_reset_request_suppresses_recent_duplicate_admin_notification(
    make_client,
    settings_factory,
    monkeypatch,
):
    admin_notifications = []

    async def _fake_send_password_reset_request_notification(**kwargs):
        admin_notifications.append(kwargs["request_info"])
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr(
        "picgen.routes.send_password_reset_request_notification",
        _fake_send_password_reset_request_notification,
    )
    settings = settings_factory(
        auth_enabled=True,
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-1",
    )
    client, _, _ = make_client(settings=settings)

    first = client.post("/api/password-reset-requests", json={"username": "unknown"})
    second = client.post("/api/password-reset-requests", json={"username": "unknown"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(admin_notifications) == 1


def test_user_can_change_own_password_and_other_sessions_are_revoked(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True)
    client, _, _ = make_client(settings=settings)

    register = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert register.status_code == 200
    first_cookie = register.headers["set-cookie"].split(";", 1)[0]

    second_client = TestClient(client.app)
    second_login = second_client.post(
        "/api/auth/login",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert second_login.status_code == 200
    second_cookie = second_login.headers["set-cookie"].split(";", 1)[0]

    wrong_current_password = client.put(
        "/api/me/password",
        json={"current_password": "wrong password", "new_password": "new correct horse battery"},
    )
    assert wrong_current_password.status_code == 400
    assert wrong_current_password.json()["code"] == "invalid_credentials"

    changed = client.put(
        "/api/me/password",
        json={"current_password": USER_PASSWORD, "new_password": "new correct horse battery"},
    )
    assert changed.status_code == 200
    assert changed.json()["status"] == "ok"
    assert changed.json()["user"]["username"] == "alice"

    current_session = client.get("/api/me", headers={"cookie": first_cookie})
    assert current_session.status_code == 200
    revoked_other_session = second_client.get("/api/me", headers={"cookie": second_cookie})
    assert revoked_other_session.status_code == 401

    old_password = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert old_password.status_code == 400
    assert old_password.json()["code"] == "invalid_credentials"

    new_password = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "new correct horse battery"},
    )
    assert new_password.status_code == 200


def test_user_profile_can_update_username_and_optional_fields(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True)
    client, _, _ = make_client(settings=settings)

    register = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert register.status_code == 200

    missing_password = client.put(
        "/api/me/profile",
        json={
            "username": "alice-new",
            "display_name": "Alice 昵称",
        },
    )
    assert missing_password.status_code == 400
    assert missing_password.json()["code"] == "current_password_required"

    updated = client.put(
        "/api/me/profile",
        json={
            "username": "alice-new",
            "current_password": USER_PASSWORD,
            "display_name": "Alice 昵称",
            "wechat": "alice-wx",
            "phone_country_code": "+86",
            "phone": "13800138000",
            "email": "alice@example.com",
            "company": "6renyou",
            "department": "PD & OPS",
            "team": "市场部",
            "job_title": "设计运营",
            "note": "偏好旅行海报和酒店质感。",
        },
    )
    assert updated.status_code == 200
    profile = updated.json()["user"]
    assert profile["username"] == "alice-new"
    assert profile["display_name"] == "Alice 昵称"
    assert profile["wechat"] == "alice-wx"
    assert profile["phone_country_code"] == "+86"
    assert profile["phone"] == "13800138000"
    assert profile["email"] == "alice@example.com"
    assert profile["company"] == "6renyou"
    assert profile["department"] == "PD & OPS"
    assert profile["team"] == "市场部"
    assert profile["job_title"] == "设计运营"
    assert profile["note"] == "偏好旅行海报和酒店质感。"

    old_username_login = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert old_username_login.status_code == 400

    new_username_login = client.post(
        "/api/auth/login",
        json={"username": "alice-new", "password": USER_PASSWORD},
    )
    assert new_username_login.status_code == 200


def test_user_profile_rejects_reserved_username(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True)
    client, _, _ = make_client(settings=settings)
    register = client.post("/api/auth/register", json={"username": "alice", "password": USER_PASSWORD})
    assert register.status_code == 200

    response = client.put(
        "/api/me/profile",
        json={"username": "admin", "current_password": USER_PASSWORD},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "reserved_username"


def test_user_profile_rejects_duplicate_username_and_saves_avatar(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True)
    client, _, resolved_settings = make_client(settings=settings)

    alice = client.post("/api/auth/register", json={"username": "alice", "password": USER_PASSWORD})
    assert alice.status_code == 200
    client.post("/api/auth/logout")
    bob = client.post("/api/auth/register", json={"username": "bob", "password": USER_PASSWORD})
    assert bob.status_code == 200

    duplicate = client.put(
        "/api/me/profile",
        json={"username": "alice", "current_password": USER_PASSWORD},
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["code"] == "user_exists"

    avatar = client.post(
        "/api/me/avatar",
        json={
            "image": {
                "name": "avatar.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            }
        },
    )
    assert avatar.status_code == 200
    payload = avatar.json()
    assert payload["user"]["avatar_url"].startswith("files/avatars/")
    assert "avatar_path" not in payload["user"]
    assert (resolved_settings.data_dir / "avatars").is_dir()

    avatar_file = client.get(f"/{payload['user']['avatar_url']}")
    assert avatar_file.status_code == 200
    assert avatar_file.headers["content-type"].startswith("image/png")

    blocked_json = client.get("/files/avatars/profile.json")
    assert blocked_json.status_code == 403


def test_admin_creates_user_and_usage_scope_is_role_limited(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password=ADMIN_PASSWORD,
        default_api_key="sk-test",
    )
    client, fake, resolved_settings = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    admin_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert admin_login.status_code == 200

    create_response = client.post(
        "/api/admin/users",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert create_response.status_code == 200
    created = create_response.json()["user"]
    assert created["username"] == "alice"
    assert created["role"] == "user"
    assert created["is_active"] is True
    assert created["company"] == "6renyou"
    assert created["department"] == "PD & OPS"

    admin_users = client.get("/api/admin/users")
    assert admin_users.status_code == 200
    assert {user["username"] for user in admin_users.json()["users"]} == {"admin", "alice"}

    client.post("/api/auth/logout")
    user_login = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert user_login.status_code == 200

    me_response = client.get("/api/me")
    assert me_response.status_code == 200
    assert me_response.json()["user"]["username"] == "alice"
    assert me_response.json()["user"]["role"] == "user"

    generate_response = client.post(
        "/api/generate",
        json={
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
        },
    )

    assert generate_response.status_code == 200
    payload = generate_response.json()
    assert payload["user"]["username"] == "alice"
    assert payload["saved_metadata_path"] == ""
    assert payload["saved_metadata_url"] == ""
    assert payload["generation_job_id"] > 0
    assert payload["generated_image_id"] > 0
    assert payload["saved_image_name"].startswith("alice-generate-")
    assert not list(Path(payload["saved_image_path"]).parent.glob("*.json"))

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        metadata_row = conn.execute(
            "SELECT metadata_json FROM generated_image_metadata WHERE generated_image_id = ?",
            (payload["generated_image_id"],),
        ).fetchone()
    assert metadata_row is not None
    metadata = json.loads(metadata_row["metadata_json"])
    assert metadata["user_id"] == created["id"]
    assert metadata["username"] == "alice"
    assert metadata["saved_image_width"] == 1088
    assert metadata["saved_image_height"] == 2240
    assert metadata["upstream_actual_size"] == "1x1"
    assert metadata["image_size_normalized"] is True

    fetched_image = client.get(f"/{payload['saved_image_url']}")
    assert fetched_image.status_code == 200
    assert fetched_image.headers["cache-control"] == "private, max-age=31536000, immutable"

    user_usage_response = client.get("/api/usage")
    assert user_usage_response.status_code == 200
    user_usage = user_usage_response.json()
    assert user_usage["scope"] == "self"
    assert user_usage["current_user"]["username"] == "alice"
    assert [row["username"] for row in user_usage["users"]] == ["alice"]
    assert user_usage["users"][0]["request_count"] == 1
    assert user_usage["users"][0]["image_count"] == 1
    assert user_usage["users"][0]["saved_bytes"] > 0
    assert user_usage["users"][0]["generated_image_count"] == 1
    assert user_usage["users"][0]["delivered_image_count"] == 1

    image_stats_response = client.get("/api/image-stats")
    assert image_stats_response.status_code == 200
    image_stats = image_stats_response.json()["stats"]
    assert image_stats == {
        "current_user_generated_image_count": 1,
        "platform_generated_image_count": 1,
    }

    forbidden_admin = client.get("/api/admin/users")
    assert forbidden_admin.status_code == 403
    assert forbidden_admin.json()["code"] == "forbidden"

    client.post("/api/auth/logout")
    admin_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert admin_login.status_code == 200

    admin_usage_response = client.get("/api/usage")
    assert admin_usage_response.status_code == 200
    admin_usage = admin_usage_response.json()
    assert admin_usage["scope"] == "all"
    usage_by_name = {row["username"]: row for row in admin_usage["users"]}
    assert usage_by_name["admin"]["request_count"] == 0
    assert usage_by_name["alice"]["request_count"] == 1

    admin_image_stats_response = client.get("/api/image-stats")
    assert admin_image_stats_response.status_code == 200
    admin_image_stats = admin_image_stats_response.json()["stats"]
    assert admin_image_stats["current_user_generated_image_count"] == 0
    assert admin_image_stats["platform_generated_image_count"] == 1


def test_result_feedback_is_recorded_and_admin_can_review_summary(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password=ADMIN_PASSWORD,
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert register_response.status_code == 200

    generate_response = client.post(
        "/api/generate",
        json={
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
        },
    )
    assert generate_response.status_code == 200
    generated = generate_response.json()

    feedback_response = client.post(
        "/api/feedback",
        json={
            "rating": "bad",
            "reason": "人物手部变形，文字也不清楚",
            "prompt": generated["prompt"],
            "mode": generated["mode"],
            "model": generated["model"],
            "saved_image_path": generated["saved_image_path"],
            "saved_image_url": generated["saved_image_url"],
            "generated_image_id": generated["generated_image_id"],
        },
    )
    assert feedback_response.status_code == 200
    feedback = feedback_response.json()["feedback"]
    assert feedback["rating"] == "bad"
    assert feedback["reason"] == "人物手部变形，文字也不清楚"
    assert feedback["generated_image_id"] == generated["generated_image_id"]

    user_summary = client.get("/api/feedback/summary")
    assert user_summary.status_code == 403
    assert user_summary.json()["code"] == "forbidden"

    client.post("/api/auth/logout")
    admin_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert admin_login.status_code == 200

    summary_response = client.get("/api/feedback/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["totals"]["bad"] == 1
    assert summary["totals"]["ok"] == 0
    assert summary["totals"]["good"] == 0
    assert summary["total_count"] == 1
    assert summary["satisfaction_rate"] == 0.0
    assert summary["recent"][0]["username"] == "alice"
    assert summary["recent"][0]["reason"] == "人物手部变形，文字也不清楚"
    assert summary["recent"][0]["generated_image_id"] == generated["generated_image_id"]


def test_auth_store_migrates_legacy_database_and_tracks_generation_lifecycle(make_client, settings_factory, tmp_path):
    db_path = tmp_path / "data" / "legacy.sqlite3"
    db_path.parent.mkdir(parents=True)
    legacy_output_dir = tmp_path / "data" / "outputs" / "20260608"
    legacy_output_dir.mkdir(parents=True)
    legacy_image_path = legacy_output_dir / "legacy-generate-120000-deadbeef.png"
    legacy_metadata_path = legacy_output_dir / "legacy-generate-120000-deadbeef.json"
    legacy_image_path.write_bytes(b"legacy-image")
    legacy_metadata_path.write_text(
        json.dumps(
            {
                "mode": "generate",
                "prompt": "旧图提示词",
                "model": "gpt-image-2",
                "saved_image_width": 1024,
                "saved_image_height": 1024,
                "saved_image_bytes": len(b"legacy-image"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                username_normalized TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT
            );
            CREATE TABLE usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                endpoint_path TEXT NOT NULL,
                mode TEXT NOT NULL,
                image_count INTEGER NOT NULL DEFAULT 0,
                saved_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE password_reset_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT NOT NULL,
                username_normalized TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requested_ip TEXT NOT NULL DEFAULT '',
                user_agent TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                resolved_by_user_id INTEGER
            );
            CREATE TABLE generation_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL DEFAULT '',
                user_id INTEGER,
                username TEXT NOT NULL DEFAULT '',
                endpoint_path TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT '',
                transport TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'succeeded',
                prompt TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                size TEXT NOT NULL DEFAULT '',
                sample_count INTEGER NOT NULL DEFAULT 1,
                logo_requested INTEGER NOT NULL DEFAULT 0,
                image_count INTEGER NOT NULL DEFAULT 1,
                saved_bytes INTEGER NOT NULL DEFAULT 0,
                error_code TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                elapsed_ms REAL
            );
            CREATE TABLE generated_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                user_id INTEGER,
                candidate_index INTEGER NOT NULL DEFAULT 0,
                mode TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                prompt TEXT NOT NULL DEFAULT '',
                saved_image_path TEXT NOT NULL DEFAULT '',
                saved_image_url TEXT NOT NULL DEFAULT '',
                saved_image_name TEXT NOT NULL DEFAULT '',
                saved_metadata_path TEXT NOT NULL DEFAULT '',
                saved_metadata_url TEXT NOT NULL DEFAULT '',
                saved_image_mime TEXT NOT NULL DEFAULT '',
                saved_image_width INTEGER,
                saved_image_height INTEGER,
                saved_image_bytes INTEGER NOT NULL DEFAULT 0,
                logo_requested INTEGER NOT NULL DEFAULT 0,
                logo_overlay_applied INTEGER NOT NULL DEFAULT 0,
                first_served_at TEXT,
                last_served_at TEXT,
                served_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO generation_jobs (
                id, request_id, endpoint_path, mode, transport, status, prompt, model, size,
                sample_count, image_count, saved_bytes, started_at, completed_at
            )
            VALUES (99, 'legacy-request', '/api/generate', 'generate', 'images-generate', 'succeeded',
                    '旧图提示词', 'gpt-image-2', '1024x1024', 1, 1, ?, '2026-06-08T12:00:00+00:00',
                    '2026-06-08T12:00:10+00:00')
            """,
            (len(b"legacy-image"),),
        )
        conn.execute(
            """
            INSERT INTO generated_images (
                id, job_id, candidate_index, mode, model, prompt, saved_image_path, saved_image_url,
                saved_image_name, saved_metadata_path, saved_metadata_url, saved_image_mime,
                saved_image_width, saved_image_height, saved_image_bytes, created_at
            )
            VALUES (101, 99, 0, 'generate', 'gpt-image-2', '旧图提示词', ?, ?,
                    'legacy-generate-120000-deadbeef.png', ?, ?, 'image/png',
                    1024, 1024, ?, '2026-06-08T12:00:10+00:00')
            """,
            (
                str(legacy_image_path),
                "files/outputs/20260608/legacy-generate-120000-deadbeef.png",
                str(legacy_metadata_path),
                "files/outputs/20260608/legacy-generate-120000-deadbeef.json",
                len(b"legacy-image"),
            ),
        )

    settings = settings_factory(
        auth_enabled=True,
        auth_db_path=db_path,
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    register_response = client.post("/api/auth/register", json={"username": "wilson wei", "password": USER_PASSWORD})
    assert register_response.status_code == 400

    register_response = client.post("/api/auth/register", json={"username": "wilsonwei", "password": USER_PASSWORD})
    assert register_response.status_code == 200
    user_id = register_response.json()["user"]["id"]

    generate_response = client.post(
        "/api/generate",
        json={
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
            "sample_count": 1,
            "logo_requested": True,
        },
    )
    assert generate_response.status_code == 200
    generated = generate_response.json()
    assert generated["generation_job_id"] > 0
    assert generated["generated_image_id"] > 0
    assert generated["saved_image_name"].startswith("wilsonwei-generate-")

    file_response = client.get(f"/{generated['saved_image_url']}")
    assert file_response.status_code == 200

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "schema_migrations" in tables
        assert "password_reset_requests" in tables
        assert "user_preferences" in tables
        assert "generation_jobs" in tables
        assert "generated_images" in tables
        assert "generated_image_metadata" in tables
        assert "gallery_image_metadata" in tables
        assert "gallery_image_tags" in tables
        assert "image_delivery_events" in tables
        password_reset_columns = {row["name"] for row in conn.execute("PRAGMA table_info(password_reset_requests)")}
        assert {"token_hash", "email", "email_sent_at", "expires_at"}.issubset(password_reset_columns)
        password_reset_indexes = {row["name"] for row in conn.execute("PRAGMA index_list(password_reset_requests)")}
        assert "idx_password_reset_token_hash" in password_reset_indexes
        gallery_metadata_indexes = {row["name"] for row in conn.execute("PRAGMA index_list(gallery_image_metadata)")}
        gallery_tag_indexes = {row["name"] for row in conn.execute("PRAGMA index_list(gallery_image_tags)")}
        assert "idx_gallery_metadata_user_favorite" in gallery_metadata_indexes
        assert "idx_gallery_tags_user_tag" in gallery_tag_indexes
        assert "idx_gallery_tags_image" in gallery_tag_indexes
        generation_job_columns = {row["name"] for row in conn.execute("PRAGMA table_info(generation_jobs)")}
        assert {"original_prompt", "prompt_mode", "recipe_id", "recipe_version"}.issubset(generation_job_columns)
        user = conn.execute(
            "SELECT role, is_active, company, department, last_seen_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        assert user["role"] == "user"
        assert bool(user["is_active"])
        assert user["company"] == "6renyou"
        assert user["department"] == "PD & OPS"
        assert user["last_seen_at"]
        job = conn.execute(
            "SELECT * FROM generation_jobs WHERE id = ?",
            (generated["generation_job_id"],),
        ).fetchone()
        assert job["user_id"] == user_id
        assert job["status"] == "succeeded"
        assert job["mode"] == "generate"
        assert job["logo_requested"] == 1
        assert job["original_prompt"] == "生成一张旅行海报"
        assert job["prompt_mode"] == "free"
        assert job["recipe_id"] == ""
        image = conn.execute(
            "SELECT * FROM generated_images WHERE id = ?",
            (generated["generated_image_id"],),
        ).fetchone()
        assert image["job_id"] == job["id"]
        assert image["user_id"] == user_id
        assert image["saved_image_name"].startswith("wilsonwei-generate-")
        assert image["served_count"] == 1
        delivery = conn.execute("SELECT * FROM image_delivery_events").fetchone()
        assert delivery["generated_image_id"] == image["id"]
        legacy_metadata = conn.execute(
            "SELECT metadata_json FROM generated_image_metadata WHERE generated_image_id = 101"
        ).fetchone()
        assert legacy_metadata is not None
        assert json.loads(legacy_metadata["metadata_json"])["prompt"] == "旧图提示词"
        new_metadata = conn.execute(
            "SELECT metadata_json FROM generated_image_metadata WHERE generated_image_id = ?",
            (generated["generated_image_id"],),
        ).fetchone()
        assert new_metadata is not None
    assert not legacy_metadata_path.exists()


def test_final_logo_image_upload_replaces_canonical_generated_image_and_notifies_once(
    make_client, settings_factory
):
    alerts = []

    async def _fake_send_generation_success_notification(**kwargs):
        alerts.append(kwargs["alert"])
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    settings = settings_factory(
        auth_enabled=True,
        default_api_key="sk-test",
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-100123456",
    )
    client, fake, resolved_settings = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    import picgen.routes

    original_notifier = picgen.routes.send_generation_success_notification
    picgen.routes.send_generation_success_notification = _fake_send_generation_success_notification

    try:
        register_response = client.post(
            "/api/auth/register",
            json={"username": "alice", "password": USER_PASSWORD},
        )
        assert register_response.status_code == 200

        generate_response = client.post(
            "/api/generate",
            json={
                "prompt": "生成一张旅行海报",
                "model": "gpt-image-2",
                "logo_requested": True,
            },
        )
        assert generate_response.status_code == 200
        generated = generate_response.json()
        original_url = generated["saved_image_url"]
        generated_image_id = generated["generated_image_id"]

        assert alerts == []

        final_response = client.post(
            "/api/final-images",
            json={
                "generated_image_id": generated_image_id,
                "source_saved_image_url": original_url,
                "logo_overlay_applied": True,
                "logo_overlay_source": "6renyou.png",
                "logo_text_color": "black",
                "image": {
                    "name": "result-logo.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            },
        )
        duplicate_final_response = client.post(
            "/api/final-images",
            json={
                "generated_image_id": generated_image_id,
                "source_saved_image_url": original_url,
                "logo_overlay_applied": True,
                "logo_overlay_source": "6renyou.png",
                "logo_text_color": "black",
                "image": {
                    "name": "result-logo-again.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            },
        )
    finally:
        picgen.routes.send_generation_success_notification = original_notifier
    assert final_response.status_code == 200
    assert duplicate_final_response.status_code == 200
    final_payload = final_response.json()["image"]
    assert final_payload["generated_image_id"] == generated_image_id
    assert final_payload["saved_image_url"] != original_url
    assert final_payload["saved_image_name"].startswith("alice-generate-")
    assert final_payload["saved_image_name"].endswith("-logo.png")
    assert final_payload["logo_overlay_applied"] is True
    assert final_payload["saved_metadata_path"] == ""
    assert final_payload["saved_metadata_url"] == ""
    assert Path(final_payload["saved_image_path"]).is_file()
    assert not Path(final_payload["saved_image_path"]).with_suffix(".json").exists()

    fetched = client.get(f"/{final_payload['saved_image_url']}")
    assert fetched.status_code == 200
    assert fetched.content == Path(final_payload["saved_image_path"]).read_bytes()

    import sqlite3

    duplicate_payload = duplicate_final_response.json()["image"]
    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        image = conn.execute(
            "SELECT * FROM generated_images WHERE id = ?",
            (generated_image_id,),
        ).fetchone()
        assert image["saved_image_url"] == duplicate_payload["saved_image_url"]
        assert image["saved_image_path"] == duplicate_payload["saved_image_path"]
        assert image["saved_metadata_url"] == duplicate_payload["saved_metadata_url"]
        assert image["logo_overlay_applied"] == 1
        metadata_row = conn.execute(
            "SELECT metadata_json FROM generated_image_metadata WHERE generated_image_id = ?",
            (generated_image_id,),
        ).fetchone()
        assert metadata_row is not None
        metadata = json.loads(metadata_row["metadata_json"])
        assert metadata["source_saved_image_url"] in {original_url, final_payload["saved_image_url"]}
        assert metadata["logo_overlay_applied"] is True
        assert metadata["logo_overlay_source"] == "6renyou.png"
    assert len(alerts) == 1
    final_alert = alerts[0]
    assert final_alert.path == "/api/final-images"
    assert final_alert.mode == "generate"
    assert final_alert.logo_requested is True
    assert final_alert.logo_overlay_applied is True
    assert final_alert.saved_image_urls == [final_payload["saved_image_url"]]
    assert final_alert.generated_image_ids == [generated_image_id]


def test_logo_final_image_detail_exposes_original_source_and_edit_lineage_is_inferred(
    make_client, settings_factory
):
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, fake, resolved_settings = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    fake.run_multipart.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 2}

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert register_response.status_code == 200

    generate_response = client.post(
        "/api/generate",
        json={
            "prompt": "生成一张亲子研学海报",
            "model": "gpt-image-2",
            "logo_requested": True,
        },
    )
    assert generate_response.status_code == 200
    generated = generate_response.json()
    generated_image_id = generated["generated_image_id"]
    original_url = generated["saved_image_url"]
    original_path = generated["saved_image_path"]

    final_response = client.post(
        "/api/final-images",
        json={
            "generated_image_id": generated_image_id,
            "source_saved_image_url": original_url,
            "logo_overlay_applied": True,
            "logo_overlay_source": "6renyou.png",
            "image": {
                "name": "result-logo.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )
    assert final_response.status_code == 200
    final_image = final_response.json()["image"]
    assert final_image["saved_image_url"] != original_url

    detail_response = client.get(f"/api/generated-images/{generated_image_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["image"]
    assert detail["saved_image_url"] == final_image["saved_image_url"]
    assert detail["original_saved_image_url"] == original_url
    assert detail["original_saved_image_path"] == original_path
    assert detail["metadata"]["source_saved_image_url"] == original_url

    edit_response = client.post(
        "/api/edit",
        json={
            "prompt": "只把标题调小一点",
            "model": "gpt-image-2",
            "logo_requested": True,
            "source_saved_image_url": detail["original_saved_image_url"],
            "source_saved_image_path": detail["original_saved_image_path"],
            "image": {
                "name": final_image["saved_image_name"],
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )
    assert edit_response.status_code == 200
    edited = edit_response.json()
    assert edited["source_generated_image_id"] == generated_image_id
    assert fake.run_multipart.await_args is not None

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        child = conn.execute(
            """
            SELECT source_generated_image_id
            FROM generated_images
            WHERE job_id = ?
            """,
            (edited["generation_job_id"],),
        ).fetchone()
    assert child is not None
    assert child["source_generated_image_id"] == generated_image_id


def test_user_preferences_are_persisted_without_api_key(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, _, _ = make_client(settings=settings)

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert register_response.status_code == 200

    empty_response = client.get("/api/preferences")
    assert empty_response.status_code == 200
    empty_preferences = empty_response.json()["preferences"]
    assert empty_preferences["default_model"] == ""
    assert "api_key" not in empty_preferences

    preference_payload = {
        "default_model": "gpt-image-2",
        "default_responses_model": "gpt-5.5",
        "default_size": "1088x2240",
        "default_quality": "high",
        "default_output_format": "webp",
        "default_image_transport": "responses",
        "logo_overlay_enabled": False,
        "auto_copyright_check_enabled": False,
        "api_key": "sk-should-be-ignored",
    }
    update_response = client.put("/api/preferences", json=preference_payload)
    assert update_response.status_code == 200
    preferences = update_response.json()["preferences"]
    assert preferences["default_model"] == "gpt-image-2"
    assert preferences["default_responses_model"] == "gpt-5.6-sol"
    assert preferences["default_size"] == "1088x2240"
    assert preferences["default_quality"] == "high"
    assert preferences["default_output_format"] == "webp"
    assert preferences["default_image_transport"] == "responses"
    assert preferences["logo_overlay_enabled"] is False
    assert preferences["auto_copyright_check_enabled"] is False
    assert "api_key" not in preferences

    manual_response = client.put(
        "/api/preferences",
        json={**preference_payload, "responses_model_storage_version": 3},
    )
    assert manual_response.status_code == 200
    preferences = manual_response.json()["preferences"]
    assert preferences["default_responses_model"] == "gpt-5.6-sol"

    manual_response = client.put(
        "/api/preferences",
        json={**preference_payload, "responses_model_storage_version": 4},
    )
    assert manual_response.status_code == 200
    preferences = manual_response.json()["preferences"]
    assert preferences["default_responses_model"] == "gpt-5.5"

    fetched_response = client.get("/api/preferences")
    assert fetched_response.status_code == 200
    assert fetched_response.json()["preferences"] == preferences


def test_legacy_gpt55_preference_is_migrated_again_from_schema_v10_once(tmp_path: Path) -> None:
    from picgen.auth import AuthStore

    db_path = tmp_path / "auth.sqlite3"
    store = AuthStore(db_path)
    store.initialize()
    user = store.create_user("legacy-model-user", USER_PASSWORD)
    store.update_user_preferences(
        user_id=user.id,
        default_responses_model="gpt-5.5",
        default_size="1088x2240",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version = 11")
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (10, ?, ?)",
            ("gpt_5_6_sol_preferences_retry", "2026-07-10T00:00:00+00:00"),
        )

    migrated = AuthStore(db_path)
    migrated.initialize()
    assert migrated.get_user_preferences(user_id=user.id)["default_responses_model"] == "gpt-5.6-sol"
    with sqlite3.connect(db_path) as conn:
        migration = conn.execute(
            "SELECT name FROM schema_migrations WHERE version = 11"
        ).fetchone()
    assert migration == ("gpt_5_6_sol_preferences_v4",)

    migrated.update_user_preferences(
        user_id=user.id,
        default_responses_model="gpt-5.5",
        default_size="1088x2240",
    )
    restarted = AuthStore(db_path)
    restarted.initialize()
    assert restarted.get_user_preferences(user_id=user.id)["default_responses_model"] == "gpt-5.5"


def test_bug_report_is_recorded_and_admin_can_review_it(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password=ADMIN_PASSWORD)
    client, _, _ = make_client(settings=settings)

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
        headers={"user-agent": "pytest-browser"},
    )
    assert register_response.status_code == 200

    report_response = client.post(
        "/api/bug-reports",
        json={
            "title": "下载按钮没有反应",
            "description": "点击下载后没有保存图片，也没有错误提示。",
            "contact": "wechat: alice",
            "page_url": "http://testserver/#resultPanel",
        },
    )
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert report_payload["notification"]["configured"] is False
    assert report_payload["report"]["notification_status"] == "not_configured"
    assert report_payload["report"]["title"] == "下载按钮没有反应"

    user_list = client.get("/api/bug-reports")
    assert user_list.status_code == 403
    assert user_list.json()["code"] == "forbidden"

    client.post("/api/auth/logout")
    admin_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert admin_login.status_code == 200

    admin_reports = client.get("/api/bug-reports")
    assert admin_reports.status_code == 200
    reports = admin_reports.json()["reports"]
    assert len(reports) == 1
    assert reports[0]["username"] == "alice"
    assert reports[0]["description"] == "点击下载后没有保存图片，也没有错误提示。"
    assert reports[0]["notification_status"] == "not_configured"


def test_bug_report_uses_telegram_admin_notification_when_configured(
    make_client,
    settings_factory,
    monkeypatch,
):
    notifications = []

    async def _fake_send_bug_report_notification(**kwargs):
        notifications.append(kwargs)
        from picgen.notifications import NotificationResult

        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr("picgen.routes.send_bug_report_notification", _fake_send_bug_report_notification)
    settings = settings_factory(
        auth_enabled=True,
        error_alert_telegram_bot_token="123:abc",
        error_alert_telegram_chat_id="-100123456",
    )
    client, _, _ = make_client(settings=settings)

    register_response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert register_response.status_code == 200

    report_response = client.post(
        "/api/bug-reports",
        json={
            "title": "下载按钮没有反应",
            "description": "点击下载后没有保存图片，也没有错误提示。",
            "contact": "wechat: alice",
        },
    )

    assert report_response.status_code == 200
    payload = report_response.json()
    assert payload["notification"]["configured"] is True
    assert payload["notification"]["sent"] is True
    assert payload["report"]["notification_status"] == "sent"
    assert len(notifications) == 1
    assert notifications[0]["settings"].error_alert_telegram_chat_id == "-100123456"
    assert notifications[0]["username"] == "alice"


def test_result_share_flow_between_users(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password=ADMIN_PASSWORD,
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    alice = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert alice.status_code == 200
    alice_id = alice.json()["user"]["id"]
    client.post("/api/auth/logout")

    bob = client.post(
        "/api/auth/register",
        json={"username": "bob", "password": USER_PASSWORD},
    )
    assert bob.status_code == 200
    bob_id = bob.json()["user"]["id"]
    client.post("/api/auth/logout")

    alice_login = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert alice_login.status_code == 200

    users_response = client.get("/api/users")
    assert users_response.status_code == 200
    share_users = users_response.json()["users"]
    assert {user["username"] for user in share_users} == {"admin", "bob"}
    assert alice_id not in {user["id"] for user in share_users}
    assert all(set(user) == {"id", "username", "display_name", "avatar_url"} for user in share_users)
    assert all("phone" not in user and "email" not in user and "wechat" not in user for user in share_users)

    generate_response = client.post(
        "/api/generate",
        json={
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
        },
    )
    assert generate_response.status_code == 200
    generated = generate_response.json()

    share_response = client.post(
        "/api/shares",
        json={
            "recipient_ids": [bob_id],
            "prompt": "陈旧提示词不应进入分享",
            "mode": "stale-mode",
            "model": "stale-model",
            "rating": "good",
            "generated_image_id": generated["generated_image_id"],
            "saved_image_path": generated["saved_image_path"],
            "saved_image_url": "files/outputs/stale.png",
            "note": "这张适合朋友圈主图",
        },
    )
    assert share_response.status_code == 200
    shares = share_response.json()["shares"]
    assert len(shares) == 1
    assert shares[0]["sender_user_id"] == alice_id
    assert shares[0]["recipient_user_id"] == bob_id
    assert shares[0]["recipient_username"] == "bob"
    assert shares[0]["generated_image_id"] == generated["generated_image_id"]
    assert shares[0]["prompt"] == "生成一张旅行海报"
    assert shares[0]["mode"] == "generate"
    assert shares[0]["model"] == "gpt-image-2"
    assert shares[0]["saved_image_url"] == generated["saved_image_url"]

    alice_inbox = client.get("/api/shares/inbox")
    assert alice_inbox.status_code == 200
    assert alice_inbox.json()["shares"] == []

    client.post("/api/auth/logout")
    bob_login = client.post(
        "/api/auth/login",
        json={"username": "bob", "password": USER_PASSWORD},
    )
    assert bob_login.status_code == 200

    bob_inbox = client.get("/api/shares/inbox")
    assert bob_inbox.status_code == 200
    inbox = bob_inbox.json()["shares"]
    assert len(inbox) == 1
    assert inbox[0]["sender_username"] == "alice"
    assert inbox[0]["prompt"] == "生成一张旅行海报"
    assert inbox[0]["mode"] == "generate"
    assert inbox[0]["model"] == "gpt-image-2"
    assert inbox[0]["saved_image_url"] == generated["saved_image_url"]
    assert inbox[0]["generated_image_id"] == generated["generated_image_id"]


def test_gallery_lists_searches_favorites_and_tags_own_images_only(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password=ADMIN_PASSWORD,
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    alice_client = TestClient(client.app)
    alice = alice_client.post("/api/auth/register", json={"username": "alice", "password": USER_PASSWORD})
    assert alice.status_code == 200
    alice_id = alice.json()["user"]["id"]
    alice_generate = alice_client.post(
        "/api/generate",
        json={"prompt": "高端旅行海报，隐秘海岛度假", "model": "gpt-image-2", "logo_requested": True},
    )
    assert alice_generate.status_code == 200
    alice_image_id = alice_generate.json()["generated_image_id"]

    bob_client = TestClient(client.app)
    bob = bob_client.post("/api/auth/register", json={"username": "bob", "password": USER_PASSWORD})
    assert bob.status_code == 200
    bob_generate = bob_client.post(
        "/api/generate",
        json={"prompt": "城市商务会议海报", "model": "gpt-image-2"},
    )
    assert bob_generate.status_code == 200
    bob_image_id = bob_generate.json()["generated_image_id"]

    initial_gallery = alice_client.get("/api/gallery")
    assert initial_gallery.status_code == 200
    payload = initial_gallery.json()
    assert payload["scope"] == "self"
    assert payload["count"] == 1
    assert payload["items"][0]["id"] == alice_image_id
    assert payload["items"][0]["user_id"] == alice_id
    assert payload["items"][0]["username"] == "alice"
    assert payload["items"][0]["is_favorite"] is False
    assert payload["items"][0]["tags"] == []
    assert payload["items"][0]["saved_image_url"] == alice_generate.json()["saved_image_url"]

    update_gallery_item = alice_client.put(
        f"/api/gallery/{alice_image_id}",
        json={"is_favorite": True, "tags": ["海岛", " 高端旅行 ", "海岛", ""]},
    )
    assert update_gallery_item.status_code == 200
    updated_item = update_gallery_item.json()["item"]
    assert updated_item["is_favorite"] is True
    assert updated_item["tags"] == ["海岛", "高端旅行"]

    search_by_prompt = alice_client.get("/api/gallery?q=海岛")
    assert search_by_prompt.status_code == 200
    assert [item["id"] for item in search_by_prompt.json()["items"]] == [alice_image_id]

    search_by_tag = alice_client.get("/api/gallery?tag=高端旅行")
    assert search_by_tag.status_code == 200
    assert [item["id"] for item in search_by_tag.json()["items"]] == [alice_image_id]

    favorites_only = alice_client.get("/api/gallery?favorite=1")
    assert favorites_only.status_code == 200
    assert [item["id"] for item in favorites_only.json()["items"]] == [alice_image_id]

    bob_cannot_update_alice = bob_client.put(
        f"/api/gallery/{alice_image_id}",
        json={"is_favorite": True, "tags": ["偷看"]},
    )
    assert bob_cannot_update_alice.status_code == 403
    assert bob_cannot_update_alice.json()["code"] == "forbidden"

    bob_gallery = bob_client.get("/api/gallery")
    assert bob_gallery.status_code == 200
    assert [item["id"] for item in bob_gallery.json()["items"]] == [bob_image_id]

    admin_client = TestClient(client.app)
    admin_login = admin_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert admin_login.status_code == 200
    admin_all = admin_client.get("/api/gallery?scope=all")
    assert admin_all.status_code == 200
    assert admin_all.json()["scope"] == "all"
    assert {item["id"] for item in admin_all.json()["items"]} == {alice_image_id, bob_image_id}


def test_user_cannot_share_or_finalize_another_users_generated_image(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    alice = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert alice.status_code == 200
    generate_response = client.post(
        "/api/generate",
        json={
            "prompt": "生成一张旅行海报",
            "model": "gpt-image-2",
        },
    )
    assert generate_response.status_code == 200
    generated = generate_response.json()

    client.post("/api/auth/logout")
    bob = client.post(
        "/api/auth/register",
        json={"username": "bob", "password": USER_PASSWORD},
    )
    assert bob.status_code == 200
    client.post("/api/auth/logout")
    carol = client.post(
        "/api/auth/register",
        json={"username": "carol", "password": USER_PASSWORD},
    )
    assert carol.status_code == 200
    carol_id = carol.json()["user"]["id"]
    client.post("/api/auth/logout")
    bob_login = client.post(
        "/api/auth/login",
        json={"username": "bob", "password": USER_PASSWORD},
    )
    assert bob_login.status_code == 200

    finalize_response = client.post(
        "/api/final-images",
        json={
            "generated_image_id": generated["generated_image_id"],
            "source_saved_image_url": generated["saved_image_url"],
            "image": {
                "name": "stolen-logo.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )
    assert finalize_response.status_code == 403
    assert finalize_response.json()["code"] == "forbidden"

    share_response = client.post(
        "/api/shares",
        json={
            "recipient_ids": [carol_id],
            "generated_image_id": generated["generated_image_id"],
            "saved_image_path": generated["saved_image_path"],
            "saved_image_url": generated["saved_image_url"],
        },
    )
    assert share_response.status_code == 403
    assert share_response.json()["code"] == "forbidden"


def test_admin_delete_user_and_duplicate_user_rejected(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password=ADMIN_PASSWORD)
    client, _, _ = make_client(settings=settings)

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200

    first = client.post(
        "/api/admin/users",
        json={"username": "Alice", "password": USER_PASSWORD},
    )
    assert first.status_code == 200
    user_id = first.json()["user"]["id"]

    duplicate = client.post(
        "/api/admin/users",
        json={"username": "alice", "password": "another password"},
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["code"] == "user_exists"

    delete_self = client.delete("/api/admin/users/1")
    assert delete_self.status_code == 400
    assert delete_self.json()["code"] == "cannot_delete_self"

    deleted = client.delete(f"/api/admin/users/{user_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "ok"

    deleted_login = client.post(
        "/api/auth/login",
        json={"username": "Alice", "password": USER_PASSWORD},
    )
    assert deleted_login.status_code == 400

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert "picgen_session=" in logout.headers["set-cookie"]

    expired_me = client.get("/api/me")
    assert expired_me.status_code == 401


def test_files_endpoint_only_serves_saved_outputs(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, admin_password=ADMIN_PASSWORD)
    client, _, resolved_settings = make_client(settings=settings)
    image_path = resolved_settings.outputs_dir / "20260604" / "safe.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"png-bytes")

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    assert (resolved_settings.data_dir / "auth.sqlite3").is_file()

    exposed_db = client.get("/files/auth.sqlite3")
    assert exposed_db.status_code in {403, 404}

    exposed_wal = client.get("/files/auth.sqlite3-wal")
    assert exposed_wal.status_code in {403, 404}

    traversal = client.get("/files/outputs/../auth.sqlite3")
    assert traversal.status_code in {403, 404}

    saved_output = client.get("/files/outputs/20260604/safe.png")
    assert saved_output.status_code == 200
    assert saved_output.content == b"png-bytes"


def test_team_chat_group_mentions_bot_and_tracks_unread(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password=ADMIN_PASSWORD,
        default_api_key="sk-test",
        default_responses_model="gpt-5.5",
    )
    client, fake, _ = make_client(settings=settings)

    admin_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert admin_login.status_code == 200
    client.post("/api/auth/logout")

    minorli_client = TestClient(client.app)
    minorli = minorli_client.post(
        "/api/auth/register",
        json={"username": "minorli", "password": USER_PASSWORD},
    )
    assert minorli.status_code == 200
    assert minorli.json()["user"]["company"] == ""
    assert minorli.json()["user"]["department"] == ""

    alice_client = TestClient(client.app)
    alice = alice_client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert alice.status_code == 200

    bob_client = TestClient(client.app)
    bob = bob_client.post(
        "/api/auth/register",
        json={"username": "bob", "password": USER_PASSWORD},
    )
    assert bob.status_code == 200

    members = alice_client.get("/api/team-chat/members")
    assert members.status_code == 200
    member_names = [item["username"] for item in members.json()["members"]]
    assert "GPT-BOT" in member_names
    assert "bob" in member_names
    assert "admin" not in member_names
    assert "minorli" not in member_names
    assert members.json()["bot"]["username"] == "GPT-BOT"
    human_member_names = [item["username"] for item in members.json()["human_members"]]
    assert human_member_names == ["bob"]
    group = members.json()["group"]
    assert group["company"] == "6renyou"
    assert group["department"] == "PD & OPS"
    assert group["title"] == "PD & OPS"
    assert group["subtitle"] == "6renyou · 部门群"
    assert group["member_count"] == 1
    assert group["room_key"].startswith("team:")

    fake.run_responses.return_value = {"output_text": "可以，建议把标题压低一点，画面会更高级。"}
    # The bot reply is dispatched as a fire-and-forget asyncio task on the loop that
    # handled alice's POST. Use alice_client as a context manager so its portal/event
    # loop stays alive while we poll for the reply — otherwise the ephemeral per-request
    # portal is torn down and the background task is cancelled before it persists the
    # reply, which makes this test flaky under load. (In production the uvicorn event
    # loop is long-lived, so the reply is always delivered.)
    with alice_client:
        send = alice_client.post(
            "/api/team-chat/messages",
            json={"room_type": "team", "content": "@GPT-BOT 这张旅行海报怎么优化？"},
        )
        assert send.status_code == 200
        created = send.json()["messages"]
        assert [item["sender_type"] for item in created] == ["user"]
        assert send.json()["bot_reply_pending"] is True

        team_messages = []
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            messages = bob_client.get("/api/team-chat/messages?room_type=team")
            assert messages.status_code == 200
            team_messages = messages.json()["messages"]
            if any(item["sender_name"] == "GPT-BOT" for item in team_messages):
                break
            time.sleep(0.05)
    assert [item["sender_name"] for item in team_messages] == ["alice", "GPT-BOT"]
    assert team_messages[1]["content"].startswith("@alice ")
    fake.run_responses.assert_awaited_once()
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["model"] == "gpt-5.5"
    assert "reasoning" not in upstream_payload
    assert "GPT-BOT" in upstream_payload["instructions"]
    assert "中文" in upstream_payload["instructions"]
    prompt_text = upstream_payload["input"][0]["content"][0]["text"]
    assert "高端定制旅行" in prompt_text
    assert "全局图片质量助手" in prompt_text
    assert "尊重用户自由提示词" in prompt_text
    assert "不要把所有用户的提示词改成统一模板" in prompt_text
    assert "不要强制套用历史风格" in prompt_text
    assert "冷门小众但高质量" in prompt_text
    assert "目的地" in prompt_text

    bob_unread = bob_client.get("/api/team-chat/unread")
    assert bob_unread.status_code == 200
    assert bob_unread.json()["unread"]["total"] >= 2
    assert bob_unread.json()["unread"]["rooms"][group["room_key"]] >= 2

    minorli_messages = minorli_client.get("/api/team-chat/messages?room_type=team")
    assert minorli_messages.status_code == 200
    assert minorli_messages.json()["messages"] == []

    read = bob_client.post(
        "/api/team-chat/read",
        json={"room_type": "team", "message_id": team_messages[-1]["id"]},
    )
    assert read.status_code == 200
    bob_unread_after_read = bob_client.get("/api/team-chat/unread")
    assert bob_unread_after_read.status_code == 200
    assert bob_unread_after_read.json()["unread"]["rooms"].get(group["room_key"], 0) == 0


def test_team_chat_messages_initial_load_returns_latest_window(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, _, _ = make_client(settings=settings)

    alice_client = TestClient(client.app)
    assert (
        alice_client.post(
            "/api/auth/register",
            json={"username": "alice", "password": USER_PASSWORD},
        ).status_code
        == 200
    )

    for index in range(205):
        response = alice_client.post(
            "/api/team-chat/messages",
            json={"room_type": "team", "content": f"message-{index:03d}"},
        )
        assert response.status_code == 200

    initial = alice_client.get("/api/team-chat/messages?room_type=team")
    assert initial.status_code == 200
    initial_messages = initial.json()["messages"]
    assert len(initial_messages) == 100
    assert initial_messages[0]["content"] == "message-105"
    assert initial_messages[-1]["content"] == "message-204"

    latest_id = initial_messages[-1]["id"]
    next_response = alice_client.post(
        "/api/team-chat/messages",
        json={"room_type": "team", "content": "message-205"},
    )
    assert next_response.status_code == 200
    incremental = alice_client.get(f"/api/team-chat/messages?room_type=team&after_id={latest_id}")
    assert incremental.status_code == 200
    assert [item["content"] for item in incremental.json()["messages"]] == ["message-205"]


def test_team_chat_group_is_scoped_by_company_and_department(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, _, _ = make_client(settings=settings)

    alice_client = TestClient(client.app)
    alice = alice_client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert alice.status_code == 200

    bob_client = TestClient(client.app)
    bob = bob_client.post(
        "/api/auth/register",
        json={"username": "bob", "password": USER_PASSWORD},
    )
    assert bob.status_code == 200

    invalid_register = client.post(
        "/api/auth/register",
        json={
            "username": "eve",
            "password": USER_PASSWORD,
            "company": "Other Co",
            "department": "PD & OPS",
        },
    )
    assert invalid_register.status_code == 400
    assert invalid_register.json()["code"] == "validation_error"

    invalid_profile = alice_client.put(
        "/api/me/profile",
        json={
            "username": "alice",
            "company": "6renyou",
            "department": "Marketing",
        },
    )
    assert invalid_profile.status_code == 400
    assert invalid_profile.json()["code"] == "validation_error"

    carol_client = TestClient(client.app)
    carol = carol_client.post(
        "/api/auth/register",
        json={"username": "carol", "password": USER_PASSWORD},
    )
    assert carol.status_code == 200

    alice_members = alice_client.get("/api/team-chat/members")
    assert alice_members.status_code == 200
    alice_payload = alice_members.json()
    alice_member_names = [item["username"] for item in alice_payload["members"]]
    assert "bob" in alice_member_names
    assert "carol" in alice_member_names
    assert alice_payload["group"]["room_key"].startswith("team:")

    send = alice_client.post(
        "/api/team-chat/messages",
        json={"room_type": "team", "content": "PD OPS 小组消息"},
    )
    assert send.status_code == 200

    bob_messages = bob_client.get("/api/team-chat/messages?room_type=team")
    assert bob_messages.status_code == 200
    assert [item["content"] for item in bob_messages.json()["messages"]] == ["PD OPS 小组消息"]

    carol_messages = carol_client.get("/api/team-chat/messages?room_type=team")
    assert carol_messages.status_code == 200
    assert [item["content"] for item in carol_messages.json()["messages"]] == ["PD OPS 小组消息"]


def test_admin_org_dictionary_group_assets_stats_and_summary(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password=ADMIN_PASSWORD,
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    alice_client = TestClient(client.app)
    alice = alice_client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert alice.status_code == 200

    bob_client = TestClient(client.app)
    bob = bob_client.post(
        "/api/auth/register",
        json={"username": "bob", "password": USER_PASSWORD},
    )
    assert bob.status_code == 200
    bob_id = bob.json()["user"]["id"]

    admin_client = TestClient(client.app)
    admin_login = admin_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert admin_login.status_code == 200

    public_orgs = client.get("/api/org-units")
    assert public_orgs.status_code == 200
    assert ("6renyou", "PD & OPS") in {
        (item["company"], item["department"]) for item in public_orgs.json()["org_units"]
    }

    orgs = admin_client.get("/api/admin/org-units")
    assert orgs.status_code == 200
    assert ("6renyou", "PD & OPS") in {(item["company"], item["department"]) for item in orgs.json()["org_units"]}

    create_org = admin_client.post(
        "/api/admin/org-units",
        json={"company": "6renyou", "department": "Bespoke Travel"},
    )
    assert create_org.status_code == 200
    assert create_org.json()["org_unit"]["is_active"] is True

    move_bob = admin_client.put(
        f"/api/admin/users/{bob_id}/org",
        json={
            "company": "6renyou",
            "department": "Bespoke Travel",
            "reason": "加入高端定制旅行组",
        },
    )
    assert move_bob.status_code == 200
    assert move_bob.json()["user"]["department"] == "Bespoke Travel"

    admin_users = admin_client.get("/api/admin/users")
    assert admin_users.status_code == 200
    bob_admin_row = next(item for item in admin_users.json()["users"] if item["id"] == bob_id)
    assert bob_admin_row["company"] == "6renyou"
    assert bob_admin_row["department"] == "Bespoke Travel"

    audit = admin_client.get("/api/admin/org-audit")
    assert audit.status_code == 200
    audit_events = audit.json()["events"]
    assert audit_events[0]["target_user_id"] == bob_id
    assert audit_events[0]["old_department"] == "PD & OPS"
    assert audit_events[0]["new_department"] == "Bespoke Travel"
    assert audit_events[0]["reason"] == "加入高端定制旅行组"

    bob_members = bob_client.get("/api/team-chat/members")
    assert bob_members.status_code == 200
    assert bob_members.json()["group"]["department"] == "Bespoke Travel"
    assert "alice" not in [item["username"] for item in bob_members.json()["members"]]

    set_announcement = admin_client.put(
        "/api/team-chat/group-announcement",
        json={
            "company": "6renyou",
            "department": "Bespoke Travel",
            "content": "本周优先沉淀高端定制旅行素材。",
        },
    )
    assert set_announcement.status_code == 200

    bob_announcement = bob_client.get("/api/team-chat/group-announcement")
    assert bob_announcement.status_code == 200
    assert bob_announcement.json()["announcement"]["content"] == "本周优先沉淀高端定制旅行素材。"

    alice_announcement = alice_client.get("/api/team-chat/group-announcement")
    assert alice_announcement.status_code == 200
    assert alice_announcement.json()["announcement"] is None

    generate = alice_client.post(
        "/api/generate",
        json={"prompt": "高端旅行海报，隐秘海岛度假", "model": "gpt-image-2"},
    )
    assert generate.status_code == 200
    generated = generate.json()

    feedback = alice_client.post(
        "/api/feedback",
        json={
            "rating": "good",
            "reason": "适合沉淀为参考",
            "generated_image_id": generated["generated_image_id"],
        },
    )
    assert feedback.status_code == 200

    assets = alice_client.get("/api/team-chat/group-assets")
    assert assets.status_code == 200
    group_assets = assets.json()["assets"]
    assert len(group_assets) == 1
    assert group_assets[0]["generated_image_id"] == generated["generated_image_id"]
    assert group_assets[0]["prompt"] == "高端旅行海报，隐秘海岛度假"

    manual_asset = alice_client.post(
        "/api/team-chat/group-assets",
        json={
            "generated_image_id": generated["generated_image_id"],
            "title": "隐秘海岛主视觉",
            "note": "适合作为高端海岛产品参考",
        },
    )
    assert manual_asset.status_code == 200
    assert manual_asset.json()["asset"]["title"] == "隐秘海岛主视觉"

    duplicate_manual_asset = alice_client.post(
        "/api/team-chat/group-assets",
        json={
            "generated_image_id": generated["generated_image_id"],
            "title": "隐秘海岛主视觉二次保存",
        },
    )
    assert duplicate_manual_asset.status_code == 200

    assets_after_manual_save = alice_client.get("/api/team-chat/group-assets")
    assert assets_after_manual_save.status_code == 200
    assert len(assets_after_manual_save.json()["assets"]) == 1
    assert assets_after_manual_save.json()["assets"][0]["title"] == "隐秘海岛主视觉二次保存"

    stats = alice_client.get("/api/team-chat/group-stats")
    assert stats.status_code == 200
    stats_payload = stats.json()["stats"]
    assert stats_payload["group"]["department"] == "PD & OPS"
    assert stats_payload["users"]["member_count"] >= 1
    assert stats_payload["usage"]["generated_image_count"] >= 1
    assert stats_payload["feedback"]["totals"]["good"] == 1
    assert stats_payload["assets"]["asset_count"] == 1

    admin_org_stats = admin_client.get("/api/admin/org-stats")
    assert admin_org_stats.status_code == 200
    org_stats = admin_org_stats.json()["org_stats"]
    pd_ops_stats = next(item for item in org_stats if item["group"]["department"] == "PD & OPS")
    bespoke_stats = next(item for item in org_stats if item["group"]["department"] == "Bespoke Travel")
    assert pd_ops_stats["usage"]["generated_image_count"] >= 1
    assert pd_ops_stats["assets"]["asset_count"] == 1
    assert bespoke_stats["users"]["member_count"] == 1

    summary = alice_client.get("/api/team-chat/group-summary?days=7")
    assert summary.status_code == 200
    summary_text = summary.json()["summary"]["text"]
    assert "6renyou · PD & OPS" in summary_text
    assert "高端旅行海报" in summary_text
    assert "满意 1" in summary_text


def test_team_chat_private_rooms_are_limited_to_participants(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, _, _ = make_client(settings=settings)

    alice_client = TestClient(client.app)
    alice = alice_client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert alice.status_code == 200
    bob_client = TestClient(client.app)
    bob = bob_client.post(
        "/api/auth/register",
        json={"username": "bob", "password": USER_PASSWORD},
    )
    assert bob.status_code == 200
    bob_id = bob.json()["user"]["id"]
    carol_client = TestClient(client.app)
    carol = carol_client.post(
        "/api/auth/register",
        json={"username": "carol", "password": USER_PASSWORD},
    )
    assert carol.status_code == 200

    send = alice_client.post(
        "/api/team-chat/messages",
        json={"room_type": "dm", "recipient_user_id": bob_id, "content": "这个版式我觉得可以。"},
    )
    assert send.status_code == 200
    assert send.json()["messages"][0]["room_type"] == "dm"

    alice_id = alice.json()["user"]["id"]
    bob_messages = bob_client.get(f"/api/team-chat/messages?room_type=dm&recipient_user_id={alice_id}")
    assert bob_messages.status_code == 200
    assert bob_messages.json()["messages"][0]["content"] == "这个版式我觉得可以。"

    carol_room = carol_client.get(f"/api/team-chat/messages?room_type=dm&recipient_user_id={bob_id}")
    assert carol_room.status_code == 200
    assert carol_room.json()["messages"] == []

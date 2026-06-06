from __future__ import annotations

import json
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
    assert [(item["username_normalized"], item["status"]) for item in requests] == [
        ("missing-user", "pending"),
        ("alice", "pending"),
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
        "message": "如果账号存在，管理员会看到找回申请。请联系管理员获取新密码。",
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


def test_admin_creates_user_and_usage_scope_is_role_limited(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        admin_password=ADMIN_PASSWORD,
        default_api_key="sk-test",
    )
    client, fake, _ = make_client(settings=settings)
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
    metadata = json.loads(Path(payload["saved_metadata_path"]).read_text(encoding="utf-8"))
    assert metadata["user_id"] == created["id"]
    assert metadata["username"] == "alice"
    assert payload["generation_job_id"] > 0
    assert payload["generated_image_id"] > 0
    assert payload["saved_image_name"].startswith("alice-generate-")

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
    import sqlite3

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
            """
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
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "schema_migrations" in tables
        assert "user_preferences" in tables
        assert "generation_jobs" in tables
        assert "generated_images" in tables
        assert "image_delivery_events" in tables
        user = conn.execute("SELECT role, is_active, last_seen_at FROM users WHERE id = ?", (user_id,)).fetchone()
        assert user["role"] == "user"
        assert bool(user["is_active"])
        assert user["last_seen_at"]
        job = conn.execute("SELECT * FROM generation_jobs").fetchone()
        assert job["user_id"] == user_id
        assert job["status"] == "succeeded"
        assert job["mode"] == "generate"
        assert job["logo_requested"] == 1
        image = conn.execute("SELECT * FROM generated_images").fetchone()
        assert image["job_id"] == job["id"]
        assert image["user_id"] == user_id
        assert image["saved_image_name"].startswith("wilsonwei-generate-")
        assert image["served_count"] == 1
        delivery = conn.execute("SELECT * FROM image_delivery_events").fetchone()
        assert delivery["generated_image_id"] == image["id"]


def test_final_logo_image_upload_replaces_canonical_generated_image(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True,
        default_api_key="sk-test",
    )
    client, fake, resolved_settings = make_client(settings=settings)
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
            "logo_requested": True,
        },
    )
    assert generate_response.status_code == 200
    generated = generate_response.json()
    original_url = generated["saved_image_url"]
    generated_image_id = generated["generated_image_id"]

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
    assert final_response.status_code == 200
    final_payload = final_response.json()["image"]
    assert final_payload["generated_image_id"] == generated_image_id
    assert final_payload["saved_image_url"] != original_url
    assert final_payload["saved_image_name"].startswith("alice-generate-")
    assert final_payload["saved_image_name"].endswith("-logo.png")
    assert final_payload["logo_overlay_applied"] is True
    assert Path(final_payload["saved_image_path"]).is_file()

    fetched = client.get(f"/{final_payload['saved_image_url']}")
    assert fetched.status_code == 200
    assert fetched.content == Path(final_payload["saved_image_path"]).read_bytes()

    import sqlite3

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.row_factory = sqlite3.Row
        image = conn.execute(
            "SELECT * FROM generated_images WHERE id = ?",
            (generated_image_id,),
        ).fetchone()
        assert image["saved_image_url"] == final_payload["saved_image_url"]
        assert image["saved_image_path"] == final_payload["saved_image_path"]
        assert image["saved_metadata_url"] == final_payload["saved_metadata_url"]
        assert image["logo_overlay_applied"] == 1


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

    update_response = client.put(
        "/api/preferences",
        json={
            "default_model": "gpt-image-2",
            "default_responses_model": "gpt-5.5",
            "default_size": "1088x2240",
            "default_quality": "high",
            "default_output_format": "webp",
            "default_image_transport": "responses",
            "logo_overlay_enabled": False,
            "auto_copyright_check_enabled": False,
            "api_key": "sk-should-be-ignored",
        },
    )
    assert update_response.status_code == 200
    preferences = update_response.json()["preferences"]
    assert preferences["default_model"] == "gpt-image-2"
    assert preferences["default_responses_model"] == "gpt-5.5"
    assert preferences["default_size"] == "1088x2240"
    assert preferences["default_quality"] == "high"
    assert preferences["default_output_format"] == "webp"
    assert preferences["default_image_transport"] == "responses"
    assert preferences["logo_overlay_enabled"] is False
    assert preferences["auto_copyright_check_enabled"] is False
    assert "api_key" not in preferences

    fetched_response = client.get("/api/preferences")
    assert fetched_response.status_code == 200
    assert fetched_response.json()["preferences"] == preferences


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
    assert all(set(user) == {"id", "username"} for user in share_users)

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

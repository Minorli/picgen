from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient
from test_api import TINY_PNG_B64

ADMIN_PASSWORD = "correct horse battery admin"
USER_PASSWORD = "correct horse battery"


def _register(client: TestClient, username: str) -> dict[str, object]:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": USER_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["user"]


def _generate(client: TestClient, fake) -> dict[str, object]:
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}
    response = client.post(
        "/api/generate",
        json={"prompt": "发布授权回归图", "model": "gpt-image-2", "size": "auto"},
    )
    assert response.status_code == 200
    return response.json()


def test_self_registration_is_closed_by_default_and_reported(make_client, settings_factory) -> None:
    settings = settings_factory(auth_enabled=True, self_registration_enabled=False)
    client, _, _ = make_client(settings=settings)

    config = client.get("/api/config")
    assert config.status_code == 200
    assert config.json()["self_registration_enabled"] is False

    response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": USER_PASSWORD},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "registration_disabled"


def test_self_registered_user_is_unassigned_and_cannot_change_org(make_client, settings_factory) -> None:
    settings = settings_factory(auth_enabled=True, self_registration_enabled=True)
    client, _, _ = make_client(settings=settings)

    response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "password": USER_PASSWORD,
            "company": "6renyou",
            "department": "PD & OPS",
        },
    )
    assert response.status_code == 200
    user = response.json()["user"]
    assert user["company"] == ""
    assert user["department"] == ""

    anonymous_client = TestClient(client.app)
    assert anonymous_client.get("/api/org-units").status_code == 401

    group = client.get("/api/team-chat/members")
    assert group.status_code == 200
    assert group.json()["group"]["room_key"] == f"team:unassigned:{user['id']}"
    assert group.json()["human_members"] == []

    profile = client.put(
        "/api/me/profile",
        json={
            "username": "alice",
            "company": "6renyou",
            "department": "PD & OPS",
        },
    )
    assert profile.status_code == 200
    assert profile.json()["user"]["company"] == ""
    assert profile.json()["user"]["department"] == ""


def test_unassigned_registration_stays_isolated_after_store_restart(make_client, settings_factory) -> None:
    from picgen.auth import AuthStore

    settings = settings_factory(auth_enabled=True, self_registration_enabled=True)
    client, _, resolved_settings = make_client(settings=settings)
    user = _register(client, "alice")

    restarted = AuthStore(resolved_settings.resolved_auth_db_path)
    restarted.initialize()
    persisted = next(item for item in restarted.list_active_users() if item["id"] == user["id"])
    assert persisted["company"] == ""
    assert persisted["department"] == ""
    assert restarted.team_chat_group_for_user(int(user["id"]))["room_key"] == f"team:unassigned:{user['id']}"


def test_output_files_require_owner_share_or_admin_access(make_client, settings_factory) -> None:
    settings = settings_factory(
        auth_enabled=True,
        self_registration_enabled=True,
        admin_password=ADMIN_PASSWORD,
        default_api_key="sk-test",
    )
    root_client, fake, resolved_settings = make_client(settings=settings)

    alice_client = TestClient(root_client.app)
    alice = _register(alice_client, "alice")
    generated = _generate(alice_client, fake)
    image_url = f"/{generated['saved_image_url']}"
    assert alice_client.get(image_url).status_code == 200

    bob_client = TestClient(root_client.app)
    bob = _register(bob_client, "bob")
    assert bob_client.get(image_url).status_code == 404

    shared = alice_client.post(
        "/api/shares",
        json={
            "recipient_ids": [bob["id"]],
            "generated_image_id": generated["generated_image_id"],
            "saved_image_path": generated["saved_image_path"],
            "saved_image_url": generated["saved_image_url"],
        },
    )
    assert shared.status_code == 200
    assert bob_client.get(image_url).status_code == 200

    unowned = resolved_settings.outputs_dir / "20260711" / "unowned.png"
    unowned.parent.mkdir(parents=True, exist_ok=True)
    unowned.write_bytes(b"unowned")
    assert bob_client.get("/files/outputs/20260711/unowned.png").status_code == 404

    admin_client = TestClient(root_client.app)
    login = admin_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    assert admin_client.get(image_url).status_code == 200
    assert admin_client.get("/files/outputs/20260711/unowned.png").status_code == 200

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        delivered_users = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT user_id FROM image_delivery_events WHERE relative_path = ?",
                (str(generated["saved_image_url"]).removeprefix("files/"),),
            )
        }
    assert {alice["id"], bob["id"]}.issubset(delivered_users)


def test_group_output_access_uses_current_group_membership(make_client, settings_factory) -> None:
    settings = settings_factory(
        auth_enabled=True,
        self_registration_enabled=True,
        admin_password=ADMIN_PASSWORD,
        default_api_key="sk-test",
    )
    root_client, fake, _ = make_client(settings=settings)
    alice_client = TestClient(root_client.app)
    alice = _register(alice_client, "alice")
    bob_client = TestClient(root_client.app)
    bob = _register(bob_client, "bob")
    outsider_client = TestClient(root_client.app)
    _register(outsider_client, "outsider")

    admin_client = TestClient(root_client.app)
    assert admin_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    ).status_code == 200
    for user in (alice, bob):
        assigned = admin_client.put(
            f"/api/admin/users/{user['id']}/org",
            json={"company": "6renyou", "department": "PD & OPS", "reason": "test"},
        )
        assert assigned.status_code == 200

    generated = _generate(alice_client, fake)
    saved = alice_client.post(
        "/api/team-chat/group-assets",
        json={"generated_image_id": generated["generated_image_id"], "title": "共享作品"},
    )
    assert saved.status_code == 200
    image_url = f"/{generated['saved_image_url']}"
    assert bob_client.get(image_url).status_code == 200
    assert outsider_client.get(image_url).status_code == 404


def test_legacy_share_url_must_resolve_to_the_senders_own_image(make_client, settings_factory) -> None:
    settings = settings_factory(
        auth_enabled=True,
        self_registration_enabled=True,
        default_api_key="sk-test",
    )
    root_client, fake, _ = make_client(settings=settings)
    owner_client = TestClient(root_client.app)
    owner = _register(owner_client, "owner")
    generated = _generate(owner_client, fake)

    attacker_client = TestClient(root_client.app)
    _register(attacker_client, "attacker")
    recipient_client = TestClient(root_client.app)
    recipient = _register(recipient_client, "recipient")

    forged = attacker_client.post(
        "/api/shares",
        json={
            "recipient_ids": [recipient["id"]],
            "saved_image_path": generated["saved_image_path"],
            "saved_image_url": generated["saved_image_url"],
        },
    )
    assert forged.status_code == 403
    assert forged.json()["code"] == "forbidden"
    assert recipient_client.get(f"/{generated['saved_image_url']}").status_code == 404

    legacy_own_share = owner_client.post(
        "/api/shares",
        json={
            "recipient_ids": [recipient["id"]],
            "saved_image_path": generated["saved_image_path"],
            "saved_image_url": f"/{generated['saved_image_url']}",
        },
    )
    assert legacy_own_share.status_code == 200
    shared = legacy_own_share.json()["shares"][0]
    assert shared["sender_user_id"] == owner["id"]
    assert shared["generated_image_id"] == generated["generated_image_id"]
    assert recipient_client.get(f"/{generated['saved_image_url']}").status_code == 200


def test_legacy_share_migration_keeps_only_sender_owned_images(make_client, settings_factory) -> None:
    from picgen.auth import AuthStore

    settings = settings_factory(
        auth_enabled=True,
        self_registration_enabled=True,
        default_api_key="sk-test",
    )
    root_client, fake, resolved_settings = make_client(settings=settings)

    owner_client = TestClient(root_client.app)
    _register(owner_client, "owner")
    owner_image = _generate(owner_client, fake)

    sender_client = TestClient(root_client.app)
    sender = _register(sender_client, "sender")
    sender_image = _generate(sender_client, fake)

    recipient_client = TestClient(root_client.app)
    recipient = _register(recipient_client, "recipient")

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version = 15")
        legacy_rows = (
            (sender_image["saved_image_path"], f"/{sender_image['saved_image_url']}"),
            (owner_image["saved_image_path"], owner_image["saved_image_url"]),
        )
        for saved_image_path, saved_image_url in legacy_rows:
            conn.execute(
                """
                INSERT INTO shared_results (
                    sender_user_id,
                    recipient_user_id,
                    generated_image_id,
                    saved_image_path,
                    saved_image_url,
                    created_at
                )
                VALUES (?, ?, NULL, ?, ?, ?)
                """,
                (
                    sender["id"],
                    recipient["id"],
                    saved_image_path,
                    saved_image_url,
                    "2026-07-11T00:00:00+00:00",
                ),
            )

    migrated = AuthStore(resolved_settings.resolved_auth_db_path)
    migrated.initialize()

    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        rows = conn.execute(
            """
            SELECT generated_image_id, saved_image_path, saved_image_url
            FROM shared_results
            WHERE sender_user_id = ? AND recipient_user_id = ?
            ORDER BY id
            """,
            (sender["id"], recipient["id"]),
        ).fetchall()
        migration = conn.execute(
            "SELECT name FROM schema_migrations WHERE version = 15"
        ).fetchone()

    assert rows == [
        (
            sender_image["generated_image_id"],
            sender_image["saved_image_path"],
            sender_image["saved_image_url"],
        )
    ]
    assert migration == ("shared_result_image_ownership",)
    assert recipient_client.get(f"/{sender_image['saved_image_url']}").status_code == 200
    assert recipient_client.get(f"/{owner_image['saved_image_url']}").status_code == 404


def test_group_asset_path_without_image_id_does_not_authorize_output(make_client, settings_factory) -> None:
    settings = settings_factory(
        auth_enabled=True,
        self_registration_enabled=True,
        default_api_key="sk-test",
    )
    root_client, fake, resolved_settings = make_client(settings=settings)

    owner_client = TestClient(root_client.app)
    _register(owner_client, "owner")
    owner_image = _generate(owner_client, fake)

    recipient_client = TestClient(root_client.app)
    recipient = _register(recipient_client, "recipient")
    with sqlite3.connect(resolved_settings.resolved_auth_db_path) as conn:
        conn.execute(
            """
            INSERT INTO group_saved_items (
                room_key,
                user_id,
                generated_image_id,
                saved_image_path,
                saved_image_url,
                created_at
            )
            VALUES (?, ?, NULL, ?, ?, ?)
            """,
            (
                f"team:unassigned:{recipient['id']}",
                recipient["id"],
                owner_image["saved_image_path"],
                owner_image["saved_image_url"],
                "2026-07-11T00:00:00+00:00",
            ),
        )

    assert recipient_client.get(f"/{owner_image['saved_image_url']}").status_code == 404


def test_preferences_put_replaces_fields_but_mode_patch_is_isolated(make_client, settings_factory) -> None:
    settings = settings_factory(auth_enabled=True, self_registration_enabled=True)
    client, _, _ = make_client(settings=settings)
    _register(client, "alice")

    first = client.put(
        "/api/preferences",
        json={
            "default_model": "custom-image",
            "default_responses_model": "custom-responses",
            "default_size": "1024x1024",
            "default_quality": "high",
            "default_output_format": "webp",
            "default_image_transport": "responses",
            "logo_overlay_enabled": False,
            "auto_copyright_check_enabled": False,
            "ui_mode": "professional",
        },
    )
    assert first.status_code == 200

    replacement = client.put("/api/preferences", json={"default_size": "1088x2240"})
    assert replacement.status_code == 200
    preferences = replacement.json()["preferences"]
    assert preferences["default_model"] == ""
    assert preferences["default_responses_model"] == settings.default_responses_model
    assert preferences["default_size"] == "1088x2240"
    assert preferences["default_quality"] == ""
    assert preferences["default_output_format"] == ""
    assert preferences["default_image_transport"] == ""
    assert preferences["logo_overlay_enabled"] is True
    assert preferences["auto_copyright_check_enabled"] is True
    assert preferences["ui_mode"] == "professional"

    patched = client.patch("/api/preferences/ui-mode", json={"ui_mode": "simple"})
    assert patched.status_code == 200
    patched_preferences = patched.json()["preferences"]
    assert patched_preferences["ui_mode"] == "simple"
    for key, value in preferences.items():
        if key not in {"ui_mode", "updated_at"}:
            assert patched_preferences[key] == value


def test_simple_checklist_completion_is_persisted_without_replacing_preferences(
    make_client,
    settings_factory,
) -> None:
    settings = settings_factory(auth_enabled=True, self_registration_enabled=True)
    client, _, _ = make_client(settings=settings)
    _register(client, "alice")
    assert client.put(
        "/api/preferences",
        json={"default_size": "1088x2240", "ui_mode": "simple"},
    ).status_code == 200

    completed = client.patch(
        "/api/preferences/simple-checklist",
        json={"completed": True},
    )
    assert completed.status_code == 200
    assert completed.json()["preferences"]["simple_checklist_completed"] is True
    assert completed.json()["preferences"]["default_size"] == "1088x2240"
    assert completed.json()["preferences"]["ui_mode"] == "simple"

    replacement = client.put("/api/preferences", json={"default_size": "1792x1792"})
    assert replacement.status_code == 200
    assert replacement.json()["preferences"]["simple_checklist_completed"] is True
    assert client.get("/api/preferences").json()["preferences"]["simple_checklist_completed"] is True


def test_password_reset_smtp_failure_never_forwards_reset_token(
    make_client,
    settings_factory,
    monkeypatch,
) -> None:
    from picgen.notifications import NotificationResult

    notifications: list[dict[str, object]] = []

    def _failed_email(**_kwargs):
        return NotificationResult(configured=True, sent=False, status="failed", error="smtp down")

    async def _capture_notification(**kwargs):
        notifications.append(kwargs["request_info"])
        return NotificationResult(configured=True, sent=True, status="sent")

    monkeypatch.setattr("picgen.routes.send_password_reset_email", _failed_email)
    monkeypatch.setattr(
        "picgen.routes.send_password_reset_request_notification",
        _capture_notification,
    )
    settings = settings_factory(
        auth_enabled=True,
        self_registration_enabled=True,
        public_base_url="https://picgen.example.com",
        smtp_host="smtp.example.com",
        smtp_username="mailer",
        smtp_password="secret",
        smtp_from_email="picgen@example.com",
        bug_report_webhook_url="https://example.invalid/webhook",
    )
    client, _, _ = make_client(settings=settings)
    _register(client, "alice")
    profile = client.put(
        "/api/me/profile",
        json={"username": "alice", "email": "alice@example.com"},
    )
    assert profile.status_code == 200

    response = client.post("/api/password-reset-requests", json={"username": "alice"})
    assert response.status_code == 200
    assert len(notifications) == 1
    assert notifications[0]["reset_token"] == ""

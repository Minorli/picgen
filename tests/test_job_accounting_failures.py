from __future__ import annotations

import sqlite3

from test_api import TINY_PNG_B64

from picgen.auth import AuthStore


def test_usage_record_failure_preserves_completed_image_job(make_client, settings_factory, monkeypatch):
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/register", json={"username": "accounting", "password": "correct horse battery"}
    ).status_code == 200
    fake.run_json.return_value = {"data": [{"b64_json": TINY_PNG_B64}]}

    def fail_usage(self, **kwargs):
        raise sqlite3.OperationalError("usage table is locked")

    monkeypatch.setattr(AuthStore, "record_usage", fail_usage)
    response = client.post("/api/image-jobs", json={"prompt": "a green circle", "size": "auto"})
    assert response.status_code == 200
    assert response.json()["generated_image_id"] > 0
    fake.run_json.assert_awaited_once()
    with sqlite3.connect(settings.resolved_auth_db_path) as conn:
        assert conn.execute("SELECT status,image_count FROM generation_jobs").fetchone() == ("succeeded", 1)
        assert conn.execute("SELECT count(*) FROM generated_images").fetchone()[0] == 1


def test_unexpected_generation_error_does_not_leak_details_into_history(make_client, settings_factory):
    settings = settings_factory(auth_enabled=True, default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/register", json={"username": "history", "password": "correct horse battery"}
    ).status_code == 200
    fake.run_json.side_effect = RuntimeError("private credential sk-sensitive123456 /private/server/path")
    response = client.post("/api/image-jobs", json={"prompt": "a green circle", "size": "auto"})
    assert response.status_code == 500
    with sqlite3.connect(settings.resolved_auth_db_path) as conn:
        status, message = conn.execute("SELECT status,error_message FROM generation_jobs").fetchone()
    assert status == "failed"
    assert "sk-sensitive" not in message
    assert "/private/server/path" not in message
    assert "request_id" in message

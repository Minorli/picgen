"""Regression tests for the 2026-07 full-project bug sweep."""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from test_api import TINY_PNG_B64

from picgen.auth import AccountLockedError, AuthStore, InvalidCredentialsError
from picgen.config import Settings
from picgen.errors import APIError
from picgen.storage import prune_old_outputs, save_derived_output_image
from picgen.upstream import HttpxAsyncClient, parse_sse_json_events
from picgen.upstream.payload import prepare_image_payload

# --- storage ------------------------------------------------------------


def test_prune_keeps_yesterday_with_one_day_retention(tmp_path: Path) -> None:
    # A folder's newest file can be seconds old at midnight; retention_days=1
    # must never delete yesterday's folder while today is still in progress.
    outputs = tmp_path / "outputs"
    yesterday = outputs / (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    yesterday.mkdir(parents=True)
    (yesterday / "late-night.png").write_bytes(b"x")

    removed = prune_old_outputs(outputs, retention_days=1)

    assert removed == 0
    assert yesterday.exists()


def test_empty_filename_prefix_stays_empty() -> None:
    from picgen.storage import sanitize_filename_prefix

    # Anonymous saves pass an empty prefix; it must not inherit
    # sanitize_filename's "image.png" fallback and become a folder name.
    assert sanitize_filename_prefix("") == ""
    assert sanitize_filename_prefix("   ") == ""
    assert sanitize_filename_prefix("wilson wei") == "wilson-wei"


def test_derived_image_never_adopts_directory_outside_outputs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    outputs = data_dir / "outputs"
    outputs.mkdir(parents=True)
    outside = tmp_path / "static"
    outside.mkdir()
    planted = outside / "index.html"
    planted.write_text("<html></html>")

    result = save_derived_output_image(
        data_dir=data_dir,
        outputs_dir=outputs,
        source_image_path=str(planted),
        mode="result",
        image_bytes=b"\x89PNG\r\n\x1a\n" + b"0" * 32,
        image_mime="image/png",
        metadata={},
        suffix="logo",
    )

    saved = Path(result["saved_image_path"])
    assert outputs in saved.parents
    assert not list(outside.glob("*.png"))


def test_derived_image_uses_current_day_and_sanitizes_historical_source_name(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    outputs = data_dir / "outputs"
    old_day = outputs / "20260101" / "alice"
    old_day.mkdir(parents=True)
    source = old_day / "old#100%poster.png"
    source.write_bytes(b"source")

    result = save_derived_output_image(
        data_dir=data_dir,
        outputs_dir=outputs,
        source_image_path=str(source),
        mode="generate",
        image_bytes=b"\x89PNG\r\n\x1a\n" + b"0" * 32,
        image_mime="image/png",
        metadata={},
        suffix="logo",
    )

    saved = Path(result["saved_image_path"])
    assert saved.parent.parent.name == datetime.now().strftime("%Y%m%d")
    assert saved.parent.name == "alice"
    assert "#" not in saved.name
    assert "%" not in saved.name
    assert source.exists()


def test_derived_image_names_remain_unique_after_long_prefix_truncation(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    outputs = data_dir / "outputs"
    source_dir = outputs / "20260711" / "same-prefix"
    source_dir.mkdir(parents=True)
    common = "a" * 80
    first_source = source_dir / f"{common}-first-11111111.png"
    second_source = source_dir / f"{common}-second-22222222.png"
    first_source.write_bytes(b"source-1")
    second_source.write_bytes(b"source-2")
    image_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 32

    first = save_derived_output_image(
        data_dir=data_dir,
        outputs_dir=outputs,
        source_image_path=str(first_source),
        mode="generate",
        image_bytes=image_bytes,
        image_mime="image/png",
        metadata={},
        suffix="logo",
    )
    second = save_derived_output_image(
        data_dir=data_dir,
        outputs_dir=outputs,
        source_image_path=str(second_source),
        mode="generate",
        image_bytes=image_bytes,
        image_mime="image/png",
        metadata={},
        suffix="logo",
    )

    assert first["saved_image_path"] != second["saved_image_path"]


# --- config env parsing ---------------------------------------------------


def test_cors_env_accepts_empty_and_comma_and_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PICGEN_CORS_ALLOW_ORIGINS", "")
    assert Settings(_env_file=None).cors_allow_origins == []

    monkeypatch.setenv("PICGEN_CORS_ALLOW_ORIGINS", "http://a.com, http://b.com")
    assert Settings(_env_file=None).cors_allow_origins == ["http://a.com", "http://b.com"]

    monkeypatch.setenv("PICGEN_CORS_ALLOW_ORIGINS", '["http://c.com"]')
    assert Settings(_env_file=None).cors_allow_origins == ["http://c.com"]


def test_empty_auth_db_path_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PICGEN_AUTH_DB_PATH", "")
    settings = Settings(_env_file=None)
    assert settings.auth_db_path is None
    assert settings.resolved_auth_db_path.name == "auth.sqlite3"


def test_empty_user_agent_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PICGEN_UPSTREAM_USER_AGENT", "")
    assert Settings(_env_file=None).upstream_user_agent.startswith("Mozilla/5.0")


# --- middleware -----------------------------------------------------------


def test_bearer_header_without_token_is_401_not_500(make_client, settings_factory) -> None:
    settings = settings_factory(proxy_auth_token="secret-token")
    client, _, _ = make_client(settings=settings)

    response = client.get("/api/config", headers={"Authorization": "Bearer "})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


# --- upstream client -------------------------------------------------------


@pytest.mark.asyncio
async def test_oversized_image_download_is_not_retried() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, headers={"Content-Length": str(64 * 1024 * 1024)}, content=b"")

    client = HttpxAsyncClient(max_retries=2, retry_backoff=0.0, max_image_bytes=1024)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(APIError) as info:
            await client.fetch_image("https://upstream.test/big.png", "UA")
        assert info.value.code == "upstream_image_too_large"
        assert calls["count"] == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_remote_protocol_error_translates_to_clean_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    client = HttpxAsyncClient(max_retries=0, retry_backoff=0.0)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(APIError) as info:
            await client.run_json("https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA")
        assert info.value.status == 502
        assert info.value.code == "upstream_network_error"
    finally:
        await client.aclose()


# --- SSE parsing ------------------------------------------------------------


def test_sse_event_with_unicode_line_separator_survives() -> None:
    body = 'data: {"type": "response.completed", "text": "a b"}\n\n'
    events = parse_sse_json_events(body)
    assert len(events) == 1
    assert events[0]["text"] == "a b"


# --- candidate payloads -----------------------------------------------------


def test_placeholder_candidates_are_dropped_and_index_preserved(tmp_path: Path) -> None:
    upstream = {
        "created": 1,
        "data": [
            {"revised_prompt": "moderated away"},  # no image at all
            {"b64_json": TINY_PNG_B64},
            {"b64_json": TINY_PNG_B64, "revised_prompt": "extra valid candidate"},
        ],
    }
    payload = prepare_image_payload(
        upstream,
        data_dir=tmp_path,
        outputs_dir=tmp_path / "outputs",
        user_agent="UA",
        save_context={"mode": "generate", "sample_count": 1},
        fetch_remote=None,
    )
    assert payload["candidate_count"] == 1
    assert payload["images"][0]["candidate_index"] == 1
    assert len([path for path in (tmp_path / "outputs").rglob("*") if path.is_file()]) == 1


def test_all_placeholder_candidates_yield_zero_count(tmp_path: Path) -> None:
    upstream = {"created": 1, "data": [{"revised_prompt": "nothing"}]}
    payload = prepare_image_payload(
        upstream,
        data_dir=tmp_path,
        outputs_dir=tmp_path / "outputs",
        user_agent="UA",
        save_context={"mode": "generate"},
        fetch_remote=None,
    )
    assert payload["candidate_count"] == 0


# --- size mismatch retry ------------------------------------------------------


def test_size_mismatch_retry_defaults_to_disabled() -> None:
    # The upstream currently downscales deterministically — a retry doubles
    # the bill for the same result, so it must be opt-in.
    assert Settings(_env_file=None).size_mismatch_max_retries == 0


def test_anonymous_execution_overrides_are_disabled_by_default() -> None:
    assert Settings(_env_file=None).allow_anonymous_execution_overrides is False


def test_default_responses_reasoning_effort_is_xhigh_and_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings(_env_file=None).default_responses_reasoning_effort == "xhigh"

    monkeypatch.setenv("PICGEN_DEFAULT_RESPONSES_REASONING_EFFORT", "high")
    assert Settings(_env_file=None).default_responses_reasoning_effort == "high"

    with pytest.raises(ValueError, match="default_responses_reasoning_effort"):
        Settings(_env_file=None, default_responses_reasoning_effort="unsupported")


def _generate_poster(client, size="1088x2240"):
    return client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成一张 6 人游竖版旅行海报",
            "model": "gpt-image-2",
            "size": size,
        },
    )


def test_size_mismatch_retries_and_keeps_exact_result(make_client, settings_factory, tmp_path: Path) -> None:
    from test_api import png_b64_with_dimensions

    settings = settings_factory(default_api_key="sk-test", size_mismatch_max_retries=1)
    client, fake, resolved = make_client(settings=settings)
    fake.run_json.side_effect = [
        {"data": [{"b64_json": png_b64_with_dimensions(1024, 1536)}], "created": 1},
        {"data": [{"b64_json": png_b64_with_dimensions(1088, 2240)}], "created": 1},
    ]

    response = _generate_poster(client)

    assert response.status_code == 200
    payload = response.json()
    assert fake.run_json.await_count == 2
    assert payload["saved_image_width"] == 1088
    assert payload["saved_image_height"] == 2240
    assert not payload.get("size_mismatch")
    assert payload["size_mismatch_retries"] == 1
    # The losing first attempt's file must be cleaned up.
    outputs = list((resolved.data_dir / "outputs").rglob("*.png"))
    assert len(outputs) == 1


def test_size_mismatch_retries_same_aspect_upscale_before_normalizing(
    make_client,
    settings_factory,
) -> None:
    from test_api import valid_png_b64

    settings = settings_factory(default_api_key="sk-test", size_mismatch_max_retries=1)
    client, fake, _ = make_client(settings=settings)
    fake.run_json.side_effect = [
        {"data": [{"b64_json": valid_png_b64(544, 1120)}], "created": 1},
        {"data": [{"b64_json": valid_png_b64(1088, 2240)}], "created": 2},
    ]

    response = _generate_poster(client)

    assert response.status_code == 200
    payload = response.json()
    assert fake.run_json.await_count == 2
    assert payload["saved_image_width"] == 1088
    assert payload["saved_image_height"] == 2240
    assert payload["size_mismatch_retries"] == 1
    assert not payload.get("image_size_normalized")


def test_size_mismatch_keeps_closest_aspect_when_all_attempts_fail(make_client, settings_factory) -> None:
    from test_api import png_b64_with_dimensions

    settings = settings_factory(default_api_key="sk-test", size_mismatch_max_retries=1)
    client, fake, resolved = make_client(settings=settings)
    fake.run_json.side_effect = [
        {"data": [{"b64_json": png_b64_with_dimensions(900, 1750)}], "created": 1},
        {"data": [{"b64_json": png_b64_with_dimensions(1920, 1080)}], "created": 1},
    ]

    response = _generate_poster(client)

    assert response.status_code == 200
    payload = response.json()
    assert fake.run_json.await_count == 2
    assert payload["size_mismatch"] is True
    assert payload["saved_image_width"] == 900
    assert payload["saved_image_height"] == 1750
    assert payload["size_mismatch_retries"] == 1
    assert payload["metadata"]["size_mismatch_retries"] == 1
    assert payload["metadata"]["upstream_attempts"] == 2
    assert "已自动重新生成" in payload["size_mismatch_message"]
    outputs = list((resolved.data_dir / "outputs").rglob("*.png"))
    assert len(outputs) == 1


def test_size_mismatch_retry_disabled(make_client, settings_factory) -> None:
    from test_api import png_b64_with_dimensions

    settings = settings_factory(default_api_key="sk-test", size_mismatch_max_retries=0)
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {
        "data": [{"b64_json": png_b64_with_dimensions(1024, 1536)}],
        "created": 1,
    }

    response = _generate_poster(client)

    assert response.status_code == 200
    payload = response.json()
    assert fake.run_json.await_count == 1
    assert payload["size_mismatch"] is True
    assert "size_mismatch_retries" not in payload


def test_size_mismatch_failed_retry_is_auditable(make_client, settings_factory) -> None:
    from test_api import png_b64_with_dimensions

    settings = settings_factory(default_api_key="sk-test", size_mismatch_max_retries=1)
    client, fake, _ = make_client(settings=settings)
    fake.run_json.side_effect = [
        {"data": [{"b64_json": png_b64_with_dimensions(900, 1750)}], "created": 1},
        APIError(504, "上游超时", code="upstream_timeout"),
    ]

    response = _generate_poster(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["size_mismatch_retries"] == 1
    assert payload["metadata"]["upstream_attempts"] == 2
    assert payload["metadata"]["size_mismatch_retry_error_code"] == "upstream_timeout"
    assert "最后一次重试失败" in payload["size_mismatch_message"]


def test_size_mismatch_no_retry_for_multi_sample(make_client, settings_factory) -> None:
    from test_api import png_b64_with_dimensions

    settings = settings_factory(default_api_key="sk-test", size_mismatch_max_retries=2)
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {
        "data": [
            {"b64_json": png_b64_with_dimensions(1024, 1536)},
            {"b64_json": png_b64_with_dimensions(1024, 1536)},
        ],
        "created": 1,
    }

    response = client.post(
        "/api/generate",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/generations",
            "prompt": "生成一张 6 人游竖版旅行海报",
            "model": "gpt-image-2",
            "size": "1088x2240",
            "sample_count": 2,
        },
    )

    assert response.status_code == 200
    assert fake.run_json.await_count == 1


def test_responses_channel_reinforces_size_in_prompt(make_client, settings_factory) -> None:
    from test_api import png_b64_with_dimensions

    settings = settings_factory(default_api_key="sk-test", size_mismatch_max_retries=0)
    client, fake, _ = make_client(settings=settings)
    fake.run_responses.return_value = {
        "data": [{"b64_json": png_b64_with_dimensions(1088, 2240)}],
        "created": 1,
    }

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/responses",
            "prompt": "生成一张 6 人游竖版旅行海报",
            "size": "1088x2240",
        },
    )

    assert response.status_code == 200
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["model"] == "gpt-5.6-sol"
    assert upstream_payload["reasoning"]["effort"] == "xhigh"
    input_text = upstream_payload["input"][0]["content"][0]["text"]
    assert "画布尺寸要求" in input_text
    assert "1088x2240" in input_text


# --- text fidelity transcript diff -------------------------------------------


def test_transcript_diff_catches_single_char_substitution() -> None:
    from picgen.routes import _transcript_diff_report

    before = ["逃离人海喧嚣，坠入北疆的秋天童话", "禾木的白桦林镶上金黄，"]
    after = ["逃离人海喧器，坠入北疆的秋天童话", "禾木的白桦林镶上金黄，"]
    report = _transcript_diff_report(before, after, "主标题字体小一点")
    assert "结论：不通过" in report
    assert "喧" in report


def test_transcript_diff_ignores_line_split_and_logo(caplog) -> None:
    from picgen.routes import _transcript_diff_report

    before = ["6人游定制旅行", "24h管家：", "有温度的陪伴随时在线"]
    after = ["Friends & Family", "24h", "管家：", "有温度的陪伴随时在线"]
    report = _transcript_diff_report(before, after, "")
    assert "结论：通过" in report


def test_transcript_diff_allows_requested_changes() -> None:
    from picgen.routes import _transcript_diff_report

    before = ["4人参考价：10800元/人起"]
    after = ["4人参考价：12800元/人起"]
    report = _transcript_diff_report(before, after, "把价格改成 12800")
    assert "结论：通过" in report


# --- auth store --------------------------------------------------------------


def _make_store(tmp_path: Path) -> AuthStore:
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.initialize()
    return store


def _record_image(store: AuthStore, user_id: int, *, url: str, metadata: dict | None = None) -> int:
    job_id = store.create_generation_job(
        request_id="req",
        user_id=user_id,
        username="tester",
        endpoint_path="/api/generate",
        mode="generate",
        model="gpt-image-2",
        size="1024x1024",
    )
    records = store.complete_generation_job(
        job_id=job_id,
        result={
            "images": [
                {
                    "saved_image_url": url,
                    "saved_image_path": f"/tmp/{url}",
                    "saved_image_bytes": 10,
                    "metadata": metadata or {},
                }
            ]
        },
        elapsed_ms=1.0,
    )
    return int(records[0]["id"])


def test_preferences_put_replaces_fields_and_ui_mode_patch_preserves_them(make_client, settings_factory) -> None:
    settings = settings_factory(auth_enabled=True, admin_password="correct horse battery admin")
    client, _, _ = make_client(settings=settings)
    assert (
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "correct horse battery"},
        ).status_code
        == 200
    )

    first = client.put(
        "/api/preferences",
        json={
            "default_model": "gpt-image-2",
            "default_size": "1088x2240",
            "default_quality": "high",
            "logo_overlay_enabled": False,
            "ui_mode": "professional",
        },
    )
    assert first.status_code == 200
    assert first.json()["preferences"]["ui_mode"] == "professional"

    legacy = client.put(
        "/api/preferences",
        json={"default_size": "1792x1792"},
    )
    assert legacy.status_code == 200
    assert legacy.json()["preferences"]["default_size"] == "1792x1792"
    assert legacy.json()["preferences"]["ui_mode"] == "professional"
    assert legacy.json()["preferences"]["default_model"] == ""
    assert legacy.json()["preferences"]["default_quality"] == ""
    assert legacy.json()["preferences"]["logo_overlay_enabled"] is True

    mode_only = client.patch("/api/preferences/ui-mode", json={"ui_mode": "simple"})
    assert mode_only.status_code == 200
    assert mode_only.json()["preferences"]["ui_mode"] == "simple"
    assert mode_only.json()["preferences"]["default_size"] == "1792x1792"
    assert mode_only.json()["preferences"]["default_model"] == ""
    assert mode_only.json()["preferences"]["default_quality"] == ""
    assert mode_only.json()["preferences"]["logo_overlay_enabled"] is True


@pytest.mark.parametrize("ui_mode", ["", "expert", None])
def test_preferences_rejects_unsupported_ui_mode(make_client, settings_factory, ui_mode) -> None:
    settings = settings_factory(auth_enabled=True, admin_password="correct horse battery admin")
    client, _, _ = make_client(settings=settings)
    assert (
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "correct horse battery"},
        ).status_code
        == 200
    )

    response = client.put("/api/preferences", json={"ui_mode": ui_mode})

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_legacy_preferences_table_gains_optional_ui_mode_column(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    user = store.create_user("legacy-user", "correct horse battery")
    store.update_user_preferences(user_id=user.id, default_size="1088x2240")

    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        conn.execute("DROP TABLE user_preferences")
        conn.executescript(
            """
            CREATE TABLE user_preferences (
                user_id INTEGER PRIMARY KEY,
                default_model TEXT NOT NULL DEFAULT '',
                default_responses_model TEXT NOT NULL DEFAULT '',
                default_size TEXT NOT NULL DEFAULT '',
                default_quality TEXT NOT NULL DEFAULT '',
                default_output_format TEXT NOT NULL DEFAULT '',
                default_image_transport TEXT NOT NULL DEFAULT '',
                logo_overlay_enabled INTEGER NOT NULL DEFAULT 1,
                auto_copyright_check_enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            INSERT INTO user_preferences (
                user_id, default_size, logo_overlay_enabled,
                auto_copyright_check_enabled, updated_at
            )
            VALUES (?, '1088x2240', 1, 1, '2026-07-01T00:00:00+00:00')
            """,
            (user.id,),
        )

    migrated = AuthStore(tmp_path / "auth.sqlite3")
    migrated.initialize()
    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(user_preferences)")}
    assert "ui_mode" in columns
    preferences = migrated.get_user_preferences(user_id=user.id)
    assert preferences["default_size"] == "1088x2240"
    assert "ui_mode" not in preferences

    updated = migrated.update_user_preferences(
        user_id=user.id,
        default_size="1088x2240",
        ui_mode="simple",
    )
    assert updated["ui_mode"] == "simple"


def test_version_history_not_limited_by_library_size(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    user = store.create_user("wilson", "correct horse battery")
    first = _record_image(store, user.id, url="files/outputs/a.png")
    second = _record_image(store, user.id, url="files/outputs/b.png")

    # limit=1 with a 2-image library: the OLD flat query kept only the oldest
    # image, so the newer image's version history 404'd. The lineage-scoped
    # query must still find it.
    versions = store.list_generated_image_versions_for_user(
        generated_image_id=second, user_id=user.id, limit=1
    )
    assert versions is not None
    assert versions[0]["id"] == second

    # Sanity: the oldest image still resolves too.
    versions_first = store.list_generated_image_versions_for_user(
        generated_image_id=first, user_id=user.id, limit=1
    )
    assert versions_first is not None


def test_update_gallery_item_returns_image_metadata(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    user = store.create_user("wilson", "correct horse battery")
    image_id = _record_image(
        store,
        user.id,
        url="files/outputs/logo-final.png",
        metadata={"source_saved_image_url": "files/outputs/base.png"},
    )

    updated = store.update_gallery_item(
        user_id=user.id, generated_image_id=image_id, is_favorite=True, tags=["旅行"]
    )

    # The PUT response must carry the same metadata the GET list carries;
    # dropping it made the frontend lose original_saved_image_url after a
    # favorite/tag update.
    assert updated["metadata"].get("source_saved_image_url") == "files/outputs/base.png"
    assert updated.get("original_saved_image_url") == "files/outputs/base.png"


def test_final_asset_metadata_merges_with_original_generation_metadata(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    user = store.create_user("wilson", "correct horse battery")
    image_id = _record_image(
        store,
        user.id,
        url="files/outputs/base.png",
        metadata={"upstream_actual_size": "544x1120", "size_retry_count": 1},
    )

    store.replace_generated_image_asset(
        generated_image_id=image_id,
        user_id=user.id,
        image={
            "saved_image_path": str(tmp_path / "outputs" / "base-logo.png"),
            "saved_image_url": "files/outputs/base-logo.png",
            "saved_image_name": "base-logo.png",
            "saved_image_mime": "image/png",
            "saved_image_width": 1088,
            "saved_image_height": 2240,
            "saved_image_bytes": 123,
            "metadata": {"logo_overlay_applied": True},
        },
        logo_overlay_applied=True,
    )

    detail = store.generated_image_detail_for_user(generated_image_id=image_id, user_id=user.id)
    assert detail is not None
    assert detail["metadata"]["upstream_actual_size"] == "544x1120"
    assert detail["metadata"]["size_retry_count"] == 1
    assert detail["metadata"]["logo_overlay_applied"] is True


# --- 2026-07-10 full-project sweep ---------------------------------------


def test_strict_size_normalizes_same_aspect_upscale(make_client, settings_factory) -> None:
    from test_api import valid_png_b64

    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    # Exactly half the target on both axes: same aspect, safe to upscale.
    fake.run_json.return_value = {"data": [{"b64_json": valid_png_b64(544, 1120)}], "created": 1}

    response = _generate_poster(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved_image_width"] == 1088
    assert payload["saved_image_height"] == 2240
    assert not payload.get("size_mismatch")
    assert payload.get("image_size_normalized") is True
    assert payload.get("upstream_actual_size") == "544x1120"


def test_strict_size_keeps_wrong_aspect_without_cropping(make_client, settings_factory) -> None:
    from test_api import valid_png_b64

    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    # 1024x1536 (0.667) vs 1088x2240 (0.486): a cover-fit crop would cut ~27%
    # of the poster's width. The image must be kept as-is with a notice.
    fake.run_json.return_value = {"data": [{"b64_json": valid_png_b64(1024, 1536)}], "created": 1}

    response = _generate_poster(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved_image_width"] == 1024
    assert payload["saved_image_height"] == 1536
    assert payload.get("size_mismatch") is True
    assert "不一致" in str(payload.get("size_mismatch_message") or "")
    assert not payload.get("image_size_normalized")


def test_sanitize_filename_strips_url_hostile_chars() -> None:
    from picgen.storage import sanitize_filename, sanitize_filename_prefix

    # ? truncates saved_image_url in the browser; % double-decodes in
    # resolve_storage_path; # becomes a fragment.
    assert sanitize_filename("团队#2") == "团队2"
    assert sanitize_filename_prefix("a?b%c") == "abc"
    # Junk-only prefixes must not become a literal "image.png/" folder.
    assert sanitize_filename_prefix("??") == ""
    assert sanitize_filename_prefix("..") == ""


def test_prune_skips_old_folder_containing_recent_file(tmp_path: Path) -> None:
    import os

    outputs = tmp_path / "outputs"
    old_day = outputs / (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
    old_day.mkdir(parents=True)
    stale = old_day / "old.png"
    stale.write_bytes(b"x")
    old_ts = (datetime.now() - timedelta(days=10)).timestamp()
    os.utime(stale, (old_ts, old_ts))
    # A derived image (e.g. logo overlay of an old source) written today lands
    # in the source's day-folder; pruning by folder name alone would delete it.
    (old_day / "derived-today.png").write_bytes(b"y")

    removed = prune_old_outputs(outputs, retention_days=7)

    assert removed == 0
    assert (old_day / "derived-today.png").exists()

    # Once every file is genuinely old, the folder goes.
    fresh = old_day / "derived-today.png"
    os.utime(fresh, (old_ts, old_ts))
    assert prune_old_outputs(outputs, retention_days=7) == 1
    assert not old_day.exists()


def test_expired_lock_resets_counter_and_active_lock_blocks(tmp_path: Path) -> None:
    import sqlite3

    from picgen.auth import AccountLockedError, InvalidCredentialsError

    store = _make_store(tmp_path)
    user = store.create_user("wilson", "correct horse battery")

    def set_lock_state(count: int, locked_until: str | None) -> None:
        with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
            conn.execute(
                "UPDATE users SET failed_login_count = ?, locked_until = ? WHERE id = ?",
                (count, locked_until, user.id),
            )

    # Expired lock + wrong password: served their time, restart count at 1.
    past = (datetime.now(tz=UTC) - timedelta(minutes=30)).isoformat(timespec="seconds")
    set_lock_state(5, past)
    with pytest.raises(InvalidCredentialsError):
        store.authenticate("wilson", "wrong-password")
    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        row = conn.execute(
            "SELECT failed_login_count, locked_until FROM users WHERE id = ?", (user.id,)
        ).fetchone()
    assert row[0] == 1
    assert row[1] is None

    # Active lock still blocks even with the correct password.
    future = (datetime.now(tz=UTC) + timedelta(minutes=30)).isoformat(timespec="seconds")
    set_lock_state(5, future)
    with pytest.raises(AccountLockedError):
        store.authenticate("wilson", "correct horse battery")


def test_password_reset_invalidates_login_verified_against_old_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from picgen import auth as auth_module

    first = _make_store(tmp_path)
    second = AuthStore(tmp_path / "auth.sqlite3")
    user = first.create_user("wilson", "old correct horse battery")
    verified = threading.Event()
    resume = threading.Event()
    original_verify = auth_module.verify_password

    def blocking_verify(password: str, encoded: str) -> bool:
        result = original_verify(password, encoded)
        if password == "old correct horse battery":
            verified.set()
            assert resume.wait(timeout=5)
        return result

    monkeypatch.setattr(auth_module, "verify_password", blocking_verify)
    with ThreadPoolExecutor(max_workers=1) as pool:
        login = pool.submit(
            first.authenticate_and_create_session,
            "wilson",
            "old correct horse battery",
            days=1,
        )
        assert verified.wait(timeout=5)
        second.reset_user_password(
            user_id=user.id,
            password="new correct horse battery",
            admin_user_id=user.id,
        )
        resume.set()
        with pytest.raises(InvalidCredentialsError):
            login.result(timeout=5)

    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user.id,)).fetchone()[0] == 0


def test_concurrent_successful_login_does_not_clear_new_account_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from picgen import auth as auth_module

    first = _make_store(tmp_path)
    second = AuthStore(tmp_path / "auth.sqlite3")
    user = first.create_user("wilson", "correct horse battery")
    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        conn.execute("UPDATE users SET failed_login_count = 4 WHERE id = ?", (user.id,))

    verified = threading.Event()
    resume = threading.Event()
    original_verify = auth_module.verify_password

    def blocking_verify(password: str, encoded: str) -> bool:
        result = original_verify(password, encoded)
        if password == "correct horse battery":
            verified.set()
            assert resume.wait(timeout=5)
        return result

    monkeypatch.setattr(auth_module, "verify_password", blocking_verify)
    with ThreadPoolExecutor(max_workers=1) as pool:
        login = pool.submit(first.authenticate, "wilson", "correct horse battery")
        assert verified.wait(timeout=5)
        with pytest.raises(InvalidCredentialsError):
            second.authenticate("wilson", "wrong password")
        resume.set()
        with pytest.raises(AccountLockedError):
            login.result(timeout=5)

    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        failed_count, locked_until = conn.execute(
            "SELECT failed_login_count, locked_until FROM users WHERE id = ?", (user.id,)
        ).fetchone()
    assert failed_count >= 5
    assert locked_until


def test_error_mentions_sample_count_ignores_moderation_prose() -> None:
    from picgen.routes import _error_mentions_sample_count

    moderation = APIError(400, "your sample was flagged by moderation", code="upstream_error")
    assert not _error_mentions_sample_count(moderation)
    named_param = APIError(400, 'The parameter "n" is not supported', code="upstream_error")
    assert _error_mentions_sample_count(named_param)


def test_itinerary_size_accepts_uppercase_x() -> None:
    from picgen.routes import _parse_itinerary_size

    assert _parse_itinerary_size("1920X1088") == (1920, 1088)

"""Regression tests for the 2026-07 full-project bug sweep."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from test_api import TINY_PNG_B64

from picgen.auth import AuthStore
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
        ],
    }
    payload = prepare_image_payload(
        upstream,
        data_dir=tmp_path,
        outputs_dir=tmp_path / "outputs",
        user_agent="UA",
        save_context={"mode": "generate"},
        fetch_remote=None,
    )
    assert payload["candidate_count"] == 1
    assert payload["images"][0]["candidate_index"] == 1


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


def test_size_mismatch_keeps_largest_when_all_attempts_fail(make_client, settings_factory) -> None:
    from test_api import png_b64_with_dimensions

    settings = settings_factory(default_api_key="sk-test", size_mismatch_max_retries=1)
    client, fake, resolved = make_client(settings=settings)
    fake.run_json.side_effect = [
        {"data": [{"b64_json": png_b64_with_dimensions(1024, 1536)}], "created": 1},
        {"data": [{"b64_json": png_b64_with_dimensions(512, 768)}], "created": 1},
    ]

    response = _generate_poster(client)

    assert response.status_code == 200
    payload = response.json()
    assert fake.run_json.await_count == 2
    assert payload["size_mismatch"] is True
    assert payload["saved_image_width"] == 1024
    assert payload["size_mismatch_retries"] == 1
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

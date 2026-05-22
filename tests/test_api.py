from __future__ import annotations

from pathlib import Path

import pytest
from starlette.types import Scope

from picgen.errors import APIError
from picgen.middleware import BodySizeLimitMiddleware
from picgen.upstream import parse_sse_json_events, stream_events_to_image_payload

TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def test_health_endpoint_reports_ok(make_client):
    client, _, _ = make_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_ready_endpoint_reports_dependencies(make_client):
    client, _, _ = make_client()
    response = client.get("/api/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["storage_writable"] is True
    assert payload["upstream_client_ready"] is True
    assert "version" in payload


def test_config_reports_api_key_presence_without_leaking_value(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-secret")
    client, _, _ = make_client(settings=settings)
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["has_default_api_key"] is True
    assert payload["responses_url"] == "https://api.openai.com/v1/responses"
    assert payload["default_responses_model"] == "gpt-5.5"
    assert "sk-secret" not in response.text
    assert payload["max_image_bytes"] > 0
    assert payload["upstream_timeout_seconds"] > 0


def test_request_id_is_round_tripped(make_client):
    client, _, _ = make_client()
    response = client.get("/api/health", headers={"X-Request-ID": "abc1234567"})
    assert response.headers["x-request-id"] == "abc1234567"


def test_request_id_is_generated_when_missing(make_client):
    client, _, _ = make_client()
    response = client.get("/api/health")
    rid = response.headers.get("x-request-id", "")
    assert 8 <= len(rid) <= 64


def test_security_headers_are_set(make_client):
    client, _, _ = make_client()
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_generate_requires_prompt_before_api_key(make_client):
    client, _, _ = make_client()
    response = client.post("/api/generate", json={"api_key": "sk-test"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "生成提示词不能为空"
    assert body["code"] == "validation_error"


def test_edit_requires_image_payload(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, _, _ = make_client(settings=settings)
    response = client.post("/api/edit", json={"prompt": "换成水彩风格"})
    assert response.status_code == 400
    assert response.json()["error"] == "缺少 image 文件"


def test_edit_uses_images_api_and_preserves_mode(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.return_value = {
        "data": [{"b64_json": TINY_PNG_B64}],
        "created": 99,
    }

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "把背景改成纯白",
            "model": "gpt-image-2",
            "mode": "reference",
            "size": "1024x1024",
            "quality": "high",
            "output_format": "png",
            "image": {
                "name": "ref.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "reference"
    assert payload["model"] == "gpt-image-2"
    assert payload["saved_image_url"].startswith("/files/outputs/")
    assert payload["raw_response"]["data"][0]["b64_json"].startswith("[omitted ")
    assert TINY_PNG_B64 not in str(payload["raw_response"])

    fake.run_multipart.assert_awaited_once()
    upstream_args = fake.run_multipart.await_args.args
    # signature: (url, api_key, fields, files, user_agent)
    assert upstream_args[0] == "https://api.openai.com/v1/images/edits"
    fields = upstream_args[2]
    assert fields["model"] == "gpt-image-2"
    assert fields["prompt"] == "把背景改成纯白"
    assert fields["size"] == "1024x1024"
    assert fields["quality"] == "high"
    assert fields["output_format"] == "png"
    files = upstream_args[3]
    assert len(files) == 1
    assert files[0]["field_name"] == "image"
    assert files[0]["filename"] == "ref.png"


def test_edit_accepts_ordered_reference_images_and_returns_candidates(
    make_client, settings_factory
):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.return_value = {
        "data": [
            {"b64_json": TINY_PNG_B64, "revised_prompt": "candidate 1"},
            {"b64_json": TINY_PNG_B64, "revised_prompt": "candidate 2"},
            {"b64_json": TINY_PNG_B64, "revised_prompt": "candidate 3"},
        ],
        "created": 100,
    }

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "把素材做成模板风格",
            "model": "gpt-image-2",
            "mode": "reference",
            "sample_count": 3,
            "images": [
                {
                    "name": "style.png",
                    "type": "image/png",
                    "role": "style_template",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
                {
                    "name": "material.png",
                    "type": "image/png",
                    "role": "material",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sample_count"] == 3
    assert payload["candidate_count"] == 3
    assert len(payload["images"]) == 3
    assert payload["source_image_names"] == ["style.png", "material.png"]
    assert payload["source_image_roles"] == ["style_template", "material"]
    assert payload["saved_image_url"] == payload["images"][0]["saved_image_url"]

    upstream_args = fake.run_multipart.await_args.args
    fields = upstream_args[2]
    assert fields["n"] == 3
    files = upstream_args[3]
    assert [part["field_name"] for part in files] == ["image", "image"]
    assert [part["filename"] for part in files] == ["style.png", "material.png"]
    assert [part["role"] for part in files] == ["style_template", "material"]


def test_edit_fans_out_when_upstream_returns_fewer_candidates(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.side_effect = [
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 1},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 2},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 3},
    ]

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "生成三张候选",
            "model": "gpt-image-2",
            "sample_count": 3,
            "images": [
                {
                    "name": "style.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
                {
                    "name": "material.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["candidate_count"] == 3
    assert fake.run_multipart.await_count == 3
    first_fields = fake.run_multipart.await_args_list[0].args[2]
    second_fields = fake.run_multipart.await_args_list[1].args[2]
    assert first_fields["n"] == 3
    assert "n" not in second_fields


def test_edit_retries_without_sample_count_after_502(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.side_effect = [
        APIError(502, "Upstream request failed", code="upstream_error"),
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 1},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 2},
        {"data": [{"b64_json": TINY_PNG_B64}], "created": 3},
    ]

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "生成三张候选",
            "model": "gpt-image-2",
            "sample_count": 3,
            "images": [
                {
                    "name": "style.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
                {
                    "name": "material.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["candidate_count"] == 3
    assert fake.run_multipart.await_count == 4
    assert fake.run_multipart.await_args_list[0].args[2]["n"] == 3
    assert "n" not in fake.run_multipart.await_args_list[1].args[2]


def test_edit_passes_mask_and_options(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 0}

    response = client.post(
        "/api/edit",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/images/edits",
            "prompt": "去掉文字",
            "model": "gpt-image-2",
            "mode": "edit",
            "output_format": "webp",
            "output_compression": 80,
            "image": {
                "name": "src.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
            "mask": {
                "name": "mask.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 200
    upstream_args = fake.run_multipart.await_args.args
    fields = upstream_args[2]
    assert fields["output_format"] == "webp"
    assert fields["output_compression"] == 80
    files = upstream_args[3]
    field_names = sorted(part["field_name"] for part in files)
    assert field_names == ["image", "mask"]


def test_responses_image_requires_prompt(make_client):
    client, _, _ = make_client()
    response = client.post("/api/responses-image", json={"api_key": "sk-test"})
    assert response.status_code == 400
    assert response.json()["error"] == "Responses 图像提示词不能为空"


def test_responses_image_saves_streamed_image(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_responses.return_value = {
        "data": [{"b64_json": TINY_PNG_B64}],
        "created": 1,
        "response_id": "resp_test",
        "stream_events": [{"type": "response.image_generation_call.partial_image"}],
    }
    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/responses",
            "prompt": "生成一张小图",
            "model": "gpt-5.5",
            "mode": "reference",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "reference"
    assert payload["model"] == "gpt-5.5"
    assert payload["saved_image_url"].startswith("/files/outputs/")
    assert (Path(payload["saved_image_path"])).is_file()
    fake.run_responses.assert_awaited_once()
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["stream"] is True
    assert upstream_payload["tools"] == [{"type": "image_generation"}]


def test_responses_image_uploads_input_file_and_uses_file_id(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.return_value = {"id": "file_test_input"}
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "基于这张图重新打光",
            "model": "gpt-5.5",
            "mode": "edit",
            "image": {
                "name": "source.png",
                "type": "image/png",
                "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["files_endpoint_url"] == "https://sub.tidba.com/v1/files"
    assert payload["source_file_id"] == "file_test_input"
    fake.run_file_upload.assert_awaited_once()
    assert fake.run_file_upload.await_args.args[0] == "https://sub.tidba.com/v1/files"
    assert fake.run_file_upload.await_args.args[2]["filename"] == "source.png"
    upstream_payload = fake.run_responses.await_args.args[2]
    content = upstream_payload["input"][0]["content"]
    assert content == [
        {"type": "input_text", "text": "基于这张图重新打光"},
        {"type": "input_image", "file_id": "file_test_input"},
    ]
    assert "data:image/png;base64" not in str(upstream_payload)


def test_responses_image_uploads_ordered_reference_images(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.side_effect = [{"id": "file_style"}, {"id": "file_material"}]
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "把素材做成模板风格",
            "model": "gpt-5.5",
            "mode": "reference",
            "sample_count": 3,
            "images": [
                {
                    "name": "style.png",
                    "type": "image/png",
                    "role": "style_template",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
                {
                    "name": "material.png",
                    "type": "image/png",
                    "role": "material",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_file_ids"] == ["file_style", "file_material"]
    assert payload["source_image_names"] == ["style.png", "material.png"]
    assert fake.run_file_upload.await_count == 2

    uploaded = [call.args[2]["filename"] for call in fake.run_file_upload.await_args_list]
    assert uploaded == ["style.png", "material.png"]
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["tools"][0]["n"] == 3
    assert upstream_payload["input"][0]["content"] == [
        {"type": "input_text", "text": "把素材做成模板风格"},
        {"type": "input_image", "file_id": "file_style"},
        {"type": "input_image", "file_id": "file_material"},
    ]


def test_copyright_risk_uses_gpt55_and_inline_images(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_responses.return_value = {
        "output_text": "风险等级：低\n可能风险点：含有活动标识，商用前确认授权。",
    }

    response = client.post(
        "/api/copyright-risk",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://api.openai.com/v1/responses",
            "prompt": "生成一张活动图",
            "images": [
                {
                    "name": "result.png",
                    "type": "image/png",
                    "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "gpt-5.5"
    assert "风险等级：低" in payload["risk_text"]
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["model"] == "gpt-5.5"
    content = upstream_payload["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert "版权与商标风险审查助手" in content[0]["text"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")


def test_responses_image_can_fallback_to_inline_after_file_upload_error(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.side_effect = APIError(502, "Files 上传接口在接收文件时断开连接")
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "基于这张图重新打光",
            "model": "gpt-5.5",
            "allow_inline_fallback": True,
            "image": {
                "name": "source-upload.jpg",
                "type": "image/jpeg",
                "data_url": f"data:image/jpeg;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["file_upload_fallback"] is True
    assert payload["source_file_id"] is None
    upstream_payload = fake.run_responses.await_args.args[2]
    content = upstream_payload["input"][0]["content"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")


def test_responses_image_falls_back_to_inline_by_default_after_file_upload_error(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.side_effect = APIError(502, "Files 上传接口在接收文件时断开连接")
    fake.run_responses.return_value = {"data": [{"b64_json": TINY_PNG_B64}], "created": 1}

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "基于这张图重新打光",
            "model": "gpt-5.5",
            "image": {
                "name": "source-upload.jpg",
                "type": "image/jpeg",
                "data_url": f"data:image/jpeg;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["file_upload_fallback"] is True
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,")


def test_responses_image_can_disable_inline_fallback(make_client, settings_factory):
    settings = settings_factory(default_api_key="sk-test")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.side_effect = APIError(502, "Files 上传接口在接收文件时断开连接")

    response = client.post(
        "/api/responses-image",
        json={
            "api_key": "sk-test",
            "endpoint_url": "https://sub.tidba.com/v1/responses",
            "prompt": "基于这张图重新打光",
            "model": "gpt-5.5",
            "allow_inline_fallback": False,
            "image": {
                "name": "source-upload.jpg",
                "type": "image/jpeg",
                "data_url": f"data:image/jpeg;base64,{TINY_PNG_B64}",
            },
        },
    )

    assert response.status_code == 502
    assert response.json()["error"] == "Files 上传接口在接收文件时断开连接"
    fake.run_responses.assert_not_called()


def test_payload_size_limit_blocks_oversized_request(make_client, settings_factory):
    settings = settings_factory(max_request_body_bytes=1024, default_api_key="sk-test")
    client, _, _ = make_client(settings=settings)
    big_payload = {"prompt": "a" * 2048}
    response = client.post("/api/generate", json=big_payload)
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_payload_size_limit_counts_streamed_body_without_content_length():
    async def drain_app(scope, receive, send):
        while True:
            message = await receive()
            if message["type"] != "http.request" or not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    app = BodySizeLimitMiddleware(drain_app, max_bytes=1024)
    messages = [
        {"type": "http.request", "body": b"a" * 800, "more_body": True},
        {"type": "http.request", "body": b"b" * 800, "more_body": False},
    ]
    sent: list[dict[str, object]] = []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/generate",
        "raw_path": b"/api/generate",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "root_path": "",
    }

    async def receive() -> dict[str, object]:
        return messages.pop(0)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    import anyio

    anyio.run(app, scope, receive, send)

    response_start = next(message for message in sent if message["type"] == "http.response.start")
    assert response_start["status"] == 413


def test_rate_limit_returns_429(make_client, settings_factory):
    settings = settings_factory(rate_limit_per_minute=2, rate_limit_burst=2)
    client, _, _ = make_client(settings=settings)
    # generate endpoint -> still validation 400, but counts toward rate limit
    client.post("/api/generate", json={})
    client.post("/api/generate", json={})
    response = client.post("/api/generate", json={})
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert "Retry-After" in response.headers


def test_proxy_auth_token_enforced(make_client, settings_factory):
    settings = settings_factory(proxy_auth_token="topsecret")
    client, _, _ = make_client(settings=settings)
    response = client.post("/api/generate", json={"prompt": "x"})
    assert response.status_code == 401
    response2 = client.post(
        "/api/generate",
        json={"prompt": "x"},
        headers={"X-Proxy-Token": "topsecret"},
    )
    # missing api_key but past auth
    assert response2.status_code in {400}
    health_response = client.get("/api/health")
    assert health_response.status_code == 200  # health is allowlisted


def test_responses_sse_parser_keeps_partial_image() -> None:
    body = (
        "event: response.image_generation_call.partial_image\n"
        f'data: {{"type":"response.image_generation_call.partial_image","partial_image_b64":"{TINY_PNG_B64}"}}\n\n'
        "data: [DONE]\n\n"
    )

    events = parse_sse_json_events(body)
    payload = stream_events_to_image_payload(events, url="https://api.openai.com/v1/responses", started_at=0)

    assert len(events) == 1
    assert payload["data"][0]["b64_json"] == TINY_PNG_B64


@pytest.mark.parametrize("payload", [
    {"prompt": " "},
    {"prompt": "x" * 32_001},
])
def test_generate_validation_errors(make_client, settings_factory, payload):
    settings = settings_factory(default_api_key="sk-test")
    client, _, _ = make_client(settings=settings)
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 400

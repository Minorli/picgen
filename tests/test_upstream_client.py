from __future__ import annotations

import json

import httpx
import pytest

from picgen.errors import APIError
from picgen.upstream import HttpxAsyncClient

pytestmark = pytest.mark.asyncio


async def _build_client(transport: httpx.MockTransport, **kwargs) -> HttpxAsyncClient:
    client = HttpxAsyncClient(**kwargs)
    # Swap the underlying client to use the mock transport while preserving config.
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=transport, timeout=client._client.timeout)
    return client


async def test_run_json_does_not_retry_non_idempotent_post() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, text='{"error": {"message": "transient"}}')

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=2, retry_backoff=0.0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_json("https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA")
        assert info.value.status == 503
        assert calls["count"] == 1
    finally:
        await client.aclose()


async def test_run_json_raises_after_max_retries() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(502, text='{"error":{"message":"bad"}}'))
    client = await _build_client(transport, max_retries=1, retry_backoff=0.0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_json("https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA")
        assert info.value.status == 502
    finally:
        await client.aclose()


async def test_run_json_reports_retry_exhaustion_to_user() -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            502,
            text='{"error":{"message":"An error occurred while processing your request."}}',
        )
    )
    client = await _build_client(transport, max_retries=2, retry_backoff=0.0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_json("https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA")
        assert info.value.status == 502
        assert "已自动尝试" not in info.value.message
        assert "上游连续返回" not in (info.value.details or "")
    finally:
        await client.aclose()


async def test_run_multipart_invalid_mask_is_not_misclassified_as_content_policy() -> None:
    body = json.dumps(
        {
            "error": {
                "code": "invalid_mask_image_format",
                "message": "Invalid mask image format - mask size does not match image size",
                "type": "image_generation_user_error",
            }
        }
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(400, text=body))
    client = await _build_client(transport, max_retries=0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_multipart(
                "https://upstream.test/images/edits",
                "sk-test",
                {"prompt": "add a lamp"},
                [],
                "UA",
            )
        assert info.value.status == 400
        assert info.value.code == "upstream_invalid_image_input"
        assert "内容审核" not in info.value.message
        assert "像素尺寸一致" in info.value.message
        assert "mask size does not match image size" in (info.value.details or "")
    finally:
        await client.aclose()


async def test_run_multipart_explicit_content_policy_code_is_still_classified() -> None:
    body = json.dumps(
        {
            "error": {
                "code": "content_policy_violation",
                "message": "The request violates content policy",
                "type": "image_generation_user_error",
            }
        }
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(400, text=body))
    client = await _build_client(transport, max_retries=0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_multipart(
                "https://upstream.test/images/edits",
                "sk-test",
                {"prompt": "disallowed"},
                [],
                "UA",
            )
        assert info.value.code == "upstream_content_policy"
        assert "内容审核" in info.value.message
    finally:
        await client.aclose()


async def test_run_json_translates_timeout() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.ConnectTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=2, retry_backoff=0.0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_json("https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA")
        assert info.value.status == 504
        assert info.value.code == "upstream_timeout"
        assert calls["count"] == 1
    finally:
        await client.aclose()


async def test_fetch_image_returns_bytes_and_mime() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"\x89PNG\r\n\x1a\n",
            headers={"Content-Type": "image/png"},
        )

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=0)
    try:
        data, mime = await client.fetch_image("https://cdn.test/img", "UA")
        assert data.startswith(b"\x89PNG")
        assert mime == "image/png"
    finally:
        await client.aclose()


async def test_fetch_image_rejects_oversized_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # No Content-Length declared up front; the cap must trigger while streaming.
        return httpx.Response(200, content=b"\x89PNG" + b"x" * 4096)

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=0, max_image_bytes=64)
    try:
        with pytest.raises(APIError) as info:
            await client.fetch_image("https://cdn.test/huge.png", "UA")
        assert info.value.status == 502
        assert "过大" in info.value.message
    finally:
        await client.aclose()


async def test_fetch_image_rejects_oversized_content_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"\x89PNG",
            headers={"Content-Length": "999999999"},
        )

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=0, max_image_bytes=64)
    try:
        with pytest.raises(APIError) as info:
            await client.fetch_image("https://cdn.test/huge.png", "UA")
        assert info.value.status == 502
    finally:
        await client.aclose()


async def test_fetch_image_retries_idempotent_download_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, text='{"error":{"message":"transient"}}')
        return httpx.Response(
            200,
            content=b"\x89PNG\r\n\x1a\n",
            headers={"Content-Type": "image/png"},
        )

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=2, retry_backoff=0.0)
    try:
        data, mime = await client.fetch_image("https://cdn.test/img", "UA")
        assert data.startswith(b"\x89PNG")
        assert mime == "image/png"
        assert calls["count"] == 2
    finally:
        await client.aclose()


async def test_run_responses_parses_sse() -> None:
    sse_body = (
        b'event: response.image_generation_call.partial_image\ndata: {"partial_image_b64":"abcd"}\n\ndata: [DONE]\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=0)
    try:
        payload = await client.run_responses(
            "https://upstream.test/responses",
            "sk-test",
            {"stream": True, "model": "gpt-5.5", "input": []},
            "UA",
        )
        assert payload["data"][0]["b64_json"] == "abcd"
    finally:
        await client.aclose()


async def test_run_responses_preserves_multiple_image_outputs() -> None:
    response_payload = {
        "id": "resp_multi",
        "created_at": 123,
        "model": "gpt-5.5",
        "status": "completed",
        "output": [
            {"type": "image_generation_call", "result": "image-one", "revised_prompt": "one"},
            {"type": "image_generation_call", "result": "image-two", "revised_prompt": "two"},
            {"type": "image_generation_call", "result": "image-three", "revised_prompt": "three"},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=json.dumps(response_payload),
            headers={"Content-Type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=0)
    try:
        payload = await client.run_responses(
            "https://upstream.test/responses",
            "sk-test",
            {"stream": False, "model": "gpt-5.5", "tools": [{"type": "image_generation"}], "input": []},
            "UA",
        )
        assert [item["b64_json"] for item in payload["data"]] == ["image-one", "image-two", "image-three"]
        assert [item["revised_prompt"] for item in payload["data"]] == ["one", "two", "three"]
    finally:
        await client.aclose()


async def test_run_responses_preserves_text_from_sse() -> None:
    coordinate_json = '[{"index":0,"name":"巴黎","lat":48.8566,"lng":2.3522,"confidence":0.72}]'
    sse_body = (
        b"event: response.output_text.delta\n"
        + json.dumps({"type": "response.output_text.delta", "delta": coordinate_json})
        .encode("utf-8")
        .join((b"data: ", b"\n\n"))
        + b"event: response.completed\n"
        + json.dumps(
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_text",
                    "model": "gpt-5.5",
                    "status": "completed",
                    "output_text": coordinate_json,
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": coordinate_json}],
                        }
                    ],
                },
            }
        )
        .encode("utf-8")
        .join((b"data: ", b"\n\n"))
        + b"data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=0)
    try:
        payload = await client.run_responses(
            "https://upstream.test/responses",
            "sk-test",
            {"model": "gpt-5.5", "instructions": "只返回 JSON", "input": []},
            "UA",
        )
        assert payload["id"] == "resp_text"
        assert payload["output_text"] == coordinate_json
        assert payload["output"][0]["content"][0]["text"] == coordinate_json
        assert payload["stream_events"]
    finally:
        await client.aclose()


async def test_run_responses_sends_stream_as_json_boolean() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            text=json.dumps({"id": "resp_1", "output": []}),
            headers={"Content-Type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=0)
    try:
        await client.run_responses(
            "https://upstream.test/responses",
            "sk-test",
            {"stream": True, "model": "gpt-5.5", "input": []},
            "UA",
        )
        assert observed["payload"]["stream"] is True
    finally:
        await client.aclose()


async def test_upstream_http_error_status_and_details_are_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            text=json.dumps(
                {
                    "error": {
                        "message": (
                            "Rate limit reached for gpt-image-2-codex in organization org-BOvpEHVcDPTe8h4lZnwMO5Ly"
                        ),
                        "type": "rate_limit_error",
                        "api_key": "sk-secret123456",
                    }
                }
            ),
        )

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_json(
                "https://upstream.test/generate",
                "sk-test",
                {"prompt": "hi"},
                "UA",
            )
        assert info.value.status == 429
        assert info.value.code == "upstream_rate_limited"
        assert "图片生成服务当前请求较多" in info.value.message
        assert "Rate limit reached" not in info.value.message
        assert "org-BOvpEHVcDPTe8h4lZnwMO5Ly" not in (info.value.details or "")
        assert "sk-secret123456" not in (info.value.details or "")
        assert "rate_limit_error" in (info.value.details or "")
    finally:
        await client.aclose()

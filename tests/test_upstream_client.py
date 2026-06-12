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


async def test_run_json_retries_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 2:
            return httpx.Response(503, text='{"error": {"message": "transient"}}')
        return httpx.Response(200, text=json.dumps({"data": [{"b64_json": "abc"}]}))

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=2, retry_backoff=0.0)
    try:
        payload = await client.run_json("https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA")
        assert payload["data"][0]["b64_json"] == "abc"
        assert calls["count"] == 2
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
        assert "已自动尝试 3 次" in info.value.message
        assert "上游连续返回 502" in (info.value.details or "")
    finally:
        await client.aclose()


async def test_run_json_translates_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=0, retry_backoff=0.0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_json("https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA")
        assert info.value.status == 504
        assert info.value.code == "upstream_timeout"
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

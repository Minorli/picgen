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
        payload = await client.run_json(
            "https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA"
        )
        assert payload["data"][0]["b64_json"] == "abc"
        assert calls["count"] == 2
    finally:
        await client.aclose()


async def test_run_json_raises_after_max_retries() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(502, text='{"error":{"message":"bad"}}'))
    client = await _build_client(transport, max_retries=1, retry_backoff=0.0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_json(
                "https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA"
            )
        assert info.value.status == 502
    finally:
        await client.aclose()


async def test_run_json_translates_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)
    client = await _build_client(transport, max_retries=0, retry_backoff=0.0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_json(
                "https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA"
            )
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


async def test_run_responses_parses_sse() -> None:
    sse_body = (
        b"event: response.image_generation_call.partial_image\n"
        b'data: {"partial_image_b64":"abcd"}\n\n'
        b"data: [DONE]\n\n"
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

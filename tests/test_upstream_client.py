from __future__ import annotations

import json
import logging

import httpx
import pytest

from picgen.errors import APIError
from picgen.upstream import HttpxAsyncClient

pytestmark = pytest.mark.asyncio


async def _build_client(transport: httpx.MockTransport, **kwargs) -> HttpxAsyncClient:
    client = HttpxAsyncClient(**kwargs)
    # Swap the underlying client to use the mock transport while preserving config.
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=transport, timeout=client._client.timeout, follow_redirects=client._client.follow_redirects
    )
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


async def test_run_json_preserves_deep_upstream_400_without_recursion_error() -> None:
    depth = 1100
    body = '{"error":' * depth + '{"message":"deep rejection"}' + "}" * depth
    transport = httpx.MockTransport(lambda request: httpx.Response(400, text=body))
    client = await _build_client(transport, max_retries=0)
    try:
        with pytest.raises(APIError) as info:
            await client.run_json("https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA")
        assert info.value.status == 400
        assert info.value.code == "upstream_error"
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


async def test_run_json_translates_timeout(caplog) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.ConnectTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)
    client = await _build_client(
        transport, max_retries=2, retry_backoff=0.0, connect_timeout=15.0, total_timeout=1200.0
    )
    try:
        with caplog.at_level(logging.WARNING), pytest.raises(APIError) as info:
            await client.run_json("https://upstream.test/generate", "sk-test", {"prompt": "hi"}, "UA")
        assert info.value.status == 504
        assert info.value.code == "upstream_timeout"
        assert calls["count"] == 3
        assert "连接" in info.value.message
        assert "1200" not in (info.value.details or "")
        record = next(record for record in caplog.records if record.getMessage() == "upstream_timeout")
        assert record.fields["timeout_s"] == 15.0
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


async def _run_generation(client: HttpxAsyncClient, method: str) -> dict:
    url = "https://upstream.test/generate"
    if method == "run_multipart":
        return await client.run_multipart(url, "sk-test", {"prompt": "测试图片"}, [], "UA")
    if method == "run_responses":
        return await client.run_responses(url, "sk-test", {"stream": True, "input": "测试图片"}, "UA")
    return await client.run_json(url, "sk-test", {"prompt": "测试图片"}, "UA")


@pytest.mark.parametrize("method", ["run_json", "run_multipart", "run_responses"])
@pytest.mark.parametrize("error_type", [httpx.ConnectTimeout, httpx.ConnectError])
async def test_generation_recovers_from_initial_connection_failure(method, error_type) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise error_type("connection failed", request=request)
        return httpx.Response(200, json={"data": [{"b64_json": "image-result"}]})

    client = await _build_client(httpx.MockTransport(handler), max_retries=2, retry_backoff=0.0)
    try:
        result = await _run_generation(client, method)
        assert result["data"] == [{"b64_json": "image-result"}]
        assert len(requests) == 2
        assert requests[0].content == requests[1].content
        assert requests[0].headers == requests[1].headers
    finally:
        await client.aclose()


@pytest.mark.parametrize("method", ["run_json", "run_multipart", "run_responses"])
@pytest.mark.parametrize("error_type", [httpx.ConnectTimeout, httpx.ConnectError])
@pytest.mark.parametrize("max_retries", [0, 2])
async def test_generation_connection_retries_are_bounded(method, error_type, max_retries) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise error_type("connection failed", request=request)

    client = await _build_client(httpx.MockTransport(handler), max_retries=max_retries, retry_backoff=0.0)
    try:
        with pytest.raises(APIError) as info:
            await _run_generation(client, method)
        expected_code = "upstream_timeout" if error_type is httpx.ConnectTimeout else "upstream_network_error"
        assert info.value.code == expected_code
        assert calls == max_retries + 1
    finally:
        await client.aclose()


@pytest.mark.parametrize("method", ["run_json", "run_multipart", "run_responses"])
@pytest.mark.parametrize(
    "error_type",
    [
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.ReadError,
        httpx.WriteError,
        httpx.RemoteProtocolError,
    ],
)
async def test_generation_does_not_retry_ambiguous_send_failures(method, error_type) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise error_type("request failed", request=request)

    client = await _build_client(httpx.MockTransport(handler), max_retries=2, retry_backoff=0.0)
    try:
        with pytest.raises(APIError):
            await _run_generation(client, method)
        assert calls == 1
    finally:
        await client.aclose()


@pytest.mark.parametrize("method", ["run_json", "run_multipart", "run_responses"])
async def test_generation_does_not_retry_http_service_unavailable(method) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    client = await _build_client(httpx.MockTransport(handler), max_retries=2, retry_backoff=0.0)
    try:
        with pytest.raises(APIError) as info:
            await _run_generation(client, method)
        assert info.value.status == 503
        assert calls == 1
    finally:
        await client.aclose()


@pytest.mark.parametrize("method", ["run_json", "run_multipart", "run_responses"])
@pytest.mark.parametrize("error_type", [httpx.ConnectTimeout, httpx.ConnectError])
@pytest.mark.parametrize("redirect_path", ["/redirected", "/generate"])
async def test_generation_does_not_restart_post_after_redirect_connection_failure(
    method, error_type, redirect_path
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(307, headers={"Location": redirect_path})
        raise error_type("redirect connection failed", request=request)

    client = await _build_client(httpx.MockTransport(handler), max_retries=2, retry_backoff=0.0)
    try:
        with pytest.raises(APIError):
            await _run_generation(client, method)
        assert len(requests) == 2
        assert requests[0].url.path == "/generate"
        assert requests[1].url.path == redirect_path
        assert all(request.method == "POST" for request in requests)
    finally:
        await client.aclose()


@pytest.mark.parametrize("method", ["run_json", "run_multipart", "run_responses"])
@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ReadError, httpx.ConnectError])
async def test_generation_does_not_retry_response_body_failure_and_closes_stream(method, error_type) -> None:
    calls = 0

    class FailingBody(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b'{"data": ['
            raise error_type("response body interrupted")

        async def aclose(self):
            self.closed = True

    body = FailingBody()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, stream=body, headers={"Content-Type": "application/json"})

    client = await _build_client(httpx.MockTransport(handler), max_retries=2, retry_backoff=0.0)
    try:
        with pytest.raises(APIError):
            await _run_generation(client, method)
        assert calls == 1
        assert body.closed
    finally:
        await client.aclose()

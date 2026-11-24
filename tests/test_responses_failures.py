from __future__ import annotations

import logging

import httpx
import pytest

from picgen.errors import APIError
from picgen.upstream.client import HttpxAsyncClient
from picgen.upstream.errors import extract_error_message
from picgen.upstream.payload import compact_raw_response, normalize_responses_image_payload
from picgen.upstream.responses import parse_sse_json_events, stream_events_to_image_payload


def _stream(events):
    return stream_events_to_image_payload(events, url="https://upstream.test/responses", started_at=0)


@pytest.mark.parametrize("status", ["failed", "incomplete", "cancelled"])
@pytest.mark.parametrize("with_preview", [False, True])
def test_failed_response_never_becomes_preview_success(status, with_preview):
    events = [{"type": "response.image_generation_call.partial_image", "partial_image_b64": "preview"}]
    if not with_preview:
        events = []
    events.append({"type": f"response.{status}", "response": {"id": "resp_failed", "status": status}})

    with pytest.raises(APIError) as info:
        _stream(events)

    assert info.value.code == "upstream_error"
    assert info.value.status == 502
    assert "resp_failed" in info.value.details
    assert status in info.value.details


@pytest.mark.parametrize("event_type", ["response.failed", "response.incomplete", "error"])
def test_failure_event_without_response_status_is_still_rejected(event_type):
    with pytest.raises(APIError):
        _stream([{"type": event_type}])


@pytest.mark.parametrize(
    ("upstream_code", "expected_code", "expected_status"),
    [
        ("rate_limit_exceeded", "upstream_rate_limited", 429),
        ("content_policy_violation", "upstream_content_policy", 400),
        ("server_error", "upstream_error", 502),
    ],
)
@pytest.mark.parametrize("envelope", ["response", "event", "json"])
def test_response_errors_keep_classification_and_redact_details(
    upstream_code, expected_code, expected_status, envelope
):
    error = {"code": upstream_code, "message": "provider detail sk-secret123456"}
    with pytest.raises(APIError) as info:
        if envelope == "response":
            _stream([{"type": "response.failed", "response": {"status": "failed", "error": error}}])
        elif envelope == "event":
            _stream([{"type": "error", **error}])
        else:
            normalize_responses_image_payload({"status": "failed", "error": error})

    assert info.value.code == expected_code
    assert info.value.status == expected_status
    assert "sk-secret123456" not in info.value.details
    assert "provider detail" not in info.value.message
    assert upstream_code in info.value.details


def test_json_error_without_failed_status_is_not_lost():
    with pytest.raises(APIError) as info:
        normalize_responses_image_payload({"error": {"code": "rate_limit_exceeded", "message": "limited"}})
    assert info.value.code == "upstream_rate_limited"


def test_long_error_message_does_not_hide_policy_classification():
    with pytest.raises(APIError) as info:
        normalize_responses_image_payload({"error": {"code": "moderation_blocked", "message": "x" * 5000}})
    assert info.value.code == "upstream_content_policy"
    assert len(info.value.details) <= 4000


def test_incomplete_reason_is_preserved_without_image_data():
    with pytest.raises(APIError) as info:
        normalize_responses_image_payload(
            {
                "id": "resp_cutoff",
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [{"type": "image_generation_call", "result": "secret-image-data"}],
            }
        )
    assert "max_output_tokens" in info.value.details
    assert "secret-image-data" not in info.value.details


def test_failure_is_not_overwritten_by_later_response_event():
    with pytest.raises(APIError):
        _stream(
            [
                {"type": "response.failed", "response": {"status": "failed"}},
                {
                    "type": "response.completed",
                    "response": {"status": "completed", "output": [{"type": "image_generation_call", "result": "x"}]},
                },
            ]
        )


def test_failure_summary_is_warning_and_excludes_provider_message(caplog):
    with caplog.at_level(logging.INFO, logger="picgen.upstream.responses"), pytest.raises(APIError):
        _stream(
            [
                {"type": "response.image_generation_call.partial_image", "partial_image_b64": "preview"},
                {
                    "type": "response.failed",
                    "response": {
                        "id": "resp_failed",
                        "status": "failed",
                        "error": {"code": "server_error", "message": "private provider message"},
                    },
                },
            ]
        )
    record = next(record for record in caplog.records if record.getMessage() == "upstream_responses_stream_error")
    assert record.levelno == logging.WARNING
    assert record.fields["response_id"] == "resp_failed"
    assert record.fields["response_error_code"] == "server_error"
    assert "private provider message" not in str(record.fields)


def test_sse_event_field_supplies_missing_json_type():
    events = parse_sse_json_events('event: error\ndata: {"code":"rate_limit_exceeded","message":"limited"}\n\n')
    assert events[0]["type"] == "error"
    with pytest.raises(APIError) as info:
        _stream(events)
    assert info.value.code == "upstream_rate_limited"


def test_sse_event_field_does_not_leak_to_next_event():
    events = parse_sse_json_events('event: error\ndata: [DONE]\n\ndata: {"result":"image"}\n\n')
    assert "type" not in events[0]
    assert _stream(events)["data"][0]["b64_json"] == "image"


def test_partial_only_legacy_stream_is_preserved():
    payload = _stream([{"type": "response.image_generation_call.partial_image", "partial_image_b64": "preview"}])
    assert payload["data"][0]["b64_json"] == "preview"


def test_completed_empty_response_remains_available_for_no_image_handling():
    payload = _stream([{"type": "response.completed", "response": {"status": "completed", "output": []}}])
    assert payload["status"] == "completed"
    assert payload["output"] == []


def test_completed_multi_image_response_is_preserved():
    payload = _stream(
        [{
            "type": "response.completed",
            "response": {
                "status": "completed",
                "output": [
                    {"type": "image_generation_call", "result": "one"},
                    {"type": "image_generation_call", "result": "two"},
                ],
            },
        }]
    )
    assert [image["b64_json"] for image in payload["data"]] == ["one", "two"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("image_tool", [False, True])
async def test_http_200_failed_response_is_rejected_without_paid_retry(stream, image_tool):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if stream:
            return httpx.Response(
                200,
                text=(
                    'event: response.failed\n'
                    'data: {"response":{"status":"failed","error":{"code":"server_error"}}}\n\n'
                ),
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(200, json={"status": "failed", "error": {"code": "server_error"}})

    client = HttpxAsyncClient(max_retries=2, retry_backoff=0)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    payload = {"stream": stream, "input": "test"}
    if image_tool:
        payload["tools"] = [{"type": "image_generation"}]
    try:
        with pytest.raises(APIError) as info:
            await client.run_responses("https://upstream.test/responses", "sk-test", payload, "UA")
        assert info.value.code == "upstream_error"
        assert calls == 1
    finally:
        await client.aclose()


def test_raw_response_redacts_nested_credentials_and_removes_images():
    upstream = {
        "model": "image-model",
        "created": 123,
        "api_key": "not-an-openai-style-key",
        "stream_events": [{
            "error": {"authorization": "Bearer privatecredential", "password": 123456},
            "b64_json": "image-data",
            "image_url": "data:image/png;base64,inline-image",
            "text": "provider echoes sk-private123456",
        }],
        "url": "https://upstream.test/output?token=private-token&size=large",
    }
    compacted = compact_raw_response(upstream)
    assert compacted["model"] == "image-model"
    assert compacted["created"] == 123
    assert compacted["api_key"] == "***"
    event = compacted["stream_events"][0]
    assert event["error"] == {"authorization": "***", "password": "***"}
    assert event["b64_json"] == "[omitted 10 chars]"
    assert event["image_url"].startswith("[omitted data URL")
    assert event["text"] == "provider echoes sk-***"
    assert compacted["url"] == "https://upstream.test/output?token=***"
    assert upstream["api_key"] == "not-an-openai-style-key"


def test_raw_response_compaction_bounds_untrusted_nesting():
    upstream = {"password": "private-password"}
    for _ in range(1100):
        upstream = {"nested": [upstream]}
    compacted = compact_raw_response(upstream)
    assert len(str(compacted)) < 1000
    assert "private-password" not in str(compacted)


def test_raw_response_redacts_credential_used_as_field_name():
    assert compact_raw_response({"sk-private123456": "value"}) == {"sk-***": "***"}


@pytest.mark.parametrize("body", ["failed sk-private123456", '{"message": "failed sk-private123456"'])
def test_non_json_error_details_are_also_redacted(body):
    message, details = extract_error_message(body)
    assert "sk-private123456" not in message
    assert "sk-private123456" not in details


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["run_json", "run_responses"])
async def test_deep_http_200_json_is_classified_as_invalid_response(method):
    body = '{"nested":' * 10000 + '"sk-private123456"' + '}' * 10000
    client = HttpxAsyncClient(max_retries=0)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    )
    try:
        with pytest.raises(APIError) as info:
            await getattr(client, method)("https://upstream.test/generate", "sk-test", {}, "UA")
        assert info.value.code == "upstream_invalid_response"
        assert info.value.status == 502
        assert "sk-private123456" not in info.value.details
    finally:
        await client.aclose()


def test_deep_sse_json_rejects_stream_even_after_preview():
    deep_json = '{"nested":' * 10000 + '0' + '}' * 10000
    body = 'data: {"partial_image_b64":"preview"}\n\n' + f'data: {deep_json}\n\n'
    with pytest.raises(APIError) as info:
        parse_sse_json_events(body)
    assert info.value.status == 502
    assert info.value.code == "upstream_invalid_response"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ['{"status":"failed","error":{"code":"server_error"}}', '{invalid'])
async def test_failed_json_response_does_not_log_success(body, caplog):
    client = HttpxAsyncClient(max_retries=0)
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    )
    try:
        with caplog.at_level(logging.INFO, logger="picgen.upstream.client"), pytest.raises(APIError):
            await client.run_responses("https://upstream.test/responses", "sk-test", {}, "UA")
        assert all(record.getMessage() != "upstream_responses_ok" for record in caplog.records)
    finally:
        await client.aclose()

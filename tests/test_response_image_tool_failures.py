from __future__ import annotations

import json
import logging

import httpx
import pytest

from picgen.errors import APIError
from picgen.upstream.client import HttpxAsyncClient
from picgen.upstream.errors import sanitize_image_diagnostics
from picgen.upstream.payload import normalize_responses_image_payload
from picgen.upstream.responses import stream_events_to_image_payload


def _failed_call():
    return {
        "type": "image_generation_call", "id": "img_failed", "status": "failed",
        "error": {"code": "rate_limit_exceeded", "message": "limited sk-private123456"},
    }


def _completed(*items):
    return {"id": "resp_test", "status": "completed", "output": list(items)}


def _stream(events, *, expect_image=True):
    return stream_events_to_image_payload(events, url="https://mock.invalid", started_at=0, expect_image=expect_image)


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("as_event_item", [False, True])
def test_nested_image_error_is_not_hidden_by_completed_response_or_preview(preview, as_event_item):
    events = (
        [{"type": "response.image_generation_call.partial_image", "partial_image_b64": "preview"}] if preview else []
    )
    if as_event_item:
        events.append({"type": "response.output_item.done", "item": _failed_call()})
        response = _completed()
    else:
        response = _completed(_failed_call())
    events.append({"type": "response.completed", "response": response})
    with pytest.raises(APIError) as info:
        _stream(events)
    assert info.value.code == "upstream_rate_limited"
    assert "sk-private123456" not in info.value.details
    assert "img_failed" in info.value.details


def test_json_nested_image_error_keeps_classification():
    with pytest.raises(APIError) as info:
        normalize_responses_image_payload(_completed(_failed_call()))
    assert info.value.code == "upstream_rate_limited"


def test_mixed_complete_and_failed_images_keep_real_success_and_safe_diagnostics():
    good = {"type": "image_generation_call", "id": "img_ok", "status": "completed", "result": "real-image"}
    bad = {**_failed_call(), "result": "failed-preview"}
    events = [
        {"type": "response.output_item.done", "item": bad},
        {"type": "response.completed", "response": _completed(bad, good)},
    ]
    result = _stream(events)
    assert [image["b64_json"] for image in result["data"]] == ["real-image"]
    diagnostics = result["image_diagnostics"]
    assert diagnostics["result_image_count"] == 1
    assert diagnostics["image_calls"][0]["error"]["code"] == "rate_limit_exceeded"
    assert "sk-private123456" not in json.dumps(diagnostics)
    assert "failed-preview" not in json.dumps(diagnostics)


def test_failure_event_does_not_preempt_a_later_complete_candidate():
    events = [
        {"type": "response.image_generation_call.failed", "item_id": "img_failed", "error": {"code": "server_error"}},
        {"type": "response.output_item.done", "item": {
            "type": "image_generation_call", "id": "img_ok", "status": "completed", "result": "real-image",
        }},
        {"type": "response.completed", "response": _completed()},
    ]
    assert _stream(events)["data"][0]["b64_json"] == "real-image"


@pytest.mark.parametrize("expect_image", [False, True])
def test_no_image_logging_distinguishes_text_requests(expect_image, caplog):
    response = _completed({"type": "message", "content": [{"type": "output_text", "text": "private customer text"}]})
    with caplog.at_level(logging.INFO):
        result = _stream([{"type": "response.completed", "response": response}], expect_image=expect_image)
    event_name = "upstream_responses_stream_no_image" if expect_image else "upstream_responses_stream_ok"
    record = next(record for record in caplog.records if record.getMessage() == event_name)
    assert record.levelno == (logging.WARNING if expect_image else logging.INFO)
    assert "private customer text" not in str(record.fields)
    assert result["output"] == response["output"]


def test_typed_refusal_is_diagnosed_without_guessing_content_policy():
    response = _completed({"type": "message", "content": [{"type": "refusal", "refusal": "private refusal text"}]})
    result = normalize_responses_image_payload(response, fallback_b64="preview")
    assert result["data"] == []
    assert result["image_diagnostics"]["refusal_count"] == 1
    assert result["image_diagnostics"]["reason"] == "response_refusal"
    assert "private refusal text" not in json.dumps(result["image_diagnostics"])


def test_plain_text_does_not_imply_policy_rejection():
    response = _completed({"type": "message", "content": [{"type": "output_text", "text": "content policy discussed"}]})
    result = normalize_responses_image_payload(response)
    assert result["image_diagnostics"]["refusal_count"] == 0
    assert result["image_diagnostics"]["reason"] == "no_image_output"


def test_completed_response_with_unfinished_tool_has_diagnostic():
    result = _stream([
        {"type": "response.image_generation_call.generating", "item_id": "img_pending"},
        {"type": "response.completed", "response": _completed()},
    ])
    assert result["image_diagnostics"]["reason"] == "image_tool_unfinished"


def test_json_no_image_diagnostics_are_logged_without_text(caplog):
    with caplog.at_level(logging.INFO):
        result = normalize_responses_image_payload(_completed({"type": "message", "content": [
            {"type": "output_text", "text": "private text sk-private123456"},
        ]}))
    record = next(record for record in caplog.records if record.getMessage() == "upstream_responses_no_image")
    assert "private text" not in str(record.fields)
    assert result["image_diagnostics"]["text_chars"] > 0


def test_refusal_delta_events_remain_diagnosable_when_terminal_output_omits_them():
    result = _stream([
        {"type": "response.refusal.delta", "item_id": "msg_refusal", "delta": "private text"},
        {"type": "response.refusal.done", "item_id": "msg_refusal", "refusal": "private text"},
        {"type": "response.completed", "response": _completed()},
    ])
    assert result["image_diagnostics"]["refusal_count"] == 1
    assert result["image_diagnostics"]["reason"] == "response_refusal"


def test_upstream_cannot_inject_trusted_image_diagnostics():
    result = normalize_responses_image_payload({
        **_completed(), "image_diagnostics": {"reason": "content_policy", "private": "do not expose"},
    })
    assert result["image_diagnostics"]["reason"] == "no_image_output"
    assert "private" not in result["image_diagnostics"]


def test_completed_unfinished_tool_cannot_promote_preview_to_final():
    result = _stream([
        {"type": "response.image_generation_call.generating", "item_id": "img_pending"},
        {"type": "response.image_generation_call.partial_image", "partial_image_b64": "preview"},
        {"type": "response.completed", "response": _completed()},
    ])
    assert not result.get("data")
    assert result["image_diagnostics"]["reason"] == "image_tool_unfinished"


def test_early_image_tool_status_is_preserved_past_tail_event_limit():
    result = _stream([
        {"type": "response.output_item.added", "item": {
            "id": "img_pending", "type": "image_generation_call", "status": "in_progress",
        }},
        *[{"type": "response.output_text.delta", "delta": "private text"} for _ in range(30)],
        {"type": "response.completed", "response": _completed()},
    ])
    assert len(result["stream_events"]) == 20
    assert result["image_diagnostics"]["reason"] == "image_tool_unfinished"
    assert result["image_diagnostics"]["image_calls"][0]["id"] == "img_pending"


def test_diagnostic_sanitizer_drops_unknown_or_untyped_content():
    assert sanitize_image_diagnostics(None) == {}
    assert sanitize_image_diagnostics({"private": "private prompt"}) == {}
    safe = sanitize_image_diagnostics({
        "reason": "private prompt", "response_id": {"private": "prompt"},
        "image_call_count": "private text", "text_chars": -3,
        "image_calls": [{
            "id": "img_ok", "status": "failed", "result": "base64-secret",
            "error": {"code": "server_error", "message": "private prompt", "param": "sk-private123456"},
        }] * 30,
    })
    assert safe["reason"] == "no_image_output"
    assert safe["response_id"] == ""
    assert safe["image_call_count"] == 0
    assert safe["text_chars"] == 0
    assert len(safe["image_calls"]) == 20
    assert "private" not in json.dumps(safe)
    assert "base64-secret" not in json.dumps(safe)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image_failed", "image_empty", "text"])
async def test_json_image_failure_does_not_log_success_or_retry(kind, caplog):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        response = _completed(_failed_call()) if kind == "image_failed" else _completed()
        return httpx.Response(200, json=response)

    client = HttpxAsyncClient(max_retries=2)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request_payload = {} if kind == "text" else {"tools": [{"type": "image_generation"}]}
    try:
        with caplog.at_level(logging.INFO):
            if kind == "image_failed":
                with pytest.raises(APIError):
                    await client.run_responses("https://mock.invalid", "local-test", request_payload, "Test")
            else:
                await client.run_responses("https://mock.invalid", "local-test", request_payload, "Test")
        event_names = [record.getMessage() for record in caplog.records]
        assert ("upstream_responses_ok" in event_names) == (kind == "text")
        assert ("upstream_responses_no_image" in event_names) == (kind == "image_empty")
        assert calls == 1
    finally:
        await client.aclose()


def test_terminal_image_summaries_keep_all_earlier_completed_results():
    events = [
        {"type": "response.output_item.done", "item": {
            "type": "image_generation_call", "id": f"img_{index}", "status": "completed", "result": f"image_{index}",
        }} for index in range(2)
    ]
    terminal = _completed(*[
        {"type": "image_generation_call", "id": f"img_{index}", "status": "completed"} for index in range(2)
    ])
    result = _stream([*events, {"type": "response.completed", "response": terminal}])
    assert [item["b64_json"] for item in result["data"]] == ["image_0", "image_1"]
    assert all("result" not in item for item in terminal["output"])


def test_explicit_terminal_failure_overrides_earlier_completed_result():
    with pytest.raises(APIError) as info:
        _stream([
            {"type": "response.output_item.done", "item": {
                "type": "image_generation_call", "id": "img_failed", "status": "completed", "result": "earlier-image",
            }},
            {"type": "response.completed", "response": _completed(_failed_call())},
        ])
    assert info.value.code == "upstream_rate_limited"


def test_nested_error_message_classifies_without_exposing_private_prompt():
    with pytest.raises(APIError) as info:
        normalize_responses_image_payload(_completed({
            "type": "image_generation_call", "id": "img_private", "status": "failed",
            "error": {"message": "content policy: private customer travel description"},
        }))
    assert info.value.code == "upstream_content_policy"
    assert "img_private" in info.value.details
    assert "private customer travel description" not in info.value.details
    assert "message" not in json.loads(info.value.details)["image_calls"][0]["error"]


@pytest.mark.parametrize("stage", ["input", "output"])
def test_real_failed_image_call_reports_moderation_stage_after_empty_terminal_output(stage, caplog):
    events = [
        {"type": "response.output_item.added", "item": {
            "type": "image_generation_call", "id": "img_moderated", "status": "failed",
            "error": {
                "type": "image_generation_user_error", "code": "moderation_blocked",
                "message": "private provider safety system message",
                "moderation_details": {"categories": ["private category text"], "moderation_stage": stage},
                "param": None,
            },
        }},
        *[{"type": "response.output_text.delta", "delta": "private response text"} for _ in range(30)],
        {"type": "response.completed", "response": _completed()},
    ]
    with caplog.at_level(logging.INFO), pytest.raises(APIError) as info:
        _stream(events)
    assert info.value.code == "upstream_content_policy"
    error = json.loads(info.value.details)["image_calls"][0]["error"]
    assert error["moderation_stage"] == stage
    assert "categories" not in error
    assert "private" not in info.value.details
    if stage == "output":
        assert "生成结果未通过上游安全检查" in info.value.message
        assert "提示词没有通过" not in info.value.message
    else:
        assert "提示词没有通过上游内容审核" in info.value.message
    record = next(record for record in caplog.records if record.getMessage() == "upstream_responses_stream_error")
    assert record.fields["image_moderation_stages"] == [stage]
    assert "private" not in str(record.fields)


@pytest.mark.parametrize("stage", ["private stage text", {"output": "private"}, None])
def test_unrecognized_moderation_stage_is_not_exposed(stage):
    safe = sanitize_image_diagnostics({"image_calls": [{"error": {"moderation_stage": stage}}]})
    assert "moderation_stage" not in safe["image_calls"][0]["error"]


def test_completed_without_final_image_does_not_promote_preview():
    result = _stream([
        {"type": "response.image_generation_call.partial_image", "partial_image_b64": "preview-only"},
        {"type": "response.image_generation_call.completed", "item_id": "img_done"},
        {"type": "response.completed", "response": _completed()},
    ])
    assert not result.get("data")
    assert result["image_diagnostics"]["result_image_count"] == 0


@pytest.mark.parametrize("image_key", ["b64_json", "image_b64"])
def test_completed_image_alias_survives_empty_terminal_summary(image_key):
    result = _stream([
        {"type": "response.image_generation_call.partial_image", "partial_image_b64": "preview-only"},
        {"type": "response.image_generation_call.completed", "item_id": "img_done", image_key: "final-image"},
        {"type": "response.completed", "response": _completed()},
    ])
    assert result["data"][0]["b64_json"] == "final-image"

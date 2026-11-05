from __future__ import annotations

import json

from picgen.errors import OUTPUT_IMAGE_POLICY_MESSAGE, APIError
from picgen.main import _base_operational_message


def test_output_moderation_api_and_history_describe_generated_result(make_client, settings_factory):
    client, fake, _ = make_client(settings=settings_factory(auth_enabled=True, default_api_key="sk-test"))
    registered = client.post("/api/auth/register", json={"username": "alice", "password": "secure test password"})
    assert registered.status_code == 200
    fake.run_json.side_effect = APIError(
        400,
        OUTPUT_IMAGE_POLICY_MESSAGE,
        json.dumps({"response_id": "resp_output_blocked", "moderation_stage": "output"}),
        code="upstream_content_policy",
    )

    response = client.post("/api/generate", json={
        "prompt": "生成一张旅行海报", "model": "gpt-image-2", "size": "1024x1024",
    }, headers={"X-Request-ID": "output-moderation-request"})

    assert response.status_code == 400
    assert response.json()["code"] == "upstream_content_policy"
    assert response.json()["error"] == OUTPUT_IMAGE_POLICY_MESSAGE
    assert "提示词" not in response.json()["error"]
    assert response.json()["request_id"] == "output-moderation-request"
    assert json.loads(response.json()["details"])["moderation_stage"] == "output"
    job = client.get("/api/jobs?limit=1").json()["jobs"][0]
    assert job["status"] == "failed"
    assert job["error_code"] == "upstream_content_policy"
    assert job["error_message"] == OUTPUT_IMAGE_POLICY_MESSAGE
    assert fake.run_json.await_count == 1
    fake.run_responses.assert_not_awaited()


def test_policy_message_does_not_trust_arbitrary_provider_text():
    message = _base_operational_message(APIError(400, "PRIVATE_PROVIDER_REFUSAL", code="upstream_content_policy"))
    assert "PRIVATE_PROVIDER_REFUSAL" not in message
    assert "提示词" in message

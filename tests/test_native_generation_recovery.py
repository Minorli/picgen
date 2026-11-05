from __future__ import annotations

import base64
from io import BytesIO

import pytest
from PIL import Image

from picgen.routes import _resolve_image_job_transport


@pytest.mark.parametrize(
    ("enabled", "mode", "has_input", "preferred", "expected"),
    [
        (False, "generate", False, "auto", "responses-image"),
        (True, "generate", False, "auto", "images-generate"),
        (True, "generate", False, "images", "images-generate"),
        (True, "generate", False, "responses", "responses-image"),
        (True, "generate", True, "auto", "responses-image"),
        (True, "reference", True, "auto", "responses-image"),
        (True, "edit", True, "auto", "responses-image"),
        (True, "variant", True, "auto", "responses-image"),
        (True, "itinerary", False, "auto", "responses-image"),
    ],
)
def test_native_generation_preference_is_narrow(enabled, mode, has_input, preferred, expected):
    assert _resolve_image_job_transport(
        size="1088x2240", mode=mode, has_input=has_input,
        preferred_transport=preferred, prefer_images_for_generation=enabled,
    ) == expected


def test_native_generation_preference_defaults_off(settings_factory):
    assert settings_factory().prefer_images_for_generation is False


def test_native_recovery_preserves_prompt_quality_size_and_job_model(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True, default_api_key="local-test", prefer_images_for_generation=True,
        default_model="native-image-model", default_responses_model="gpt-6-astra",
        default_responses_reasoning_effort="xhigh",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post("/api/auth/register", json={
        "username": "native-user", "password": "correct horse battery",
    }).status_code == 200
    output = BytesIO()
    Image.new("RGB", (875, 1798), (50, 100, 150)).save(output, format="PNG")
    fake.run_json.return_value = {"data": [{"b64_json": base64.b64encode(output.getvalue()).decode("ascii")}]}
    prompt = "制作旅行海报，保留全部标题和行程文字"
    response = client.post("/api/image-jobs", json={"prompt": prompt, "size": "1088x2240", "mode": "generate"})
    assert response.status_code == 200
    result = response.json()
    sent = fake.run_json.await_args.args[2]
    assert sent["model"] == "native-image-model"
    assert sent["size"] == "1088x2240"
    assert sent["quality"] == "high"
    assert "竖版长图" in sent["prompt"]
    assert "1088:2240" in sent["prompt"]
    assert prompt in sent["prompt"]
    assert result["prompt"] == prompt
    assert result["effective_prompt"] == prompt
    assert result["saved_image_width"] == 1088
    assert result["saved_image_height"] == 2240
    assert result["image_size_normalized"] is True
    assert result["transport"] == "images-generate"
    assert result["reasoning_effort"] == ""
    fake.run_json.assert_awaited_once()
    fake.run_responses.assert_not_awaited()
    job = client.get("/api/jobs?limit=1").json()["jobs"][0]
    assert job["model"] == "native-image-model"
    assert job["transport"] == "images-generate"


@pytest.mark.parametrize("size,mode", [("auto", "generate"), ("1792x1792", "itinerary")])
def test_non_strict_generation_does_not_add_canvas_prompt(make_client, settings_factory, size, mode):
    client, fake, _ = make_client(settings=settings_factory(default_api_key="local-test"))
    output = BytesIO()
    Image.new("RGB", (16, 16)).save(output, format="PNG")
    fake.run_json.return_value = {"data": [{"b64_json": base64.b64encode(output.getvalue()).decode("ascii")}]}
    response = client.post("/api/generate", json={"prompt": "a lake", "size": size, "mode": mode})
    assert response.status_code == 200
    assert "画布尺寸要求" not in fake.run_json.await_args.args[2]["prompt"]

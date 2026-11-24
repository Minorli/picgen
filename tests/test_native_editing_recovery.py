from __future__ import annotations

import base64
from io import BytesIO

import pytest
from PIL import Image

from picgen.routes import _resolve_image_job_transport


def _png(image):
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _file(data, name):
    return {"name": name, "type": "image/png", "data_url": "data:image/png;base64," + base64.b64encode(data).decode()}


@pytest.mark.parametrize("mode", ["reference", "variant", "edit", "generate"])
def test_native_editing_preference_only_changes_input_requests(mode):
    assert _resolve_image_job_transport(size="1088x2240", mode=mode, has_input=True) == "responses-image"
    assert _resolve_image_job_transport(
        size="1088x2240", mode=mode, has_input=True, prefer_images_for_editing=True,
    ) == "images-edit"
    assert _resolve_image_job_transport(
        size="1088x2240", mode=mode, has_input=True, prefer_images_for_editing=True, preferred_transport="responses",
    ) == "responses-image"
    assert _resolve_image_job_transport(
        size="1088x2240", mode=mode, has_input=False, prefer_images_for_editing=True,
    ) == "responses-image"


def test_native_editing_preference_defaults_off(settings_factory):
    assert settings_factory().prefer_images_for_editing is False


def test_native_masked_edit_preserves_source_mask_pixels_and_job_model(make_client, settings_factory):
    settings = settings_factory(
        auth_enabled=True, default_api_key="local-test", prefer_images_for_editing=True,
        default_model="native-image-model", default_responses_model="gpt-6-astra",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post("/api/auth/register", json={
        "username": "native-editor", "password": "correct horse battery",
    }).status_code == 200
    source = _png(Image.new("RGBA", (32, 64), (220, 20, 20, 255)))
    mask_image = Image.new("RGBA", (32, 64), (255, 255, 255, 255))
    mask_image.putpixel((5, 5), (255, 255, 255, 0))
    mask = _png(mask_image)
    generated = _png(Image.new("RGBA", (32, 64), (10, 80, 220, 255)))
    fake.run_multipart.return_value = {"data": [{"b64_json": base64.b64encode(generated).decode()}]}
    prompt = "只修改蒙版透明区域"
    response = client.post("/api/image-jobs", json={
        "mode": "edit", "prompt": prompt, "size": "32x64",
        "image": _file(source, "source.png"), "mask": _file(mask, "mask.png"),
    })
    assert response.status_code == 200
    result = response.json()
    args = fake.run_multipart.await_args.args
    assert args[2]["model"] == "native-image-model"
    assert args[2]["size"] == "32x64"
    assert args[2]["quality"] == "high"
    assert "竖版长图" in args[2]["prompt"] and "32:64" in args[2]["prompt"]
    assert args[3][0]["data"] == source
    assert args[3][1]["data"] == mask
    assert args[3][1]["field_name"] == "mask"
    assert result["prompt"] == prompt
    assert result["transport"] == "images-edit"
    with Image.open(result["saved_image_path"]) as image:
        assert image.convert("RGBA").getpixel((0, 0)) == (220, 20, 20, 255)
        assert image.convert("RGBA").getpixel((5, 5)) == (10, 80, 220, 255)
    fake.run_multipart.assert_awaited_once()
    fake.run_responses.assert_not_awaited()
    fake.run_file_upload.assert_not_awaited()
    job = client.get("/api/jobs?limit=1").json()["jobs"][0]
    assert job["model"] == "native-image-model"
    assert job["transport"] == "images-edit"


def test_native_reference_keeps_wrong_aspect_original_without_retry(make_client, settings_factory):
    client, fake, _ = make_client(settings=settings_factory(
        default_api_key="local-test", prefer_images_for_editing=True,
    ))
    source = _png(Image.new("RGB", (32, 64)))
    generated = _png(Image.new("RGB", (1199, 1312)))
    fake.run_multipart.return_value = {"data": [{"b64_json": base64.b64encode(generated).decode()}]}
    response = client.post("/api/image-jobs", json={
        "mode": "reference", "prompt": "a lake", "size": "1088x2240", "image": _file(source, "source.png"),
    })
    assert response.status_code == 200
    result = response.json()
    assert result["saved_image_width"] == 1199
    assert result["saved_image_height"] == 1312
    assert result["size_mismatch"] is True
    assert result["requested_size"] == "1088x2240"
    fake.run_multipart.assert_awaited_once()
    fake.run_responses.assert_not_awaited()

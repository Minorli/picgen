from __future__ import annotations

import base64
import sqlite3
from io import BytesIO

import pytest
from PIL import Image

TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def _png_b64(width: int, height: int) -> str:
    output = BytesIO()
    Image.new("RGB", (width, height), (60, 120, 220)).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def _image_payload() -> dict[str, str]:
    return {
        "name": "source.png",
        "type": "image/png",
        "data_url": f"data:image/png;base64,{TINY_PNG_B64}",
    }


@pytest.mark.parametrize(
    ("size", "mode", "has_input", "preferred_transport", "expected"),
    [
        ("auto", "generate", False, "auto", "images-generate"),
        ("1024x1024", "generate", False, "auto", "images-generate"),
        ("1024x1536", "generate", False, "auto", "images-generate"),
        ("1536x1024", "generate", False, "auto", "images-generate"),
        ("1024x1024", "reference", True, "auto", "images-edit"),
        ("1088x2240", "generate", False, "auto", "responses-image"),
        ("3840x2160", "edit", True, "images", "responses-image"),
        ("1024x1024", "generate", False, "responses", "responses-image"),
    ],
)
def test_image_job_transport_policy(
    size: str,
    mode: str,
    has_input: bool,
    preferred_transport: str,
    expected: str,
) -> None:
    from picgen.routes import _resolve_image_job_transport

    assert _resolve_image_job_transport(
        size=size,
        mode=mode,
        has_input=has_input,
        preferred_transport=preferred_transport,
    ) == expected


def test_image_job_routes_native_text_generation_to_images(make_client, settings_factory) -> None:
    settings = settings_factory(default_api_key="sk-server", default_size="1024x1024")
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {"data": [{"b64_json": _png_b64(1024, 1024)}], "created": 1}

    response = client.post(
        "/api/image-jobs",
        json={"prompt": "生成方形海报", "mode": "generate", "size": "1024x1024"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transport"] == "images-generate"
    assert payload["model"] == "gpt-image-2"
    assert payload["reasoning_effort"] == ""
    fake.run_json.assert_awaited_once()
    fake.run_multipart.assert_not_awaited()
    fake.run_responses.assert_not_awaited()


def test_image_job_routes_native_reference_to_images_edit(make_client, settings_factory) -> None:
    settings = settings_factory(default_api_key="sk-server")
    client, fake, _ = make_client(settings=settings)
    fake.run_multipart.return_value = {"data": [{"b64_json": _png_b64(1024, 1024)}], "created": 1}

    response = client.post(
        "/api/image-jobs",
        json={
            "prompt": "保留主体并调整光线",
            "mode": "reference",
            "size": "1024x1024",
            "image": _image_payload(),
            "images": [_image_payload()],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transport"] == "images-edit"
    assert payload["model"] == "gpt-image-2"
    fake.run_multipart.assert_awaited_once()
    fake.run_json.assert_not_awaited()
    fake.run_responses.assert_not_awaited()


def test_image_job_routes_six_person_size_to_responses(make_client, settings_factory) -> None:
    settings = settings_factory(default_api_key="sk-server")
    client, fake, _ = make_client(settings=settings)
    fake.run_responses.return_value = {
        "data": [{"b64_json": _png_b64(1088, 2240)}],
        "created": 1,
    }

    response = client.post(
        "/api/image-jobs",
        json={"prompt": "生成六人游长海报", "mode": "generate", "size": "1088x2240"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transport"] == "responses-image"
    assert payload["model"] == "gpt-5.6-sol"
    assert payload["reasoning_effort"] == "max"
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["model"] == "gpt-5.6-sol"
    assert upstream_payload["reasoning"] == {"effort": "max"}
    fake.run_json.assert_not_awaited()
    fake.run_multipart.assert_not_awaited()


def test_image_job_routes_six_person_reference_to_responses(make_client, settings_factory) -> None:
    settings = settings_factory(default_api_key="sk-server")
    client, fake, _ = make_client(settings=settings)
    fake.run_file_upload.return_value = {"id": "file-reference"}
    fake.run_responses.return_value = {
        "data": [{"b64_json": _png_b64(1088, 2240)}],
        "created": 1,
    }

    response = client.post(
        "/api/image-jobs",
        json={
            "prompt": "六人游长海报参考图",
            "mode": "reference",
            "size": "1088x2240",
            "image": _image_payload(),
        },
    )

    assert response.status_code == 200
    assert response.json()["transport"] == "responses-image"
    fake.run_file_upload.assert_awaited_once()
    fake.run_responses.assert_awaited_once()
    fake.run_multipart.assert_not_awaited()


@pytest.mark.parametrize("mode", ["edit", "reference", "variant"])
def test_image_job_rejects_input_modes_without_an_image(make_client, settings_factory, mode: str) -> None:
    settings = settings_factory(default_api_key="sk-server")
    client, fake, _ = make_client(settings=settings)

    response = client.post(
        "/api/image-jobs",
        json={"prompt": "修改图片", "mode": mode, "size": "1024x1024"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    fake.run_json.assert_not_awaited()
    fake.run_multipart.assert_not_awaited()
    fake.run_responses.assert_not_awaited()


def test_regular_user_cannot_override_image_execution(make_client, settings_factory) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
    )
    client, fake, _ = make_client(settings=settings)
    register = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register.status_code == 200

    response = client.post(
        "/api/image-jobs",
        json={
            "prompt": "越权测试",
            "mode": "generate",
            "size": "1024x1024",
            "advanced": {
                "preferred_transport": "responses",
                "responses_url": "https://override.example/v1/responses",
                "responses_model": "custom-model",
                "reasoning_effort": "low",
            },
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    fake.run_json.assert_not_awaited()
    fake.run_responses.assert_not_awaited()


def test_admin_can_override_responses_execution(make_client, settings_factory) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
    )
    client, fake, _ = make_client(settings=settings)
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery admin"},
    )
    assert login.status_code == 200
    fake.run_responses.return_value = {
        "data": [{"b64_json": _png_b64(1024, 1024)}],
        "created": 1,
    }

    response = client.post(
        "/api/image-jobs",
        json={
            "prompt": "管理员强制 Responses",
            "mode": "generate",
            "size": "1024x1024",
            "advanced": {
                "api_key": "sk-admin",
                "responses_url": "https://admin.example/v1/responses",
                "responses_model": "gpt-5.6-sol",
                "preferred_transport": "responses",
                "reasoning_effort": "low",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transport"] == "responses-image"
    assert payload["reasoning_effort"] == "low"
    upstream_args = fake.run_responses.await_args.args
    assert upstream_args[0] == "https://admin.example/v1/responses"
    assert upstream_args[1] == "sk-admin"
    assert upstream_args[2]["reasoning"] == {"effort": "low"}


def test_admin_can_prefer_images_and_override_images_model(make_client, settings_factory) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery admin"},
    ).status_code == 200
    fake.run_json.return_value = {
        "data": [{"b64_json": _png_b64(1024, 1024)}],
        "created": 1,
    }

    response = client.post(
        "/api/image-jobs",
        json={
            "prompt": "管理员 Images 覆盖",
            "mode": "generate",
            "size": "1024x1024",
            "advanced": {
                "images_model": "custom-images-model",
                "preferred_transport": "images",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["transport"] == "images-generate"
    assert fake.run_json.await_args.args[2]["model"] == "custom-images-model"
    fake.run_responses.assert_not_awaited()


def test_custom_responses_model_does_not_receive_unsupported_reasoning(
    make_client, settings_factory
) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery admin"},
    ).status_code == 200
    fake.run_responses.return_value = {
        "data": [{"b64_json": _png_b64(1024, 1024)}],
        "created": 1,
    }

    response = client.post(
        "/api/image-jobs",
        json={
            "prompt": "自定义 Responses 模型",
            "mode": "generate",
            "size": "1024x1024",
            "advanced": {
                "responses_model": "custom-responses-model",
                "preferred_transport": "responses",
                "reasoning_effort": "ultra",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["reasoning_effort"] == ""
    upstream_payload = fake.run_responses.await_args.args[2]
    assert upstream_payload["model"] == "custom-responses-model"
    assert "reasoning" not in upstream_payload


def test_regular_user_old_generate_endpoint_uses_server_execution_settings(
    make_client, settings_factory
) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
        default_generate_url="https://server.example/v1/images/generations",
        default_model="gpt-image-2",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    ).status_code == 200
    fake.run_json.return_value = {
        "data": [{"b64_json": _png_b64(1024, 1024)}],
        "created": 1,
    }

    response = client.post(
        "/api/generate",
        json={
            "prompt": "旧页面兼容生成",
            "size": "1024x1024",
            "api_key": "sk-browser",
            "endpoint_url": "https://override.example/v1/images/generations",
            "model": "override-model",
        },
    )

    assert response.status_code == 200
    upstream_args = fake.run_json.await_args.args
    assert upstream_args[0] == "https://server.example/v1/images/generations"
    assert upstream_args[1] == "sk-server"
    assert upstream_args[2]["model"] == "gpt-image-2"


def test_regular_user_old_responses_endpoint_uses_server_model_and_reasoning(
    make_client, settings_factory
) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
        default_responses_url="https://server.example/v1/responses",
        default_responses_model="gpt-5.6-sol",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    ).status_code == 200
    fake.run_responses.return_value = {
        "data": [{"b64_json": _png_b64(1088, 2240)}],
        "created": 1,
    }

    response = client.post(
        "/api/responses-image",
        json={
            "prompt": "旧页面兼容精确尺寸",
            "size": "1088x2240",
            "api_key": "sk-browser",
            "endpoint_url": "https://override.example/v1/responses",
            "model": "override-model",
            "reasoning_effort": "low",
        },
    )

    assert response.status_code == 200
    upstream_args = fake.run_responses.await_args.args
    assert upstream_args[0] == "https://server.example/v1/responses"
    assert upstream_args[1] == "sk-server"
    assert upstream_args[2]["model"] == "gpt-5.6-sol"
    assert upstream_args[2]["reasoning"] == {"effort": "max"}


@pytest.mark.parametrize(
    ("path", "extra_payload"),
    [
        ("/api/copyright-risk", {}),
        (
            "/api/text-fidelity",
            {"text_contract": {"required": ["标题"], "forbidden": []}},
        ),
    ],
)
def test_regular_user_review_endpoints_use_server_execution_settings(
    make_client,
    settings_factory,
    path: str,
    extra_payload: dict[str, object],
) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
        default_responses_url="https://server.example/v1/responses",
        default_responses_model="gpt-5.6-sol",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    ).status_code == 200
    fake.run_responses.return_value = {"output_text": "结论：通过\n风险等级：低"}

    response = client.post(
        path,
        json={
            "prompt": "检查当前图片",
            "api_key": "sk-attacker",
            "endpoint_url": "https://attacker.example/collect",
            "model": "attacker-model",
            "images": [_image_payload()],
            **extra_payload,
        },
    )

    assert response.status_code == 200
    upstream_args = fake.run_responses.await_args.args
    assert upstream_args[0] == "https://server.example/v1/responses"
    assert upstream_args[1] == "sk-server"
    assert upstream_args[2]["model"] == "gpt-5.6-sol"
    assert upstream_args[2]["reasoning"] == {"effort": "max"}


def test_auth_disabled_does_not_allow_execution_overrides_by_default(
    make_client, settings_factory
) -> None:
    settings = settings_factory(
        auth_enabled=False,
        allow_anonymous_execution_overrides=False,
        default_api_key="sk-server",
        default_generate_url="https://server.example/v1/images/generations",
        default_model="gpt-image-2",
    )
    client, fake, _ = make_client(settings=settings)
    fake.run_json.return_value = {
        "data": [{"b64_json": _png_b64(1024, 1024)}],
        "created": 1,
    }

    response = client.post(
        "/api/generate",
        json={
            "prompt": "匿名部署覆盖测试",
            "size": "1024x1024",
            "api_key": "sk-attacker",
            "endpoint_url": "https://attacker.example/collect",
            "model": "attacker-model",
        },
    )

    assert response.status_code == 200
    upstream_args = fake.run_json.await_args.args
    assert upstream_args[0] == "https://server.example/v1/images/generations"
    assert upstream_args[1] == "sk-server"
    assert upstream_args[2]["model"] == "gpt-image-2"


def test_admin_custom_endpoint_requires_an_explicit_api_key(make_client, settings_factory) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery admin"},
    ).status_code == 200

    response = client.post(
        "/api/image-jobs",
        json={
            "prompt": "自定义上游必须显式提供 Key",
            "mode": "generate",
            "size": "1024x1024",
            "advanced": {
                "responses_url": "https://custom.example/v1/responses",
                "preferred_transport": "responses",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"
    fake.run_responses.assert_not_awaited()


def test_custom_responses_key_is_not_sent_to_default_images_endpoint(
    make_client, settings_factory
) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
        default_generate_url="https://images.example/v1/images/generations",
        default_responses_url="https://responses.example/v1/responses",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery admin"},
    ).status_code == 200
    fake.run_json.return_value = {
        "data": [{"b64_json": _png_b64(1024, 1024)}],
        "created": 1,
    }

    response = client.post(
        "/api/image-jobs",
        json={
            "prompt": "自动路由不能串用提供者 Key",
            "mode": "generate",
            "size": "1024x1024",
            "advanced": {
                "api_key": "sk-custom-responses",
                "responses_url": "https://custom.example/v1/responses",
                "preferred_transport": "auto",
            },
        },
    )

    assert response.status_code == 200
    assert fake.run_json.await_args.args[0] == "https://images.example/v1/images/generations"
    assert fake.run_json.await_args.args[1] == "sk-server"


def test_one_advanced_key_cannot_cover_custom_endpoints_on_different_origins(
    make_client, settings_factory
) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery admin"},
    ).status_code == 200

    response = client.post(
        "/api/image-jobs",
        json={
            "prompt": "不同提供者不能共用一个 Key",
            "mode": "generate",
            "size": "1024x1024",
            "advanced": {
                "api_key": "sk-one-provider",
                "generate_url": "https://images-a.example/v1/images/generations",
                "responses_url": "https://responses-b.example/v1/responses",
                "preferred_transport": "auto",
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"
    fake.run_json.assert_not_awaited()
    fake.run_responses.assert_not_awaited()


def test_failed_old_responses_job_keeps_requested_reasoning_effort(
    make_client, settings_factory
) -> None:
    from picgen.errors import APIError

    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "correct horse battery admin"},
    ).status_code == 200
    fake.run_responses.side_effect = APIError(502, "上游失败", code="upstream_error")

    response = client.post(
        "/api/responses-image",
        json={
            "prompt": "旧接口失败记录",
            "size": "1088x2240",
            "reasoning_effort": "low",
        },
    )
    assert response.status_code == 502

    job = client.get("/api/jobs?limit=1").json()["jobs"][0]
    assert job["status"] == "failed"
    assert job["model"] == "gpt-5.6-sol"
    assert job["transport"] == "responses-image"
    assert job["reasoning_effort"] == "low"


def test_image_job_records_actual_execution_metadata(make_client, settings_factory) -> None:
    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
    )
    client, fake, resolved = make_client(settings=settings)
    register = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    )
    assert register.status_code == 200
    fake.run_responses.return_value = {
        "data": [{"b64_json": _png_b64(1088, 2240)}],
        "created": 1,
    }

    response = client.post(
        "/api/image-jobs",
        json={"prompt": "记录真实执行信息", "mode": "generate", "size": "1088x2240"},
    )
    assert response.status_code == 200

    jobs_response = client.get("/api/jobs?limit=1")
    assert jobs_response.status_code == 200
    job = jobs_response.json()["jobs"][0]
    assert job["endpoint_path"] == "/api/image-jobs"
    assert job["transport"] == "responses-image"
    assert job["model"] == "gpt-5.6-sol"
    assert job["reasoning_effort"] == "max"

    with sqlite3.connect(resolved.resolved_auth_db_path) as conn:
        image_model = conn.execute(
            "SELECT model FROM generated_images WHERE job_id = ?",
            (job["id"],),
        ).fetchone()
    assert image_model == ("gpt-5.6-sol",)


def test_failed_image_job_keeps_resolved_execution_metadata(make_client, settings_factory) -> None:
    from picgen.errors import APIError

    settings = settings_factory(
        auth_enabled=True,
        admin_password="correct horse battery admin",
        default_api_key="sk-server",
    )
    client, fake, _ = make_client(settings=settings)
    assert client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "correct horse battery"},
    ).status_code == 200
    fake.run_responses.side_effect = APIError(
        502,
        "上游失败",
        code="upstream_error",
    )

    response = client.post(
        "/api/image-jobs",
        json={"prompt": "失败任务仍保留执行计划", "mode": "generate", "size": "1088x2240"},
    )
    assert response.status_code == 502

    jobs_response = client.get("/api/jobs?limit=1")
    assert jobs_response.status_code == 200
    job = jobs_response.json()["jobs"][0]
    assert job["status"] == "failed"
    assert job["transport"] == "responses-image"
    assert job["model"] == "gpt-5.6-sol"
    assert job["reasoning_effort"] == "max"

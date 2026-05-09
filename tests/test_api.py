from pathlib import Path

from fastapi.testclient import TestClient

from picgen.config import Settings
from picgen.main import create_app


def test_health_endpoint_reports_ok(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(root_dir=tmp_path, static_dir=tmp_path, data_dir=tmp_path / "data")))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_config_reports_api_key_presence_without_leaking_value(tmp_path: Path) -> None:
    settings = Settings(
        root_dir=tmp_path,
        static_dir=tmp_path,
        data_dir=tmp_path / "data",
        default_api_key="sk-secret",
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["has_default_api_key"] is True
    assert "sk-secret" not in response.text


def test_generate_requires_prompt_before_api_key(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(root_dir=tmp_path, static_dir=tmp_path, data_dir=tmp_path / "data")))

    response = client.post("/api/generate", json={"api_key": "sk-test"})

    assert response.status_code == 400
    assert response.json()["error"] == "生成提示词不能为空"


def test_edit_requires_image_payload(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            Settings(
                root_dir=tmp_path,
                static_dir=tmp_path,
                data_dir=tmp_path / "data",
                default_api_key="sk-test",
            )
        )
    )

    response = client.post("/api/edit", json={"prompt": "换成水彩风格"})

    assert response.status_code == 400
    assert response.json()["error"] == "缺少 image[] 文件"

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(SRC_DIR))

from picgen.config import Settings  # noqa: E402
from picgen.main import create_app  # noqa: E402
from picgen.routes import get_client  # noqa: E402


class FakeUpstreamClient:
    """In-memory upstream client used by route tests."""

    def __init__(self) -> None:
        self.run_json = AsyncMock()
        self.run_multipart = AsyncMock()
        self.run_file_upload = AsyncMock()
        self.run_responses = AsyncMock()
        self.fetch_image = AsyncMock()

    async def aclose(self) -> None:  # pragma: no cover - interface compatibility
        return None


@pytest.fixture()
def settings_factory(tmp_path: Path):
    def _factory(**overrides: Any) -> Settings:
        base = {
            "_env_file": None,
            "root_dir": tmp_path,
            "static_dir": tmp_path,
            "data_dir": tmp_path / "data",
            "auth_enabled": False,
            # Most route tests intentionally exercise registration. Production
            # keeps this closed by default and has dedicated coverage below.
            "self_registration_enabled": True,
            "allow_anonymous_execution_overrides": True,
            "rate_limit_per_minute": 0,
            "rate_limit_burst": 0,
            "log_level": "WARNING",
        }
        base.update(overrides)
        return Settings(**base)

    return _factory


@pytest.fixture()
def make_client(settings_factory):
    def _builder(
        *,
        settings: Settings | None = None,
        upstream: FakeUpstreamClient | None = None,
    ) -> tuple[TestClient, FakeUpstreamClient, Settings]:
        resolved_settings = settings or settings_factory()
        app = create_app(resolved_settings)
        fake = upstream or FakeUpstreamClient()
        app.dependency_overrides[get_client] = lambda: fake
        client = TestClient(app)
        return client, fake, resolved_settings

    return _builder

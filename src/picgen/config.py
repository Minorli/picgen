from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    root_dir: Path = PROJECT_ROOT
    static_dir: Path = PROJECT_ROOT / "static"
    data_dir: Path = PROJECT_ROOT / "data"
    default_generate_url: str = "https://api.openai.com/v1/images/generations"
    default_edit_url: str = "https://api.openai.com/v1/images/edits"
    default_model: str = "gpt-image-2"
    default_size: str = "auto"
    default_api_key: str = ""
    upstream_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            default_generate_url=os.environ.get(
                "PICGEN_DEFAULT_GENERATE_URL",
                "https://api.openai.com/v1/images/generations",
            ).strip(),
            default_edit_url=os.environ.get(
                "PICGEN_DEFAULT_EDIT_URL",
                "https://api.openai.com/v1/images/edits",
            ).strip(),
            default_model=os.environ.get("PICGEN_DEFAULT_MODEL", "gpt-image-2").strip() or "gpt-image-2",
            default_size=os.environ.get("PICGEN_DEFAULT_SIZE", "auto").strip() or "auto",
            default_api_key=os.environ.get("PICGEN_DEFAULT_API_KEY", "").strip(),
            upstream_user_agent=(
                os.environ.get("PICGEN_UPSTREAM_USER_AGENT", "").strip()
                or cls.upstream_user_agent
            ),
        )

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

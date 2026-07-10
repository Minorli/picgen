from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_RESPONSES_MODEL = "gpt-5.6-sol"
DEFAULT_RESPONSES_REASONING_EFFORT = "max"
LEGACY_DEFAULT_RESPONSES_MODEL = "gpt-5.5"
RESPONSES_MODEL_STORAGE_VERSION = 3


class Settings(BaseSettings):
    """Runtime configuration loaded from env vars (PICGEN_*) or .env file."""

    model_config = SettingsConfigDict(
        env_prefix="PICGEN_",
        env_file=os.environ.get("PICGEN_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    root_dir: Path = Field(default=PROJECT_ROOT)
    static_dir: Path = Field(default=PROJECT_ROOT / "static")
    data_dir: Path = Field(default=PROJECT_ROOT / "data")

    default_generate_url: str = "https://sub.tidba.com/v1/images/generations"
    default_edit_url: str = "https://sub.tidba.com/v1/images/edits"
    default_responses_url: str = "https://sub.tidba.com/v1/responses"
    default_model: str = "gpt-image-2"
    default_responses_model: str = DEFAULT_RESPONSES_MODEL
    default_size: str = "1088x2240"
    default_api_key: str = ""

    upstream_user_agent: str = DEFAULT_USER_AGENT
    upstream_timeout_seconds: float = Field(default=1200.0, ge=10.0, le=3600.0)
    upstream_connect_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    upstream_max_connections: int = Field(default=64, ge=1, le=1024)
    upstream_max_keepalive: int = Field(default=16, ge=1, le=512)
    upstream_max_retries: int = Field(default=2, ge=0, le=10)
    upstream_retry_backoff: float = Field(default=0.75, ge=0.0, le=10.0)

    max_request_body_bytes: int = Field(default=64 * 1024 * 1024, ge=1024)
    max_image_bytes: int = Field(default=32 * 1024 * 1024, ge=1024)
    # When the upstream returns an image smaller than the exact requested size,
    # optionally re-run the generation and keep the attempt closest to the
    # target. Default 0 (disabled): the current upstream downscales
    # deterministically, so a retry just doubles the bill for the same result.
    # Turn on (1-3) only if the upstream becomes intermittent again. Applies to
    # exact-size (strict) requests with sample_count == 1.
    size_mismatch_max_retries: int = Field(default=0, ge=0, le=3)
    rate_limit_per_minute: int = Field(default=120, ge=0, le=100000)
    rate_limit_burst: int = Field(default=20, ge=0, le=10000)

    # NoDecode: keep the raw env string ("a.com,b.com" or "") out of pydantic's
    # JSON decoding — without it any non-JSON value aborts startup before the
    # comma-splitting validator below ever runs.
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    cors_allow_credentials: bool = False
    proxy_auth_token: str = ""
    trust_forwarded_for: bool = False

    auth_enabled: bool = True
    auth_db_path: Path | None = None
    auth_cookie_name: str = "picgen_session"
    auth_cookie_secure: bool = False
    auth_session_days: int = Field(default=14, ge=1, le=365)
    admin_username: str = "admin"
    admin_password: str = ""

    public_base_url: str = ""
    smtp_host: str = ""
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "PicGen"
    smtp_use_tls: bool = True
    smtp_starttls: bool = False
    smtp_timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    password_reset_token_minutes: int = Field(default=30, ge=5, le=1440)

    bug_report_webhook_url: str = ""
    bug_report_webhook_kind: str = "wecom"
    bug_report_webhook_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    error_alert_telegram_bot_token: str = ""
    error_alert_telegram_chat_id: str = ""
    error_alert_telegram_timeout_seconds: float = Field(default=15.0, ge=1.0, le=30.0)
    map_provider: str = ""
    amap_key: str = ""
    mapbox_token: str = ""
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    map_geocode_timeout_seconds: float = Field(default=4.0, ge=1.0, le=30.0)

    log_level: str = "INFO"
    log_format: str = "console"

    storage_retention_days: int = Field(default=0, ge=0, le=3650)

    @field_validator(
        "default_generate_url",
        "default_edit_url",
        "default_responses_url",
        mode="after",
    )
    @classmethod
    def _validate_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("URL 不能为空")
        HttpUrl(cleaned)
        return cleaned

    @field_validator(
        "default_model",
        "default_responses_model",
        "default_size",
        mode="after",
    )
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("auth_db_path", mode="before")
    @classmethod
    def _empty_path_is_none(cls, value: object) -> object:
        # An empty env value must fall back to the default DB path; pydantic
        # would otherwise coerce "" to Path(".") which is truthy and points the
        # sqlite file at the working directory.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("upstream_user_agent", mode="after")
    @classmethod
    def _default_user_agent_when_empty(cls, value: str) -> str:
        return value.strip() or DEFAULT_USER_AGENT

    @field_validator(
        "default_api_key",
        "proxy_auth_token",
        "bug_report_webhook_url",
        "error_alert_telegram_bot_token",
        "error_alert_telegram_chat_id",
        "map_provider",
        "amap_key",
        "mapbox_token",
        "nominatim_url",
        "public_base_url",
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "smtp_from_email",
        "smtp_from_name",
        mode="after",
    )
    @classmethod
    def _strip_secret(cls, value: str) -> str:
        return value.strip()

    @field_validator("bug_report_webhook_kind", mode="after")
    @classmethod
    def _normalize_bug_report_webhook_kind(cls, value: str) -> str:
        normalized = value.strip().lower() or "wecom"
        if normalized not in {"wecom", "serverchan", "generic"}:
            raise ValueError("PICGEN_BUG_REPORT_WEBHOOK_KIND 只能是 wecom、serverchan 或 generic")
        return normalized

    @field_validator("map_provider", mode="after")
    @classmethod
    def _normalize_map_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"", "amap", "mapbox", "nominatim"}:
            raise ValueError("PICGEN_MAP_PROVIDER 只能是 amap、mapbox、nominatim 或留空")
        return normalized

    @field_validator("admin_username", mode="after")
    @classmethod
    def _validate_admin_username(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2 or len(cleaned) > 64:
            raise ValueError("管理员用户名长度必须在 2 到 64 个字符之间")
        if any(char.isspace() for char in cleaned):
            raise ValueError("管理员用户名不能包含空白字符")
        if any(ord(char) < 32 for char in cleaned):
            raise ValueError("管理员用户名包含非法字符")
        return cleaned

    @field_validator("admin_password", mode="after")
    @classmethod
    def _validate_admin_password(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned and len(cleaned) < 8:
            raise ValueError("管理员密码至少需要 8 个字符")
        return cleaned

    @field_validator("log_level", mode="after")
    @classmethod
    def _normalize_level(cls, value: str) -> str:
        normalized = value.strip().upper() or "INFO"
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"未知日志级别: {value}")
        return normalized

    @field_validator("log_format", mode="after")
    @classmethod
    def _normalize_format(cls, value: str) -> str:
        normalized = value.strip().lower() or "console"
        if normalized not in {"console", "json"}:
            raise ValueError(f"未知日志格式: {value}")
        return normalized

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                # Backwards compatibility: JSON list syntax used to be the only
                # accepted env format before NoDecode was introduced.
                try:
                    parsed = json.loads(text)
                except ValueError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def resolved_auth_db_path(self) -> Path:
        return self.auth_db_path or self.data_dir / "auth.sqlite3"

    @classmethod
    def from_env(cls, **overrides: object) -> Settings:
        return cls(**overrides)  # type: ignore[arg-type]

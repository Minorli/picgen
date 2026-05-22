from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .upstream.payload import decode_base64_blob


class FilePayload(BaseModel):
    """Image (or mask) payload sent inline from the browser."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(default="image.png", max_length=255)
    type: str = Field(default="", max_length=128)
    data_url: str = Field(default="", description="data URL or raw base64 content")

    @field_validator("name", mode="after")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        return value.strip() or "image.png"

    def decoded_bytes(self) -> bytes:
        return decode_base64_blob(self.data_url)


class _ImageOptions(BaseModel):
    quality: Literal["auto", "low", "medium", "high"] | None = None
    background: Literal["auto", "opaque", "transparent"] | None = None
    output_format: Literal["png", "jpeg", "webp"] | None = None
    output_compression: int | None = Field(default=None, ge=0, le=100)
    moderation: Literal["auto", "low"] | None = None


def _require_prompt(value: object, *, empty_message: str) -> str:
    if value is None:
        raise ValueError(empty_message)
    stripped = str(value).strip()
    if not stripped:
        raise ValueError(empty_message)
    if len(stripped) > 32_000:
        raise ValueError("提示词过长")
    return stripped


class GenerateRequest(_ImageOptions):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    prompt: str = Field(default="")
    endpoint_url: str | None = None
    model: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=512)
    size: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _validate_prompt(self) -> GenerateRequest:
        self.prompt = _require_prompt(self.prompt, empty_message="生成提示词不能为空")
        return self


class EditRequest(_ImageOptions):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    prompt: str = Field(default="")
    endpoint_url: str | None = None
    model: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=512)
    size: str | None = Field(default=None, max_length=64)
    image: FilePayload
    mask: FilePayload | None = None
    mode: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _validate_prompt(self) -> EditRequest:
        self.prompt = _require_prompt(self.prompt, empty_message="编辑指令不能为空")
        return self


class ResponsesImageRequest(_ImageOptions):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    prompt: str = Field(default="")
    endpoint_url: str | None = None
    model: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=512)
    size: str | None = Field(default=None, max_length=64)
    image: FilePayload | None = None
    mode: str | None = Field(default=None, max_length=64)
    allow_inline_fallback: bool = True

    @model_validator(mode="after")
    def _validate_prompt(self) -> ResponsesImageRequest:
        self.prompt = _require_prompt(self.prompt, empty_message="Responses 图像提示词不能为空")
        return self


class ConfigResponse(BaseModel):
    generate_url: str
    edit_url: str
    responses_url: str
    default_model: str
    default_responses_model: str
    default_size: str
    has_default_api_key: bool
    storage_dir: str
    max_image_bytes: int
    max_request_body_bytes: int
    rate_limit_per_minute: int
    upstream_timeout_seconds: float


class HealthResponse(BaseModel):
    ok: bool = True


class ReadinessResponse(BaseModel):
    ok: bool
    storage_writable: bool
    upstream_client_ready: bool
    version: str


class ErrorResponse(BaseModel):
    error: str
    details: str | None = None
    code: str | None = None
    request_id: str | None = None


class ImageResultResponse(BaseModel):
    """Loose schema for responses sent to the browser (kept flexible for clients)."""

    model_config = ConfigDict(extra="allow")

    mode: str
    prompt: str
    model: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ImageResultResponse:
        return cls.model_validate(payload)

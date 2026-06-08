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
    role: str | None = Field(default=None, max_length=64)

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
    mode: str | None = Field(default=None, max_length=64)
    sample_count: int = Field(default=1, ge=1, le=3)
    logo_requested: bool = False

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
    image: FilePayload | None = None
    images: list[FilePayload] = Field(default_factory=list, max_length=16)
    mask: FilePayload | None = None
    mode: str | None = Field(default=None, max_length=64)
    sample_count: int = Field(default=1, ge=1, le=3)
    logo_requested: bool = False

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
    images: list[FilePayload] = Field(default_factory=list, max_length=16)
    mode: str | None = Field(default=None, max_length=64)
    sample_count: int = Field(default=1, ge=1, le=3)
    allow_inline_fallback: bool = True
    logo_requested: bool = False

    @model_validator(mode="after")
    def _validate_prompt(self) -> ResponsesImageRequest:
        self.prompt = _require_prompt(self.prompt, empty_message="Responses 图像提示词不能为空")
        return self


class CopyrightRiskRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    prompt: str = Field(default="", max_length=32_000)
    context: str = Field(default="", max_length=8_000)
    endpoint_url: str | None = None
    model: str | None = Field(default=None, max_length=128)
    api_key: str | None = Field(default=None, max_length=512)
    images: list[FilePayload] = Field(default_factory=list, min_length=1, max_length=1)


class AuthRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    company: str = Field(default="6renyou", max_length=120)
    department: str = Field(default="PD & OPS", max_length=120)

    @field_validator("username", "company", "department", mode="after")
    @classmethod
    def _trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("username", mode="after")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        if any(char.isspace() for char in value):
            raise ValueError("用户名不能包含空白字符")
        return value


class AdminCreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["admin", "user"] = "user"

    @field_validator("username", mode="after")
    @classmethod
    def _trim_username(cls, value: str) -> str:
        stripped = value.strip()
        if any(char.isspace() for char in stripped):
            raise ValueError("用户名不能包含空白字符")
        return stripped


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str = Field(min_length=2, max_length=64)

    @field_validator("username", mode="after")
    @classmethod
    def _trim_username(cls, value: str) -> str:
        stripped = value.strip()
        if any(char.isspace() for char in stripped):
            raise ValueError("用户名不能包含空白字符")
        return stripped


class PasswordResetConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: str = Field(min_length=20, max_length=512)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("token", mode="after")
    @classmethod
    def _trim_token(cls, value: str) -> str:
        return value.strip()


class AdminResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    password: str = Field(min_length=8, max_length=256)


class OrganizationUnitRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    company: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=120)

    @field_validator("company", "department", mode="after")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class AdminUpdateUserOrgRequest(OrganizationUnitRequest):
    reason: str = Field(default="", max_length=1000)

    @field_validator("reason", mode="after")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        return value.strip()


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class UserProfileRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    username: str = Field(min_length=2, max_length=64)
    current_password: str = Field(default="", max_length=256)
    display_name: str = Field(default="", max_length=80)
    wechat: str = Field(default="", max_length=120)
    phone_country_code: str = Field(default="+86", max_length=8)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=160)
    company: str = Field(default="6renyou", max_length=120)
    department: str = Field(default="PD & OPS", max_length=120)
    team: str = Field(default="", max_length=120)
    job_title: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=1000)

    @field_validator(
        "username",
        "current_password",
        "display_name",
        "wechat",
        "phone_country_code",
        "phone",
        "email",
        "company",
        "department",
        "team",
        "job_title",
        "note",
        mode="after",
    )
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("username", mode="after")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        if any(char.isspace() for char in value):
            raise ValueError("用户名不能包含空白字符")
        return value

    @field_validator("phone_country_code", mode="after")
    @classmethod
    def _validate_phone_country_code(cls, value: str) -> str:
        cleaned = value or "+86"
        if not cleaned.startswith("+") or not cleaned[1:].isdigit():
            raise ValueError("电话国家码格式不正确")
        return cleaned

    @field_validator("phone", mode="after")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        if value and not all(char.isdigit() or char in {"-", " ", "(", ")"} for char in value):
            raise ValueError("电话号码格式不正确")
        return value

    @field_validator("email", mode="after")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        if value and ("@" not in value or "." not in value.rsplit("@", 1)[-1]):
            raise ValueError("邮箱格式不正确")
        return value


class AvatarUploadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    image: FilePayload


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rating: Literal["good", "ok", "bad"]
    reason: str = Field(default="", max_length=1000)
    prompt: str = Field(default="", max_length=32_000)
    mode: str = Field(default="", max_length=64)
    model: str = Field(default="", max_length=128)
    saved_image_path: str = Field(default="", max_length=1024)
    saved_image_url: str = Field(default="", max_length=1024)
    generated_image_id: int | None = Field(default=None, ge=1)

    @field_validator("reason", "prompt", "mode", "model", "saved_image_path", "saved_image_url", mode="after")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class BugReportRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="", max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    contact: str = Field(default="", max_length=256)
    page_url: str = Field(default="", max_length=1024)

    @field_validator("title", "description", "contact", "page_url", mode="after")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class ShareResultRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    recipient_ids: list[int] = Field(min_length=1, max_length=50)
    prompt: str = Field(default="", max_length=32_000)
    mode: str = Field(default="", max_length=64)
    model: str = Field(default="", max_length=128)
    rating: Literal["", "good", "ok", "bad"] = ""
    saved_image_path: str = Field(default="", max_length=1024)
    saved_image_url: str = Field(default="", max_length=1024)
    generated_image_id: int | None = Field(default=None, ge=1)
    note: str = Field(default="", max_length=1000)

    @field_validator("recipient_ids", mode="after")
    @classmethod
    def _validate_recipient_ids(cls, value: list[int]) -> list[int]:
        cleaned = [int(user_id) for user_id in value if int(user_id) > 0]
        if not cleaned:
            raise ValueError("请选择至少一个分享对象")
        return list(dict.fromkeys(cleaned))

    @field_validator("prompt", "mode", "model", "rating", "saved_image_path", "saved_image_url", "note", mode="after")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class TeamChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    room_type: Literal["team", "dm", "bot"] = "team"
    recipient_user_id: int | None = Field(default=None, ge=1)
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content", mode="after")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("消息不能为空")
        return stripped


class TeamChatReadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    room_type: Literal["team", "dm", "bot"] = "team"
    recipient_user_id: int | None = Field(default=None, ge=1)
    message_id: int = Field(default=0, ge=0)


class GroupAnnouncementRequest(OrganizationUnitRequest):
    content: str = Field(default="", max_length=2000)

    @field_validator("content", mode="after")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        return value.strip()


class GroupSavedItemRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    generated_image_id: int = Field(ge=1)
    title: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=1000)

    @field_validator("title", "note", mode="after")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class GalleryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_favorite: bool = False
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("tags", mode="after")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw_tag in value:
            tag = str(raw_tag).strip()[:40]
            if not tag:
                continue
            folded = tag.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            cleaned.append(tag)
        return cleaned


class FinalImageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    generated_image_id: int = Field(ge=1)
    image: FilePayload
    source_saved_image_path: str = Field(default="", max_length=1024)
    source_saved_image_url: str = Field(default="", max_length=1024)
    logo_overlay_applied: bool = False
    logo_overlay_source: str = Field(default="", max_length=255)
    logo_text_color: str = Field(default="", max_length=32)

    @field_validator(
        "source_saved_image_path",
        "source_saved_image_url",
        "logo_overlay_source",
        "logo_text_color",
        mode="after",
    )
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class UserPreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    default_model: str = Field(default="", max_length=128)
    default_responses_model: str = Field(default="", max_length=128)
    default_size: str = Field(default="", max_length=64)
    default_quality: Literal["", "auto", "low", "medium", "high"] = ""
    default_output_format: Literal["", "png", "jpeg", "webp"] = ""
    default_image_transport: Literal["", "images", "responses"] = ""
    logo_overlay_enabled: bool = True
    auto_copyright_check_enabled: bool = True

    @field_validator(
        "default_model",
        "default_responses_model",
        "default_size",
        "default_quality",
        "default_output_format",
        "default_image_transport",
        mode="after",
    )
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


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
    auth_enabled: bool
    bug_report_notifications_enabled: bool
    error_alert_notifications_enabled: bool
    password_reset_email_enabled: bool


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

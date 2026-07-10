from __future__ import annotations

import asyncio
import base64
import binascii
import difflib
import json
import logging
import math
import os
import re
import tempfile
import time
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

import anyio
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import FileResponse, JSONResponse

from . import __version__
from .auth import (
    TEAM_CHAT_BOT_NAME,
    AccountLockedError,
    AuthStore,
    AuthUser,
    InvalidCredentialsError,
    UserExistsError,
    normalize_username,
)
from .config import (
    DEFAULT_RESPONSES_MODEL,
    DEFAULT_RESPONSES_REASONING_EFFORT,
    LEGACY_DEFAULT_RESPONSES_MODEL,
    RESPONSES_MODEL_STORAGE_VERSION,
    Settings,
)
from .errors import APIError
from .itinerary_map import (
    apply_itinerary_coordinate_estimates,
    build_itinerary_map_plan_async,
    geocode_place_with_settings,
    project_itinerary_points,
    render_itinerary_control_png,
    render_itinerary_map_svg,
    save_itinerary_map_svg,
)
from .logging_config import get_logger, get_request_id, log_event
from .notifications import (
    GenerationSuccessAlert,
    admin_notifications_enabled,
    error_alert_notifications_enabled,
    send_bug_report_notification,
    send_generation_success_notification,
    send_password_reset_email,
    send_password_reset_request_notification,
    smtp_notifications_enabled,
)
from .recipes import list_prompt_recipes, recipe_public_dict
from .redaction import redact_sensitive_text
from .restricted_destinations import (
    RESTRICTED_DESTINATION_CODE,
    RESTRICTED_DESTINATION_ERROR,
    RESTRICTED_DESTINATION_GUARD_TEXT,
    append_restricted_destination_guard,
    stop_has_restricted_destination,
    values_contain_restricted_destination,
)
from .schemas import (
    AdminCreateUserRequest,
    AdminResetPasswordRequest,
    AdminUpdateUserOrgRequest,
    AuthRequest,
    AvatarUploadRequest,
    BugReportRequest,
    ChangePasswordRequest,
    ConfigResponse,
    CopyrightRiskRequest,
    EditRequest,
    FeedbackRequest,
    FilePayload,
    FinalImageRequest,
    GalleryUpdateRequest,
    GenerateRequest,
    GroupAnnouncementRequest,
    GroupSavedItemRequest,
    HealthResponse,
    ImageResultResponse,
    ItineraryMapPlanRequest,
    ItineraryMapRenderRequest,
    OrganizationUnitRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ReadinessResponse,
    ResponsesImageRequest,
    ShareResultRequest,
    TeamChatMessageRequest,
    TeamChatReadRequest,
    TextFidelityRequest,
    UserPreferencesRequest,
    UserProfileRequest,
)
from .storage import (
    MAX_EXACT_IMAGE_PIXELS,
    detect_image_mime,
    extension_for_mime,
    resolve_storage_path,
    sanitize_filename,
    sanitize_filename_prefix,
    save_derived_output_image,
    storage_url_for_path,
)
from .upstream import (
    compact_raw_response,
    openai_image_options,
    prepare_image_payload,
    request_metadata,
    sibling_endpoint_url,
    validate_url,
)
from .upstream.client import UpstreamClient

logger = get_logger("picgen.routes")
_TEAM_CHAT_BOT_TASKS: set[asyncio.Task[dict[str, Any]]] = set()
_ITINERARY_ID_RE = re.compile(
    r"(?i)(?:行程\s*id|行程\s*ID|itinerary\s*id|trip\s*id|(?<![A-Za-z])id)"
    r"\s*[:：#-]?\s*([A-Za-z0-9][A-Za-z0-9._-]{1,31})"
)


def _strict_requested_size(size: str | None) -> bool:
    cleaned = (size or "").strip()
    return bool(cleaned and cleaned != "auto")


def _parse_requested_size(size: Any) -> tuple[int, int] | None:
    if not isinstance(size, str):
        return None
    match = re.fullmatch(r"\s*(\d{2,5})x(\d{2,5})\s*", size)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


MAX_EXACT_IMAGE_SIDE = 3840
MAX_EXACT_IMAGE_ASPECT_RATIO = 3.0


def _validate_exact_image_size(size: str | None) -> tuple[int, int] | None:
    cleaned = (size or "").strip()
    if not cleaned or cleaned == "auto":
        return None
    parsed = _parse_requested_size(cleaned)
    if parsed is None:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "图片尺寸必须是 auto 或 WIDTHxHEIGHT 格式",
            code="invalid_parameter",
        )
    width, height = parsed
    if width > MAX_EXACT_IMAGE_SIDE or height > MAX_EXACT_IMAGE_SIDE:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            f"图片尺寸单边不能超过 {MAX_EXACT_IMAGE_SIDE} 像素",
            code="invalid_parameter",
        )
    if width * height > MAX_EXACT_IMAGE_PIXELS:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            f"图片尺寸总像素不能超过 {MAX_EXACT_IMAGE_PIXELS}",
            code="invalid_parameter",
        )
    aspect_ratio = max(width / height, height / width)
    if aspect_ratio > MAX_EXACT_IMAGE_ASPECT_RATIO:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            f"图片尺寸宽高比不能超过 {MAX_EXACT_IMAGE_ASPECT_RATIO:g}:1",
            code="invalid_parameter",
        )
    return parsed


def _highest_quality_image_options(options: dict[str, Any]) -> dict[str, Any]:
    quality = str(options.get("quality") or "").strip()
    if quality and quality != "auto":
        return options
    return {**options, "quality": "high"}


def _responses_reasoning_options(model: str) -> dict[str, dict[str, str]]:
    if model.strip() != DEFAULT_RESPONSES_MODEL:
        return {}
    return {"reasoning": {"effort": DEFAULT_RESPONSES_REASONING_EFFORT}}


def _normalize_legacy_client_responses_model(
    model: str,
    *,
    storage_version: int | None,
    default_model: str,
) -> str:
    if model == LEGACY_DEFAULT_RESPONSES_MODEL and (storage_version or 0) < RESPONSES_MODEL_STORAGE_VERSION:
        return default_model.strip() or DEFAULT_RESPONSES_MODEL
    return model


JSON_BODY = Body(...)
PASSWORD_RESET_REQUEST_MESSAGE = "如果账号存在且已填写邮箱，会收到重置邮件；否则管理员会看到找回申请。"
RESERVED_SELF_SERVICE_USERNAMES = frozenset({"admin"})
ITINERARY_DEFAULT_SIZE = "1792x1792"
ITINERARY_AUTO_SIZE = "auto"
ITINERARY_PORTRAIT_SIZE = "1088x2240"
ITINERARY_LANDSCAPE_SIZE = "1920x1088"
ITINERARY_MAX_CANVAS_SIDE = 4096
ITINERARY_INLINE_REFERENCE_MAX_BYTES = 2 * 1024 * 1024
ITINERARY_ORIENTATION_THRESHOLD = 1.25
ITINERARY_ARTWORK_INSTRUCTIONS = (
    "你是 PicGen 的图像生成助手。严格遵守用户提示词和输入参考图，"
    "输出一张用于后续程序叠加准确路线和文字的高端旅行地图底图。"
    f"{RESTRICTED_DESTINATION_GUARD_TEXT}"
)
ITINERARY_COORDINATE_INSTRUCTIONS = (
    "你是严谨的地理坐标助手。只输出可解析 JSON，不要 Markdown，不要解释；"
    "为缺少坐标的旅行路线节点估算大概经纬度，优先保证真实相对位置。"
    f"{RESTRICTED_DESTINATION_GUARD_TEXT}"
)
RESPONSES_IMAGE_INSTRUCTIONS = (
    "你是 PicGen 的图像生成助手。严格遵守用户提示词、参考图和品牌要求，输出可直接用于旅行产品设计的图像。"
    f"{RESTRICTED_DESTINATION_GUARD_TEXT}"
)
TEAM_CHAT_BOT_INSTRUCTIONS = (
    "你是 PicGen 团队聊天里的 GPT-BOT。用中文回复，专业、简洁、可信；群聊被 @ 时回复要艾特提问者，私聊直接回复。"
)
COPYRIGHT_RISK_INSTRUCTIONS = "你是图片版权与商标风险审查助手。用中文输出简短、务实、非法律意见的风险提醒。"
TEXT_FIDELITY_INSTRUCTIONS = (
    "你是 PicGen 的图片文字一致性验收助手。你会收到一张最终图和文字合同。"
    "只检查图片中可读文字是否和合同一致，不评价美感，不重写文案。"
    "必须逐字核对中文、数字、符号、英文大小写和顺序。"
)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_client(request: Request) -> UpstreamClient:
    return request.app.state.upstream_client


def get_auth_store(request: Request) -> AuthStore:
    return request.app.state.auth_store


def _raise_restricted_destination_error() -> None:
    raise APIError(
        HTTPStatus.BAD_REQUEST,
        RESTRICTED_DESTINATION_ERROR,
        code=RESTRICTED_DESTINATION_CODE,
    )


def _ensure_no_restricted_destination_text(*values: Any) -> None:
    if values_contain_restricted_destination(values):
        _raise_restricted_destination_error()


def _ensure_no_restricted_destination_stops(stops: list[Any]) -> None:
    for stop in stops:
        if isinstance(stop, dict):
            if stop_has_restricted_destination(stop):
                _raise_restricted_destination_error()
            continue
        if hasattr(stop, "model_dump") and stop_has_restricted_destination(stop.model_dump()):
            _raise_restricted_destination_error()


def _ensure_itinerary_request_has_no_restricted_destination(parsed: ItineraryMapPlanRequest) -> None:
    _ensure_no_restricted_destination_text(parsed.title, parsed.subtitle, parsed.route_style)
    _ensure_no_restricted_destination_stops([stop.model_dump() for stop in parsed.stops])


def _is_legacy_program_layout_background_prompt(value: str) -> bool:
    normalized = "".join(str(value or "").split())
    if not normalized:
        return False
    background_markers = ("无文字背景底图", "无字背景底图", "生成背景底图")
    layout_markers = ("后续程序排版", "用于程序排版", "程序排版中文", "程序覆盖", "中文由程序")
    no_text_markers = ("不生成任何可读文字", "不要生成文字内容", "不生成文字内容", "不要生成任何可读文字")
    return (
        any(marker in normalized for marker in background_markers)
        and any(marker in normalized for marker in layout_markers)
        and any(marker in normalized for marker in no_text_markers)
    )


def _ensure_not_legacy_program_layout_background_prompt(*values: str) -> None:
    if any(_is_legacy_program_layout_background_prompt(value) for value in values):
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "检测到旧程序排版背景底图提示词：它会要求 AI 生成空背景。"
            "请改成包含标题、榜单正文和全部可见文案的最终海报提示词。",
            code="legacy_layout_background_prompt",
        )


def _get_session_token(request: Request, settings: Settings) -> str:
    return request.cookies.get(settings.auth_cookie_name, "").strip()


def _password_reset_expires_at(settings: Settings) -> str:
    return (datetime.now(tz=UTC) + timedelta(minutes=settings.password_reset_token_minutes)).isoformat()


def _password_reset_url(request: Request, settings: Settings, token: str) -> str:
    base = settings.public_base_url.strip().rstrip("/")
    return f"{base}/?reset_token={token}"


def _password_reset_email_can_include_link(settings: Settings) -> bool:
    return bool(settings.public_base_url.strip())


def _safe_admin_reset_request_info(reset_request: dict[str, Any]) -> dict[str, Any]:
    return {**reset_request, "email_available": False, "reset_token": ""}


def _ensure_self_service_username_allowed(username: str, settings: Settings) -> None:
    normalized = normalize_username(username)
    reserved = {*RESERVED_SELF_SERVICE_USERNAMES, normalize_username(settings.admin_username)}
    if normalized in reserved:
        raise APIError(
            HTTPStatus.BAD_REQUEST,
            "该登录用户名为系统保留名，请换一个。",
            code="reserved_username",
        )


async def _current_user_or_none(request: Request, settings: Settings, auth_store: AuthStore) -> AuthUser | None:
    if not settings.auth_enabled:
        return None
    return await anyio.to_thread.run_sync(auth_store.user_for_session, _get_session_token(request, settings))


async def require_current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
    auth_store: AuthStore = Depends(get_auth_store),
) -> AuthUser | None:
    if not settings.auth_enabled:
        return None
    user = await _current_user_or_none(request, settings, auth_store)
    if user is None:
        raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
    return user


async def require_admin_user(user: AuthUser | None = Depends(require_current_user)) -> AuthUser:
    if user is None or not user.is_admin:
        raise APIError(HTTPStatus.FORBIDDEN, "需要管理员权限", code="forbidden")
    return user


def _auth_response(
    *,
    settings: Settings,
    auth_store: AuthStore,
    user: AuthUser,
) -> JSONResponse:
    session = auth_store.create_session(user.id, days=settings.auth_session_days)
    response = JSONResponse({"status": "ok", "user": user.public_dict()})
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=session.token,
        max_age=settings.auth_session_days * 24 * 60 * 60,
        expires=settings.auth_session_days * 24 * 60 * 60,
        path="/",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )
    return response


def _clear_auth_cookie(response: JSONResponse, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
    )


def _resolve_served_file(settings: Settings, relative_path: str) -> Path:
    cleaned = relative_path.strip().lstrip("/")
    allowed_roots: dict[str, tuple[Path, set[str]]] = {
        "outputs/": (settings.outputs_dir, {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".json"}),
        "avatars/": (settings.data_dir / "avatars", {".png", ".jpg", ".jpeg", ".webp"}),
    }
    matched_prefix = ""
    matched_root: Path | None = None
    matched_suffixes: set[str] = set()
    for prefix, (root, suffixes) in allowed_roots.items():
        if cleaned.startswith(prefix):
            matched_prefix = prefix
            matched_root = root
            matched_suffixes = suffixes
            break
    if matched_root is None:
        raise APIError(HTTPStatus.FORBIDDEN, "非法文件路径", code="forbidden")
    served_relative_path = cleaned[len(matched_prefix) :]
    if not served_relative_path:
        raise APIError(HTTPStatus.FORBIDDEN, "非法文件路径", code="forbidden")
    target_path = resolve_storage_path(matched_root, served_relative_path)
    if target_path.suffix.lower() not in matched_suffixes:
        raise APIError(HTTPStatus.FORBIDDEN, "非法文件类型", code="forbidden")
    return target_path


def _save_user_avatar(
    *,
    settings: Settings,
    user: AuthUser,
    image_bytes: bytes,
    image_mime: str,
) -> tuple[Path, str]:
    avatar_dir = settings.data_dir / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    prefix = sanitize_filename_prefix(user.username) or f"user-{user.id}"
    avatar_path = avatar_dir / f"{prefix}-{user.id}{extension_for_mime(image_mime)}"
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=avatar_path.suffix, dir=str(avatar_dir))
    temporary_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(image_bytes)
            fh.flush()
            os.fsync(fh.fileno())
        temporary_path.replace(avatar_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return avatar_path, storage_url_for_path(settings.data_dir, avatar_path)


def _map_geocoding_enabled(settings: Settings) -> bool:
    return (
        (settings.map_provider == "amap" and bool(settings.amap_key))
        or (settings.map_provider == "mapbox" and bool(settings.mapbox_token))
        or bool(settings.nominatim_url)
    )


def _public_map_provider(settings: Settings) -> str:
    return settings.map_provider or "nominatim"


def _parse_itinerary_size(value: str) -> tuple[int, int]:
    cleaned = (value or ITINERARY_DEFAULT_SIZE).strip() or ITINERARY_DEFAULT_SIZE
    if cleaned.casefold() == ITINERARY_AUTO_SIZE:
        cleaned = ITINERARY_DEFAULT_SIZE
    if "x" not in cleaned:
        raise APIError(HTTPStatus.BAD_REQUEST, "行程地图尺寸无效", code="invalid_parameter")
    width_text, height_text = cleaned.lower().split("x", 1)
    try:
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise APIError(HTTPStatus.BAD_REQUEST, "行程地图尺寸无效", code="invalid_parameter") from exc
    if width <= 0 or height <= 0:
        raise APIError(HTTPStatus.BAD_REQUEST, "行程地图尺寸必须大于 0", code="invalid_parameter")
    if width > ITINERARY_MAX_CANVAS_SIDE or height > ITINERARY_MAX_CANVAS_SIDE:
        raise APIError(HTTPStatus.BAD_REQUEST, "行程地图尺寸过大", code="invalid_parameter")
    if width % 16 != 0 or height % 16 != 0:
        raise APIError(HTTPStatus.BAD_REQUEST, "行程地图尺寸的宽高都必须是 16 的倍数", code="invalid_parameter")
    return width, height


def _itinerary_size_orientation(size: str) -> str:
    width, height = _parse_itinerary_size(size)
    if height > width:
        return "portrait"
    if width > height:
        return "landscape"
    return "square"


def _itinerary_coordinate_span(plan: dict[str, Any]) -> tuple[float, float]:
    stops = [
        stop
        for stop in plan.get("stops", [])
        if (
            isinstance(stop, dict)
            and isinstance(stop.get("lat"), (int, float))
            and isinstance(stop.get("lng"), (int, float))
        )
    ]
    if len(stops) < 2:
        return 0.0, 0.0
    lats = [float(stop["lat"]) for stop in stops]
    lngs = [float(stop["lng"]) for stop in stops]
    # Unwrap longitudes across the antimeridian exactly like the projection
    # (_project_stops) does — otherwise an Auckland→Tonga route "spans" 306°
    # east-west and auto-picks landscape for what projects as a portrait route.
    if max(lngs) - min(lngs) > 180.0:
        lngs = [lng + 360.0 if lng < 0 else lng for lng in lngs]
    lat_span = max(lats) - min(lats)
    mid_lat = (max(lats) + min(lats)) / 2
    lng_span = (max(lngs) - min(lngs)) * max(0.2, abs(math.cos(math.radians(mid_lat))))
    return lat_span, lng_span


def _choose_itinerary_output_size(plan: dict[str, Any], requested_size: str) -> dict[str, Any]:
    normalized_request = (requested_size or ITINERARY_AUTO_SIZE).strip() or ITINERARY_AUTO_SIZE
    lat_span, lng_span = _itinerary_coordinate_span(plan)
    if lat_span > lng_span * ITINERARY_ORIENTATION_THRESHOLD:
        optimal_size = ITINERARY_PORTRAIT_SIZE
        optimal_orientation = "portrait"
        reason = "南北跨度明显大于东西跨度"
    elif lng_span > lat_span * ITINERARY_ORIENTATION_THRESHOLD:
        optimal_size = ITINERARY_LANDSCAPE_SIZE
        optimal_orientation = "landscape"
        reason = "东西跨度明显大于南北跨度"
    else:
        optimal_size = ITINERARY_DEFAULT_SIZE
        optimal_orientation = "square"
        reason = "南北与东西跨度相对均衡"

    if normalized_request.casefold() == ITINERARY_AUTO_SIZE:
        selected_size = optimal_size
        orientation = optimal_orientation
        adjusted = selected_size != ITINERARY_DEFAULT_SIZE
        message = (
            f"系统根据真实坐标判断：{reason}，"
            f"已自动选择{_itinerary_orientation_label(orientation)}构图 {selected_size}。"
        )
    else:
        _parse_itinerary_size(normalized_request)
        selected_size = normalized_request
        orientation = _itinerary_size_orientation(selected_size)
        adjusted = False
        if orientation == optimal_orientation:
            message = (
                f"已按你手动选择的{_itinerary_orientation_label(orientation)}构图 {selected_size} 生成；"
                f"系统根据真实坐标判断：{reason}，当前尺寸与路线构图匹配。"
            )
        else:
            message = (
                f"已按你手动选择的{_itinerary_orientation_label(orientation)}构图 {selected_size} 生成；"
                f"系统根据真实坐标判断：{reason}，但不会自动改写手动尺寸。"
            )

    width, height = _parse_itinerary_size(selected_size)

    return {
        "requested_size": normalized_request,
        "selected_size": selected_size,
        "width": width,
        "height": height,
        "orientation": orientation,
        "adjusted": adjusted,
        "message": message,
        "lat_span": round(lat_span, 6),
        "lng_span": round(lng_span, 6),
    }


def _itinerary_orientation_label(orientation: str) -> str:
    if orientation == "portrait":
        return "竖版"
    if orientation == "landscape":
        return "横版"
    return "方图"


async def _ensure_admin_bootstrap(request: Request, settings: Settings, auth_store: AuthStore) -> None:
    if not settings.auth_enabled or getattr(request.app.state, "auth_admin_bootstrapped", False):
        return
    if settings.admin_password:
        await anyio.to_thread.run_sync(
            lambda: auth_store.ensure_admin_user(settings.admin_username, settings.admin_password)
        )
    else:
        await anyio.to_thread.run_sync(auth_store.initialize)
    request.app.state.auth_admin_bootstrapped = True


def _validate_image_size(part: FilePayload, max_image_bytes: int) -> dict[str, Any]:
    data = part.decoded_bytes()
    if len(data) > max_image_bytes:
        raise APIError(
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            f"图片过大，最大允许 {max_image_bytes // 1024} KB",
            code="payload_too_large",
        )
    file_name = sanitize_filename(part.name or "image.png")
    content_type = part.type.strip() or detect_image_mime(data)
    return {
        "field_name": "image",
        "filename": file_name,
        "content_type": content_type,
        "data": data,
    }


def _request_image_parts(
    *,
    image: FilePayload | None,
    images: list[FilePayload],
    max_image_bytes: int,
) -> list[dict[str, Any]]:
    source_images = images or ([image] if image is not None else [])
    image_parts: list[dict[str, Any]] = []
    for index, source_image in enumerate(source_images):
        part = _validate_image_size(source_image, max_image_bytes)
        part["field_name"] = "image"
        part["role"] = source_image.role or ("style_template" if index == 0 and len(source_images) > 1 else "material")
        part["index"] = index
        image_parts.append(part)
    return image_parts


def _image_reference_metadata(image_parts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "source_image_names": [str(part["filename"]) for part in image_parts],
        "source_image_roles": [str(part.get("role") or "") for part in image_parts],
        "source_image_count": len(image_parts),
        "source_image_name": str(image_parts[0]["filename"]) if image_parts else None,
    }


def _candidate_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _extend_candidate_items(target: dict[str, Any], source: dict[str, Any], limit: int) -> None:
    target_data = target.setdefault("data", [])
    if not isinstance(target_data, list):
        target_data = []
        target["data"] = target_data
    for item in _candidate_items(source):
        if len(target_data) >= limit:
            break
        target_data.append(item)


def _error_mentions_sample_count(exc: APIError) -> bool:
    haystack = f"{exc.message}\n{exc.details or ''}".lower()
    # Be specific: a bare " n" substring matches ordinary prose ("is not
    # allowed", "no credit") and would wrongly strip `n` on, e.g., a content
    # moderation 400. Only react to errors that actually name the sample-count
    # parameter.
    needles = (
        '"n"',
        "'n'",
        "parameter n",
        "param n",
        "value of n",
        "n must",
        "sample",
        "best_of",
        "num_images",
        "n_images",
    )
    return any(needle in haystack for needle in needles)


def _should_retry_without_sample_count(exc: APIError, sample_count: int) -> bool:
    if sample_count <= 1:
        return False
    if exc.status == HTTPStatus.BAD_REQUEST:
        return _error_mentions_sample_count(exc)
    # 502/503 from gateways that cannot handle n>1 usually mean the request
    # was rejected outright, so a retry without n is safe. A 504 means the
    # upstream may STILL be generating — re-POSTing would double the billing
    # for a generation that eventually completes.
    return exc.status in {
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
    }


async def _fill_candidates(
    *,
    initial: dict[str, Any],
    call_without_sample_count: Callable[[], Awaitable[dict[str, Any]]],
    sample_count: int,
) -> dict[str, Any]:
    """Top ``initial`` up to ``sample_count`` candidates.

    When the upstream ignores ``n`` and returns a single image per call, the
    missing images are fetched concurrently — each upstream call can take
    minutes, so issuing them serially would multiply end-to-end latency.
    Individual failures are tolerated: we return whatever candidates we managed
    to collect rather than discarding a successful first image.
    """

    existing = len(_candidate_items(initial))
    # Zero candidates is a refusal/failure shape (content filter, gateway
    # hiccup), not "upstream ignored n" — topping it up would silently re-run
    # full-price generations that will most likely fail the same way.
    if existing <= 0:
        return initial
    deficit = sample_count - existing
    if deficit <= 0:
        return initial
    results = await asyncio.gather(
        *(call_without_sample_count() for _ in range(deficit)),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, dict):
            _extend_candidate_items(initial, result, sample_count)
    return initial


async def _run_multipart_candidates(
    *,
    client: UpstreamClient,
    endpoint_url: str,
    api_key: str,
    fields: dict[str, Any],
    files: list[dict[str, Any]],
    user_agent: str,
    sample_count: int,
) -> dict[str, Any]:
    fallback_fields = {key: value for key, value in fields.items() if key != "n"}

    async def _call_without_n() -> dict[str, Any]:
        return await client.run_multipart(endpoint_url, api_key, fallback_fields, files, user_agent)

    try:
        response = await client.run_multipart(endpoint_url, api_key, fields, files, user_agent)
    except APIError as exc:
        if not _should_retry_without_sample_count(exc, sample_count):
            raise
        log_event(
            logger,
            logging.WARNING,
            "images_edit_sample_count_fallback",
            endpoint_url=endpoint_url,
            sample_count=sample_count,
            status=exc.status,
            message=exc.message,
        )
        response = await _call_without_n()

    return await _fill_candidates(
        initial=response,
        call_without_sample_count=_call_without_n,
        sample_count=sample_count,
    )


async def _run_json_candidates(
    *,
    client: UpstreamClient,
    endpoint_url: str,
    api_key: str,
    payload: dict[str, Any],
    user_agent: str,
    sample_count: int,
) -> dict[str, Any]:
    fallback_payload = {key: value for key, value in payload.items() if key != "n"}

    async def _call_without_n() -> dict[str, Any]:
        return await client.run_json(endpoint_url, api_key, fallback_payload, user_agent)

    try:
        response = await client.run_json(endpoint_url, api_key, payload, user_agent)
    except APIError as exc:
        if not _should_retry_without_sample_count(exc, sample_count):
            raise
        log_event(
            logger,
            logging.WARNING,
            "images_generate_sample_count_fallback",
            endpoint_url=endpoint_url,
            sample_count=sample_count,
            status=exc.status,
            message=exc.message,
        )
        response = await _call_without_n()

    return await _fill_candidates(
        initial=response,
        call_without_sample_count=_call_without_n,
        sample_count=sample_count,
    )


def _prepare_mask(part: FilePayload, max_image_bytes: int) -> dict[str, Any]:
    file_info = _validate_image_size(part, max_image_bytes)
    file_info["field_name"] = "mask"
    return file_info


def _itinerary_style_reference_part(settings: Settings) -> dict[str, Any] | None:
    candidates = (
        settings.static_dir / "itinerary-style-reference.png",
        settings.static_dir / "itinerary-style-reference.jpg",
    )
    for path in candidates:
        if not path.is_file():
            continue
        data = path.read_bytes()
        return {
            "field_name": "image",
            "filename": sanitize_filename(path.name),
            "content_type": detect_image_mime(data),
            "data": data,
            "role": "style_reference",
        }
    return None


def _itinerary_stop_lines(plan: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for index, stop in enumerate(plan.get("stops", []), start=1):
        if not isinstance(stop, dict) or stop.get("status") != "ok":
            continue
        date = str(stop.get("date") or f"第 {index} 站").strip()
        name = str(stop.get("name") or "").strip()
        transport = str(stop.get("transport") or "").strip()
        note = str(stop.get("note") or "").strip()
        lat = stop.get("lat")
        lng = stop.get("lng")
        suffixes = []
        if transport:
            suffixes.append(f"交通：{transport}")
        if note:
            suffixes.append(f"备注：{note}")
        suffixes.append(f"坐标：lat={lat}, lng={lng}")
        lines.append(f"{index:02d}. {date}｜{name}｜" + "｜".join(suffixes))
    return lines


def _itinerary_position_lock_lines(plan: dict[str, Any], *, width: int, height: int) -> list[str]:
    lines: list[str] = []
    for index, point in enumerate(project_itinerary_points(plan, width=width, height=height), start=1):
        date = str(point.get("date") or f"第 {index} 站").strip()
        name = str(point.get("name") or "").strip()
        lines.append(f"{index:02d}. {date}｜{name}｜锁定像素坐标 x={float(point['x']):.0f}, y={float(point['y']):.0f}")
    return lines


def _itinerary_artwork_prompt(
    plan: dict[str, Any],
    *,
    route_style: str,
    has_style_reference: bool,
    width: int,
    height: int,
) -> str:
    title = str(plan.get("title") or "定制旅行路线图")
    subtitle = str(plan.get("subtitle") or "").strip()
    style_prompts = {
        "comic": (
            "高级水彩漫画旅行路线图，温柔曲线，手绘纸感；风格可轻微靠近古典欧洲航海羊皮纸地图，"
            "有旧地图海岸线、卷轴纸感、罗盘和航线气质，但保持现代高端旅行海报，不要复刻任何游戏或影视 IP。"
        ),
        "premium": "高级旅行杂志手绘路线图，克制色彩，纸张肌理，安静奢华。",
        "classic": "经典手绘羊皮纸旅行路线图，复古墨线，低对比水彩。",
        "dark": "深色高级插画旅行路线图，低亮度地形肌理，文字覆盖区保持干净。",
    }
    style = style_prompts.get(route_style, style_prompts["comic"])
    stop_lines = _itinerary_stop_lines(plan)
    position_lock_lines = _itinerary_position_lock_lines(plan, width=width, height=height)
    control_role = "第二张输入图" if has_style_reference else "输入图"
    style_role = (
        "第一张输入图只是风格参考：学习它的水彩地形、地标小插画、手写感标题氛围和精致纸张质感；"
        "不要复制其中的具体新疆/西班牙地点、边界、文字、路线、编号、清单和 LOGO。\n"
        if has_style_reference
        else ""
    )
    return (
        "请生成一张高级漫画旅行路线图底图。最终路线、编号圆点、日期牌和地点文字会由程序覆盖，"
        "你只负责把地形、国家/地区氛围、城市环境、山河湖海和纸张质感做得高级自然，"
        "不要把控制稿当作可见图层叠上去，不要出现工程草稿、半透明覆盖、粗糙折线或双重地图。\n\n"
        f"标题：{title}\n"
        f"副标题/日期：{subtitle or '按行程日期呈现'}\n"
        f"视觉风格：{style}\n"
        f"{style_role}"
        f"{control_role}是程序按真实经纬度投影出来的硬性地理控制稿：它只用于理解真实区域和构图留白。"
        "请把它转译成精美手绘地图底图，而不是照抄控制稿的线条；可以自然重绘为水彩地形、山脉、湖泊、城市和地标，"
        "但不要在底图里绘制最终路线、编号点、日期牌或站点文字。\n\n"
        "几何位置锁定：请像描图纸一样沿着控制稿理解真实地理结构。每个站点所在区域必须贴近下方锁定像素坐标；"
        "可以美化背景和地形，但不得为了构图、插画或留白移动地点，不能交换东西南北关系。"
        "若风格参考图与锁定像素坐标冲突，必须以锁定像素坐标为准。\n"
        f"锁定像素坐标表（画布 {width}x{height}）：\n{chr(10).join(position_lock_lines)[:5000]}\n\n"
        "编号与站点对应如下，仅用于理解区域、地貌和城市环境；最终文字由程序覆盖，底图里不要手写这些名称：\n"
        f"{chr(10).join(stop_lines)[:7000]}\n\n"
        "成图要求：\n"
        "- 只画高级手绘地图底图、区域纹理、自然地貌、城市氛围、少量不含文字的地标小插画和干净留白。\n"
        "- 不要绘制任何编号圆点、路线线条、日期牌、地点名、交通方式文字、"
        "右侧行程清单或解释文字；这些会由程序准确覆盖。\n"
        "- 不要生成路线图例、Legend、线型说明框、比例尺说明框或左下角说明卡。\n"
        "- 地图背景应像高级旅行定制海报：真实区域轮廓和地貌层次清楚，但表达是水彩漫画，"
        "不是手机导航截图、卫星图、低质 PPT 或技术示意图。\n"
        "- 左上角只保留自然干净留白给官方 6 人游 LOGO；不要绘制 LOGO、LOGO 框、"
        "白底贴纸、占位框、水印、二维码或 OpenAI/API/debug 字样。\n"
        "- 如果参考图和本次目的地不一致，绝不能套用参考图的国家、省份、城市、山河、边界或路线。"
    )


async def _upload_itinerary_reference_images(
    *,
    settings: Settings,
    client: UpstreamClient,
    endpoint_url: str,
    api_key: str,
    parts: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[str], str, list[str]]:
    files_endpoint_url = sibling_endpoint_url(endpoint_url, "files")
    file_ids: list[str] = []
    uploaded_roles: list[str] = []
    try:
        for part in parts:
            upload_response = await client.run_file_upload(
                files_endpoint_url,
                api_key,
                part,
                settings.upstream_user_agent,
            )
            if not isinstance(upload_response, dict):
                raise APIError(HTTPStatus.BAD_GATEWAY, "Files 上传接口返回无效", code="upstream_error")
            image_file_id = str(upload_response.get("id") or "").strip()
            if not image_file_id:
                raise APIError(HTTPStatus.BAD_GATEWAY, "Files 上传接口没有返回 file id", code="upstream_error")
            file_ids.append(image_file_id)
            uploaded_roles.append(str(part.get("role") or "reference"))
        return [{"type": "input_image", "file_id": file_id} for file_id in file_ids], file_ids, "", uploaded_roles
    except APIError as exc:
        content: list[dict[str, str]] = []
        inline_roles: list[str] = []
        skipped_roles: list[str] = []
        for part in parts:
            part_role = str(part.get("role") or "reference")
            data = bytes(part["data"])
            if (
                part_role not in {"geometry_control", "style_reference"}
                and len(data) > ITINERARY_INLINE_REFERENCE_MAX_BYTES
            ):
                skipped_roles.append(part_role)
                continue
            encoded = base64.b64encode(part["data"]).decode("ascii")
            content.append({"type": "input_image", "image_url": f"data:{part['content_type']};base64,{encoded}"})
            inline_roles.append(part_role)
        upload_error = exc.message
        content = [
            *content,
        ]
        log_event(
            logger,
            logging.WARNING,
            "itinerary_reference_upload_fallback",
            status=exc.status,
            message=redact_sensitive_text(exc.message, limit=300),
            inlined_roles=inline_roles,
            skipped_roles=skipped_roles,
        )
        return content, [], upload_error, inline_roles


def _saved_image_as_data_url(saved: dict[str, Any]) -> str:
    image_data_url = str(saved.get("image_data_url") or "").strip()
    if image_data_url.startswith("data:image/"):
        return image_data_url

    image_path_value = str(saved.get("saved_image_path") or "").strip()
    image_mime = str(saved.get("saved_image_mime") or "").strip()
    if not image_path_value or not image_mime.startswith("image/"):
        return ""
    image_path = Path(image_path_value)
    if not image_path.is_file():
        return ""
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{image_mime};base64,{encoded}"


async def _generate_itinerary_artwork(
    *,
    parsed: ItineraryMapRenderRequest,
    plan: dict[str, Any],
    settings: Settings,
    client: UpstreamClient,
    user: AuthUser | None,
    output_size: str,
    composition: dict[str, Any],
) -> dict[str, Any]:
    endpoint_url = validate_url(settings.default_responses_url, "Responses 图像接口 URL")
    api_key = (parsed.api_key or settings.default_api_key).strip()
    if not api_key:
        return {}
    model = settings.default_responses_model.strip() or DEFAULT_RESPONSES_MODEL
    width, height = _parse_itinerary_size(output_size)
    # Pure-Python pixel rendering + zlib over a multi-MB canvas takes seconds of
    # CPU; run it in a worker thread so the event loop keeps serving requests.
    control_png = await anyio.to_thread.run_sync(lambda: render_itinerary_control_png(plan, width=width, height=height))
    control_part = {
        "field_name": "image",
        "filename": "itinerary-geometry-control.png",
        "content_type": "image/png",
        "data": control_png,
        "role": "geometry_control",
    }
    style_part = _itinerary_style_reference_part(settings)
    image_parts = [part for part in (style_part, control_part) if part is not None]
    image_content, image_file_ids, upload_error, included_image_roles = await _upload_itinerary_reference_images(
        settings=settings,
        client=client,
        endpoint_url=endpoint_url,
        api_key=api_key,
        parts=image_parts,
    )
    prompt = _itinerary_artwork_prompt(
        plan,
        route_style=parsed.route_style,
        has_style_reference="style_reference" in included_image_roles,
        width=width,
        height=height,
    )
    content = [{"type": "input_text", "text": append_restricted_destination_guard(prompt)}, *image_content]

    tool: dict[str, Any] = {"type": "image_generation"}
    tool["size"] = output_size
    upstream_payload: dict[str, Any] = {
        "model": model,
        "instructions": ITINERARY_ARTWORK_INSTRUCTIONS,
        **_responses_reasoning_options(model),
        "stream": True,
        "input": [{"role": "user", "content": content}],
        "tools": [tool],
    }
    upstream_response = await client.run_responses(
        endpoint_url,
        api_key,
        upstream_payload,
        settings.upstream_user_agent,
    )
    saved = await _finalize_image_response(
        upstream_response=upstream_response,
        settings=settings,
        client=client,
        save_context={
            "mode": "itinerary",
            "prompt": parsed.title,
            "model": model,
            "endpoint_url": endpoint_url,
            "files_endpoint_url": sibling_endpoint_url(endpoint_url, "files"),
            "transport": "responses-itinerary-artwork",
            "sample_count": 1,
            "logo_requested": parsed.logo_requested,
            "logo_overlay_applied": False,
            "filename_prefix": user.username if user else "",
            "route_style": parsed.route_style,
            "size": f"{width}x{height}",
            "requested_size": composition["requested_size"],
            "composition": composition,
            "itinerary_title": parsed.title,
            "itinerary_subtitle": parsed.subtitle,
            "itinerary_artwork_mode": "ai_background_source",
            "itinerary_control_sketch_bytes": len(control_png),
            "itinerary_style_reference": str(style_part.get("filename") if style_part else ""),
            "source_image_names": [str(part["filename"]) for part in image_parts],
            "source_image_roles": [
                "style_reference" if part is style_part else "geometry_control" for part in image_parts
            ],
            "source_image_count": len(image_parts),
            "source_file_ids": image_file_ids,
            "included_source_image_roles": included_image_roles,
            "file_upload_fallback": bool(upload_error),
            "file_upload_error": upload_error,
            **_user_metadata(user),
        },
        extra={
            "mode": "itinerary",
            "prompt": parsed.title,
            "model": model,
            "transport": "responses-itinerary-artwork",
            "size": f"{width}x{height}",
            "requested_size": composition["requested_size"],
            "composition": composition,
            "logo_requested": parsed.logo_requested,
            "logo_overlay_applied": False,
            "endpoint_url": endpoint_url,
            "files_endpoint_url": sibling_endpoint_url(endpoint_url, "files"),
            "source_file_ids": image_file_ids,
            "included_source_image_roles": included_image_roles,
            "file_upload_fallback": bool(upload_error),
        },
    )
    image_data_url = str(saved.get("image_data_url") or "")
    if not saved.get("saved_image_url") and not image_data_url:
        raise APIError(
            HTTPStatus.BAD_GATEWAY,
            "路线图生成接口没有返回可保存的图片",
            compact_raw_response(upstream_response),
            code="upstream_no_image",
        )
    image_mime = str(saved.get("saved_image_mime") or "")
    if (image_mime and not image_mime.startswith("image/")) or (
        image_data_url and not image_data_url.startswith("data:image/")
    ):
        raise APIError(
            HTTPStatus.BAD_GATEWAY,
            "路线图生成失败：上游返回的图片格式无效，请稍后重试",
            f"上游返回的图片格式无效：mime={image_mime or 'inline-data-url'}",
            code="upstream_error",
        )
    background_data_url = await anyio.to_thread.run_sync(lambda: _saved_image_as_data_url(saved))
    if not background_data_url:
        raise APIError(
            HTTPStatus.BAD_GATEWAY,
            "路线图生成接口没有返回可用的底图",
            compact_raw_response(upstream_response),
            code="upstream_error",
        )

    svg_text = render_itinerary_map_svg(
        plan,
        width=width,
        height=height,
        background_image_url=background_data_url,
        logo_href="",
        reserve_logo_area=parsed.logo_requested,
    )
    overlay = await anyio.to_thread.run_sync(
        lambda: save_itinerary_map_svg(
            data_dir=settings.data_dir,
            outputs_dir=settings.outputs_dir,
            svg_text=svg_text,
            filename_prefix=user.username if user else "",
            metadata={
                "mode": "itinerary",
                "prompt": parsed.title,
                "model": model,
                "transport": "responses-itinerary-artwork",
                "route_style": parsed.route_style,
                "size": f"{width}x{height}",
                "requested_size": composition["requested_size"],
                "composition": composition,
                "artwork_generated": True,
                "artwork_mode": "ai_background_program_overlay",
                "ai_background_image_path": str(saved.get("saved_image_path") or ""),
                "ai_background_image_url": str(saved.get("saved_image_url") or ""),
                "ai_background_image_mime": str(saved.get("saved_image_mime") or ""),
                "logo_requested": parsed.logo_requested,
                "logo_overlay_applied": False,
                "stop_count": len(plan.get("stops", [])),
                "source_image_names": [str(part["filename"]) for part in image_parts],
                "source_image_roles": [
                    "style_reference" if part is style_part else "geometry_control" for part in image_parts
                ],
                "source_image_count": len(image_parts),
                "source_file_ids": image_file_ids,
                "included_source_image_roles": included_image_roles,
                "file_upload_fallback": bool(upload_error),
                "file_upload_error": upload_error,
                **_user_metadata(user),
            },
            width=width,
            height=height,
        )
    )
    image = {
        **overlay,
        "candidate_index": 0,
        "mode": "itinerary",
        "model": model,
        "prompt": parsed.title,
        "logo_overlay_applied": False,
    }
    return {
        **image,
        "transport": "responses-itinerary-artwork",
        "size": f"{width}x{height}",
        "requested_size": composition["requested_size"],
        "composition": composition,
        "logo_requested": parsed.logo_requested,
        "logo_overlay_applied": False,
        "endpoint_url": endpoint_url,
        "files_endpoint_url": sibling_endpoint_url(endpoint_url, "files"),
        "source_file_ids": image_file_ids,
        "included_source_image_roles": included_image_roles,
        "file_upload_fallback": bool(upload_error),
        "ai_background_image_path": str(saved.get("saved_image_path") or ""),
        "ai_background_image_url": str(saved.get("saved_image_url") or ""),
        "ai_background_image_mime": str(saved.get("saved_image_mime") or ""),
        "candidate_count": 1,
        "images": [image],
    }


def _itinerary_coordinate_prompt(plan: dict[str, Any]) -> str:
    stops = [stop for stop in plan.get("stops", []) if isinstance(stop, dict)]
    route_lines: list[str] = []
    unresolved_lines: list[str] = []
    for stop in stops:
        index = int(stop.get("index") or 0)
        date = str(stop.get("date") or "").strip() or f"第 {index + 1} 站"
        name = str(stop.get("name") or "").strip()
        transport = str(stop.get("transport") or "").strip()
        note = str(stop.get("note") or "").strip()
        status = str(stop.get("status") or "")
        lat = stop.get("lat")
        lng = stop.get("lng")
        suffix = f"，交通：{transport}" if transport else ""
        note_suffix = f"，说明：{note}" if note else ""
        if status == "ok" and isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            route_lines.append(f"- index={index}，{date}，{name}，已知坐标 lat={lat}, lng={lng}{suffix}{note_suffix}")
        else:
            line = f"- index={index}，{date}，{name}{suffix}{note_suffix}"
            route_lines.append(line)
            unresolved_lines.append(line)
    return (
        "你是严谨的旅行路线图地理坐标助手。请根据行程标题、日期、所有站点上下文，为未确认坐标的地点给出大概经纬度。"
        "不需要门牌级精确，城市、景区、岛屿、国家区域中心点或常见旅行落点即可，但必须保持真实相对位置，"
        "不能把不同城市、省份、国家或南北东西关系颠倒。遇到酒店/民宿/小众地点无法确认时，使用其所在城市、景区或地区的大概坐标。\n\n"
        f"{RESTRICTED_DESTINATION_GUARD_TEXT}\n\n"
        f"标题：{plan.get('title') or '定制旅行路线图'}\n"
        f"副标题/日期：{plan.get('subtitle') or '未提供'}\n"
        "完整路线节点：\n"
        f"{chr(10).join(route_lines)[:6000]}\n\n"
        "需要估算坐标的节点：\n"
        f"{chr(10).join(unresolved_lines)[:3000]}\n\n"
        "只返回 JSON 数组，不要 Markdown，不要解释。index 是上面节点里的从 0 开始的 index，不要改成从 1 开始。"
        "数组每一项格式："
        '{"index":0,"name":"地点名","country":"国家或地区","lat":31.2304,"lng":121.4737,'
        '"confidence":0.58,"note":"使用城市中心大概坐标"}。'
        "index 必须使用上面给出的 index；lat/lng 必须是数字；confidence 取 0 到 1；"
        "country 使用简短中文国家/地区名。"
    )


def _json_candidates_from_text(text: str) -> list[Any]:
    stripped = text.strip()
    if not stripped:
        return []
    candidates: list[str] = [stripped]
    array_start = stripped.find("[")
    array_end = stripped.rfind("]")
    if 0 <= array_start < array_end:
        candidates.append(stripped[array_start : array_end + 1])
    object_start = stripped.find("{")
    object_end = stripped.rfind("}")
    if 0 <= object_start < object_end:
        candidates.append(stripped[object_start : object_end + 1])

    parsed_candidates: list[Any] = []
    for candidate in candidates:
        try:
            parsed_candidates.append(json.loads(candidate))
        except json.JSONDecodeError:
            continue
    return parsed_candidates


def _parse_itinerary_coordinate_estimates(text: str) -> list[dict[str, Any]]:
    for parsed in _json_candidates_from_text(text):
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            for key in ("stops", "coordinates", "items", "data"):
                items = parsed.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
            return [parsed]
    return []


async def _complete_itinerary_plan_with_ai_coordinates(
    *,
    parsed: ItineraryMapRenderRequest,
    plan: dict[str, Any],
    settings: Settings,
    client: UpstreamClient,
    user: AuthUser | None,
) -> dict[str, Any]:
    if plan.get("status") == "ready":
        return plan
    endpoint_url = validate_url(settings.default_responses_url, "Responses 文本接口 URL")
    api_key = (parsed.api_key or settings.default_api_key).strip()
    if not api_key:
        return plan

    model = settings.default_responses_model.strip() or DEFAULT_RESPONSES_MODEL
    upstream_payload = {
        "model": model,
        "instructions": ITINERARY_COORDINATE_INSTRUCTIONS,
        **_responses_reasoning_options(model),
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": _itinerary_coordinate_prompt(plan),
                    }
                ],
            }
        ],
    }
    try:
        upstream_response = await client.run_responses(
            endpoint_url,
            api_key,
            upstream_payload,
            settings.upstream_user_agent,
        )
    except APIError as exc:
        log_event(
            logger,
            logging.WARNING,
            "itinerary_ai_coordinate_estimation_failed",
            status=exc.status,
            code=exc.code,
            message=redact_sensitive_text(exc.message, limit=300),
            user_id=user.id if user else None,
            username=user.username if user else "",
        )
        return plan
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "itinerary_ai_coordinate_estimation_failed",
            error=redact_sensitive_text(str(exc), limit=300),
            user_id=user.id if user else None,
            username=user.username if user else "",
        )
        return plan

    estimates = [
        estimate
        for estimate in _parse_itinerary_coordinate_estimates(_extract_text_output(upstream_response))
        if not stop_has_restricted_destination(estimate)
    ]
    completed = apply_itinerary_coordinate_estimates(plan, estimates, source="ai_approximate")
    log_event(
        logger,
        logging.INFO if completed.get("status") == "ready" else logging.WARNING,
        "itinerary_ai_coordinate_estimation_completed",
        status=completed.get("status"),
        estimate_count=len(estimates),
        unresolved_count=len(
            [stop for stop in completed.get("stops", []) if isinstance(stop, dict) and stop.get("status") != "ok"]
        ),
        user_id=user.id if user else None,
        username=user.username if user else "",
    )
    return completed


async def handle_itinerary_map_render(
    body: Any, settings: Settings, client: UpstreamClient, user: AuthUser | None = None
) -> dict[str, Any]:
    # When auth is enabled, require_current_user has already rejected anonymous
    # callers with 401 — user is None here only in auth-disabled deployments,
    # where itinerary maps must work like generate/edit do.
    if settings.auth_enabled and user is None:
        raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
    payload = _ensure_dict(body)
    parsed = _validate_request(ItineraryMapRenderRequest, payload)
    _ensure_itinerary_request_has_no_restricted_destination(parsed)
    plan = await build_itinerary_map_plan_async(
        title=parsed.title,
        subtitle=parsed.subtitle,
        route_style=parsed.route_style,
        stops=[stop.model_dump() for stop in parsed.stops],
        geocode=lambda name: geocode_place_with_settings(name, settings),
    )
    if plan["status"] != "ready":
        plan = await _complete_itinerary_plan_with_ai_coordinates(
            parsed=parsed,
            plan=plan,
            settings=settings,
            client=client,
            user=user,
        )
    if plan["status"] != "ready":
        raise APIError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "路线图仍有地点无法自动定位，暂时不能生成准确路线图",
            "\n".join(str(item) for item in plan.get("warnings", [])),
            code="itinerary_coordinates_required",
        )

    composition = _choose_itinerary_output_size(plan, parsed.size)
    width = int(composition["width"])
    height = int(composition["height"])
    output_size = str(composition["selected_size"])
    api_key = (parsed.api_key or settings.default_api_key).strip()
    artwork_fallback_error = ""
    if parsed.generate_background and not parsed.background_image_url and api_key:
        try:
            artwork = await _generate_itinerary_artwork(
                parsed=parsed,
                plan=plan,
                settings=settings,
                client=client,
                user=user,
                output_size=output_size,
                composition=composition,
            )
        except APIError as exc:
            if exc.code != "upstream_no_image":
                raise
            log_event(
                logger,
                logging.WARNING,
                "itinerary_artwork_no_image",
                message=redact_sensitive_text(exc.message, limit=300),
                details=redact_sensitive_text(str(exc.details or ""), limit=500),
                user_id=user.id if user else None,
                username=user.username if user else "",
            )
            raise APIError(
                HTTPStatus.BAD_GATEWAY,
                "路线图 AI 底图这次没有生成成功，请稍后重试",
                "Responses image generation completed without a usable image output.",
                code="upstream_no_image",
            ) from exc
        except (OSError, ValueError, binascii.Error) as exc:
            log_event(
                logger,
                logging.WARNING,
                "itinerary_artwork_generation_failed",
                error=redact_sensitive_text(str(exc), limit=300),
            )
            raise APIError(
                HTTPStatus.BAD_GATEWAY,
                "路线图生成失败：上游返回的图片无效，请稍后重试",
                f"{type(exc).__name__}: {exc}",
                code="upstream_error",
            ) from exc
        else:
            artwork["candidate_index"] = 0
            artwork["mode"] = "itinerary"
            artwork["prompt"] = parsed.title
            artwork["logo_requested"] = parsed.logo_requested
            artwork["logo_overlay_applied"] = False
            return {
                "requested_size": composition["requested_size"],
                "size": output_size,
                "composition": composition,
                "plan": plan,
                "artwork": {
                    "generated": True,
                    "mode": "ai_background_program_overlay",
                    "model": str(artwork.get("model") or ""),
                    "image_mime": str(artwork.get("saved_image_mime") or ""),
                },
                "background_image": {
                    "generated": True,
                    "mode": "ai_background_program_overlay",
                    "model": str(artwork.get("model") or ""),
                    "image_mime": str(artwork.get("ai_background_image_mime") or ""),
                    "error": "",
                },
                **artwork,
            }

    try:
        svg_text = render_itinerary_map_svg(
            plan,
            width=width,
            height=height,
            background_image_url=parsed.background_image_url,
            logo_href="",
            reserve_logo_area=parsed.logo_requested,
        )
        saved = await anyio.to_thread.run_sync(
            lambda: save_itinerary_map_svg(
                data_dir=settings.data_dir,
                outputs_dir=settings.outputs_dir,
                svg_text=svg_text,
                filename_prefix=user.username if user else "",
                metadata={
                    **_user_metadata(user),
                    "mode": "itinerary",
                    "prompt": parsed.title,
                    "route_style": parsed.route_style,
                    "size": output_size,
                    "requested_size": composition["requested_size"],
                    "composition": composition,
                    "background_image_url": parsed.background_image_url,
                    "artwork_generated": False,
                    "artwork_mode": "program_svg_fallback",
                    "artwork_fallback_error": artwork_fallback_error,
                    "logo_requested": parsed.logo_requested,
                    "logo_overlay_applied": False,
                    "stop_count": len(parsed.stops),
                },
                width=width,
                height=height,
            )
        )
    except (OSError, ValueError, binascii.Error) as exc:
        raise APIError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc), code="itinerary_coordinates_required") from exc
    saved["candidate_index"] = 0
    saved["mode"] = "itinerary"
    saved["model"] = "program-itinerary-map"
    saved["prompt"] = parsed.title
    saved["logo_overlay_applied"] = False
    return {
        "mode": "itinerary",
        "prompt": parsed.title,
        "model": "program-itinerary-map",
        "transport": "program-itinerary-map",
        "requested_size": composition["requested_size"],
        "size": output_size,
        "composition": composition,
        "logo_requested": parsed.logo_requested,
        "logo_overlay_applied": False,
        "candidate_count": 1,
        "images": [saved],
        "plan": plan,
        "artwork": {
            "generated": False,
            "mode": "program_svg_fallback",
            "model": "",
            "image_mime": saved.get("saved_image_mime", ""),
        },
        "background_image": {
            "generated": False,
            "mode": "program_svg_fallback",
            "model": "",
            "image_mime": saved.get("saved_image_mime", ""),
            "error": artwork_fallback_error,
        },
        **saved,
    }


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/config", response_model=ConfigResponse)
    async def config(request: Request) -> ConfigResponse:
        settings = get_settings(request)
        return ConfigResponse(
            generate_url=settings.default_generate_url,
            edit_url=settings.default_edit_url,
            responses_url=settings.default_responses_url,
            default_model=settings.default_model,
            default_responses_model=settings.default_responses_model,
            default_size=settings.default_size,
            has_default_api_key=bool(settings.default_api_key),
            storage_dir=str(settings.outputs_dir),
            max_image_bytes=settings.max_image_bytes,
            max_request_body_bytes=settings.max_request_body_bytes,
            rate_limit_per_minute=settings.rate_limit_per_minute,
            upstream_timeout_seconds=settings.upstream_timeout_seconds,
            auth_enabled=settings.auth_enabled,
            bug_report_notifications_enabled=admin_notifications_enabled(settings),
            error_alert_notifications_enabled=error_alert_notifications_enabled(settings),
            password_reset_email_enabled=smtp_notifications_enabled(settings)
            and _password_reset_email_can_include_link(settings),
            map_provider=_public_map_provider(settings),
            map_geocoding_enabled=_map_geocoding_enabled(settings),
        )

    @router.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(ok=True)

    @router.get("/api/ready", response_model=ReadinessResponse)
    async def ready(
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
    ) -> ReadinessResponse:
        storage_ok = True
        try:
            settings.outputs_dir.mkdir(parents=True, exist_ok=True)
            probe = settings.outputs_dir / ".ready"
            probe.write_text("ok")
            probe.unlink(missing_ok=True)
        except Exception:
            storage_ok = False
        return ReadinessResponse(
            ok=storage_ok and client is not None,
            storage_writable=storage_ok,
            upstream_client_ready=client is not None,
            version=__version__,
        )

    @router.get("/api/recipes")
    async def recipes(
        user: AuthUser | None = Depends(require_current_user),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        if settings.auth_enabled and user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        return {"recipes": list_prompt_recipes()}

    @router.get("/api/success-templates")
    async def success_templates(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        templates = await anyio.to_thread.run_sync(lambda: auth_store.list_success_templates_for_user(user_id=user.id))
        return {"templates": templates}

    @router.get("/files/{relative_path:path}")
    async def files(
        relative_path: str,
        request: Request,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> FileResponse:
        settings = get_settings(request)
        target_path = _resolve_served_file(settings, relative_path)
        if not target_path.is_file():
            raise APIError(HTTPStatus.NOT_FOUND, "文件不存在", code="not_found")
        if settings.auth_enabled and relative_path.startswith("outputs/") and target_path.suffix.lower() != ".json":
            await anyio.to_thread.run_sync(
                lambda: auth_store.record_image_delivery(
                    relative_path=relative_path,
                    user_id=user.id if user else None,
                    status_code=200,
                    client_host=request.client.host if request.client else "",
                    user_agent=request.headers.get("user-agent", ""),
                )
            )
        # Output filenames embed a UUID, so they are safely immutable. Avatar
        # filenames are deterministic per user (same URL after re-upload) — an
        # immutable year-long cache would show the old avatar forever.
        if relative_path.startswith("avatars/"):
            cache_control = "private, no-cache"
        else:
            cache_control = "private, max-age=31536000, immutable"
        return FileResponse(
            target_path,
            headers={"Cache-Control": cache_control},
        )

    @router.post("/api/auth/register")
    async def register(
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> JSONResponse:
        payload = _ensure_dict(body)
        parsed = _validate_request(AuthRequest, payload)
        try:
            normalize_username(parsed.username)
            _ensure_self_service_username_allowed(parsed.username, settings)
            user = await anyio.to_thread.run_sync(
                lambda: auth_store.create_user(
                    parsed.username,
                    parsed.password,
                    company=parsed.company,
                    department=parsed.department,
                )
            )
        except UserExistsError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "用户名已存在", code="user_exists") from exc
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        return await anyio.to_thread.run_sync(
            lambda: _auth_response(settings=settings, auth_store=auth_store, user=user)
        )

    @router.post("/api/auth/login")
    async def login(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> JSONResponse:
        payload = _ensure_dict(body)
        parsed = _validate_request(AuthRequest, payload)
        await _ensure_admin_bootstrap(request, settings, auth_store)
        try:
            user = await anyio.to_thread.run_sync(auth_store.authenticate, parsed.username, parsed.password)
        except AccountLockedError as exc:
            raise APIError(
                HTTPStatus.TOO_MANY_REQUESTS,
                "登录失败次数过多，请稍后再试",
                code="account_locked",
            ) from exc
        except (InvalidCredentialsError, ValueError) as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "用户名或密码错误", code="invalid_credentials") from exc
        return await anyio.to_thread.run_sync(
            lambda: _auth_response(settings=settings, auth_store=auth_store, user=user)
        )

    @router.post("/api/password-reset-requests")
    async def password_reset_request(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        payload = _ensure_dict(body)
        parsed = _validate_request(PasswordResetRequest, payload)
        reset_request: dict[str, Any] | None = None
        with suppress(ValueError):
            reset_request = await anyio.to_thread.run_sync(
                lambda: auth_store.request_password_reset(
                    parsed.username,
                    client_host=request.client.host if request.client else "",
                    user_agent=request.headers.get("user-agent", ""),
                    token_expires_at=_password_reset_expires_at(settings),
                )
            )
        if reset_request is not None:
            email_sent = False
            reset_notification_info = reset_request
            if reset_request.get("notification_suppressed"):
                return {"status": "ok", "message": PASSWORD_RESET_REQUEST_MESSAGE}
            if reset_request.get("email_available") and reset_request.get("reset_token"):
                can_send_reset_email = smtp_notifications_enabled(
                    settings
                ) and _password_reset_email_can_include_link(settings)
                if smtp_notifications_enabled(settings) and not _password_reset_email_can_include_link(settings):
                    reset_notification_info = _safe_admin_reset_request_info(reset_request)
                    log_event(
                        logger,
                        logging.WARNING,
                        "password_reset_email_public_base_url_missing",
                        username=redact_sensitive_text(str(reset_request.get("username_normalized") or ""), limit=80),
                    )
                elif can_send_reset_email:
                    reset_url = _password_reset_url(request, settings, str(reset_request["reset_token"]))
                    email_result = await anyio.to_thread.run_sync(
                        lambda: send_password_reset_email(
                            settings=settings,
                            to_email=str(reset_request.get("email") or ""),
                            username=str(reset_request.get("username") or ""),
                            reset_url=reset_url,
                            expires_minutes=settings.password_reset_token_minutes,
                        )
                    )
                    if email_result.sent:
                        email_sent = True
                        await anyio.to_thread.run_sync(
                            lambda: auth_store.mark_password_reset_email_sent(int(reset_request["id"]))
                        )
                    elif email_result.configured:
                        log_event(
                            logger,
                            logging.WARNING,
                            "password_reset_email_failed",
                            status=email_result.status,
                            error=email_result.error,
                        )
                else:
                    reset_notification_info = _safe_admin_reset_request_info(reset_request)
            if not email_sent:
                _spawn_notification_task(
                    _notify_password_reset_request(settings, reset_notification_info)
                )
        return {"status": "ok", "message": PASSWORD_RESET_REQUEST_MESSAGE}

    @router.post("/api/password-reset/confirm")
    async def confirm_password_reset(
        body: Any = JSON_BODY,
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        payload = _ensure_dict(body)
        parsed = _validate_request(PasswordResetConfirmRequest, payload)
        updated_user = await anyio.to_thread.run_sync(
            lambda: auth_store.reset_password_with_token(token=parsed.token, password=parsed.password)
        )
        if updated_user is None:
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "重置链接无效或已过期，请重新申请。",
                code="invalid_reset_token",
            )
        return {"status": "ok", "message": "密码已重置，请使用新密码登录。"}

    @router.post("/api/auth/logout")
    async def logout(
        request: Request,
        settings: Settings = Depends(get_settings),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> JSONResponse:
        token = _get_session_token(request, settings)
        await anyio.to_thread.run_sync(auth_store.delete_session, token)
        response = JSONResponse({"status": "ok"})
        _clear_auth_cookie(response, settings)
        return response

    @router.get("/api/me")
    async def me(user: AuthUser | None = Depends(require_current_user)) -> dict[str, Any]:
        return {"user": user.public_dict() if user else None}

    @router.get("/api/image-stats")
    async def image_stats(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        stats = await anyio.to_thread.run_sync(lambda: auth_store.image_count_stats(user_id=user.id))
        return {"stats": stats}

    @router.put("/api/me/password")
    async def change_my_password(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(ChangePasswordRequest, payload)
        try:
            updated_user = await anyio.to_thread.run_sync(
                lambda: auth_store.change_user_password(
                    user_id=user.id,
                    current_password=parsed.current_password,
                    new_password=parsed.new_password,
                    current_session_token=_get_session_token(request, settings),
                )
            )
        except InvalidCredentialsError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "当前密码不正确", code="invalid_credentials") from exc
        return {"status": "ok", "user": updated_user.public_dict()}

    @router.put("/api/me/profile")
    async def update_my_profile(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(UserProfileRequest, payload)
        normalized_current = normalize_username(user.username)
        normalized_next = normalize_username(parsed.username)
        if normalized_next != normalized_current:
            _ensure_self_service_username_allowed(parsed.username, settings)
        if normalized_next != normalized_current and not parsed.current_password:
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "修改登录用户名需要填写当前密码",
                code="current_password_required",
            )
        try:
            updated_user = await anyio.to_thread.run_sync(
                lambda: auth_store.update_user_profile(
                    user_id=user.id,
                    username=parsed.username,
                    current_password=parsed.current_password,
                    display_name=parsed.display_name,
                    wechat=parsed.wechat,
                    phone_country_code=parsed.phone_country_code,
                    phone=parsed.phone,
                    email=parsed.email,
                    company=parsed.company,
                    department=parsed.department,
                    team=parsed.team,
                    job_title=parsed.job_title,
                    note=parsed.note,
                    current_session_token=_get_session_token(request, settings),
                )
            )
        except UserExistsError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "用户名已存在", code="user_exists") from exc
        except InvalidCredentialsError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "当前密码不正确", code="invalid_credentials") from exc
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        return {"status": "ok", "user": updated_user.public_dict()}

    @router.post("/api/me/avatar")
    async def update_my_avatar(
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(AvatarUploadRequest, payload)
        image_bytes = parsed.image.decoded_bytes()
        if not image_bytes:
            raise APIError(HTTPStatus.BAD_REQUEST, "头像文件不能为空", code="bad_request")
        max_avatar_bytes = 2 * 1024 * 1024
        if len(image_bytes) > max_avatar_bytes:
            raise APIError(HTTPStatus.BAD_REQUEST, "头像文件不能超过 2 MB", code="bad_request")
        image_mime = detect_image_mime(image_bytes)
        if image_mime not in {"image/png", "image/jpeg", "image/webp"}:
            raise APIError(HTTPStatus.BAD_REQUEST, "头像仅支持 PNG、JPG 或 WebP", code="bad_request")
        avatar_path, avatar_url = await anyio.to_thread.run_sync(
            lambda: _save_user_avatar(
                settings=settings,
                user=user,
                image_bytes=image_bytes,
                image_mime=image_mime,
            )
        )
        updated_user = await anyio.to_thread.run_sync(
            lambda: auth_store.update_user_avatar(
                user_id=user.id,
                avatar_path=str(avatar_path),
                avatar_url=avatar_url,
            )
        )
        if updated_user is None:
            raise APIError(HTTPStatus.NOT_FOUND, "用户不存在", code="not_found")
        return {"status": "ok", "user": updated_user.public_dict()}

    @router.get("/api/preferences")
    async def get_preferences(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        preferences = await anyio.to_thread.run_sync(lambda: auth_store.get_user_preferences(user_id=user.id))
        return {"preferences": preferences}

    @router.put("/api/preferences")
    async def update_preferences(
        body: Any = JSON_BODY,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(UserPreferencesRequest, payload)
        responses_model = _normalize_legacy_client_responses_model(
            parsed.default_responses_model,
            storage_version=parsed.responses_model_storage_version,
            default_model=settings.default_responses_model,
        )
        preferences = await anyio.to_thread.run_sync(
            lambda: auth_store.update_user_preferences(
                user_id=user.id,
                default_model=parsed.default_model,
                default_responses_model=responses_model,
                default_size=parsed.default_size,
                default_quality=parsed.default_quality,
                default_output_format=parsed.default_output_format,
                default_image_transport=parsed.default_image_transport,
                logo_overlay_enabled=parsed.logo_overlay_enabled,
                auto_copyright_check_enabled=parsed.auto_copyright_check_enabled,
            )
        )
        return {"status": "ok", "preferences": preferences}

    @router.get("/api/users")
    async def users(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        users = await anyio.to_thread.run_sync(lambda: auth_store.list_active_users(exclude_user_id=user.id))
        if user.is_admin:
            return {"users": users}
        return {
            "users": [
                {
                    "id": listed_user["id"],
                    "username": listed_user["username"],
                    "display_name": listed_user.get("display_name", ""),
                    "avatar_url": listed_user.get("avatar_url", ""),
                }
                for listed_user in users
            ]
        }

    @router.get("/api/org-units")
    async def public_org_units(
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        org_units = await anyio.to_thread.run_sync(auth_store.list_organization_units)
        return {"org_units": org_units}

    @router.get("/api/team-chat/members")
    async def team_chat_members(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        members = await anyio.to_thread.run_sync(lambda: auth_store.list_team_chat_members(current_user_id=user.id))
        group = await anyio.to_thread.run_sync(lambda: auth_store.team_chat_group_for_user(user.id))
        bot = next((member for member in members if member.get("type") == "bot"), None)
        human_members = [member for member in members if member.get("type") != "bot"]
        return {
            "members": members,
            "human_members": human_members,
            "bot": bot,
            "group": {
                "company": group["company"],
                "department": group["department"],
                "room_key": group["room_key"],
                "title": team_chat_group_title(group["company"], group["department"]),
                "subtitle": team_chat_group_subtitle(group["company"]),
                "member_count": len(human_members),
            },
        }

    @router.get("/api/team-chat/messages")
    async def team_chat_messages(
        room_type: str = "team",
        recipient_user_id: int | None = None,
        after_id: int = 0,
        limit: int = 100,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        try:
            room_key = await anyio.to_thread.run_sync(
                lambda: auth_store.team_chat_room_key(
                    current_user_id=user.id,
                    room_type=room_type,
                    recipient_user_id=recipient_user_id,
                )
            )
            messages = await anyio.to_thread.run_sync(
                lambda: auth_store.list_team_chat_messages(
                    room_key=room_key,
                    limit=limit,
                    after_id=after_id,
                )
            )
        except (ValueError, OverflowError) as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        return {"room_key": room_key, "messages": messages}

    @router.post("/api/team-chat/messages")
    async def create_team_chat_message(
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(TeamChatMessageRequest, payload)
        try:
            room_key = await anyio.to_thread.run_sync(
                lambda: auth_store.team_chat_room_key(
                    current_user_id=user.id,
                    room_type=parsed.room_type,
                    recipient_user_id=parsed.recipient_user_id,
                )
            )
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        mentions = _parse_team_chat_mentions(parsed.content)
        created = await anyio.to_thread.run_sync(
            lambda: auth_store.create_team_chat_message(
                room_key=room_key,
                room_type=parsed.room_type,
                sender_user_id=user.id,
                sender_type="user",
                sender_name=_team_chat_display_name(user),
                content=parsed.content,
                mentions=mentions,
            )
        )
        await anyio.to_thread.run_sync(
            lambda: auth_store.mark_team_chat_read(
                user_id=user.id,
                room_key=room_key,
                message_id=int(created["id"]),
            )
        )
        messages = [created]
        should_reply = parsed.room_type == "bot" or (
            parsed.room_type == "team" and _team_chat_bot_was_mentioned(parsed.content, mentions)
        )
        if should_reply:
            recent_messages = await anyio.to_thread.run_sync(
                lambda: auth_store.list_team_chat_messages(room_key=room_key, limit=40)
            )
            _schedule_team_chat_bot_reply(
                auth_store=auth_store,
                settings=settings,
                client=client,
                user=user,
                room_key=room_key,
                room_type=parsed.room_type,
                content=parsed.content,
                recent_messages=recent_messages,
            )
        return {
            "status": "ok",
            "room_key": room_key,
            "messages": messages,
            "bot_reply_pending": should_reply,
        }

    @router.post("/api/team-chat/read")
    async def mark_team_chat_read(
        body: Any = JSON_BODY,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(TeamChatReadRequest, payload)
        try:
            room_key = await anyio.to_thread.run_sync(
                lambda: auth_store.team_chat_room_key(
                    current_user_id=user.id,
                    room_type=parsed.room_type,
                    recipient_user_id=parsed.recipient_user_id,
                )
            )
            read = await anyio.to_thread.run_sync(
                lambda: auth_store.mark_team_chat_read(
                    user_id=user.id,
                    room_key=room_key,
                    message_id=parsed.message_id,
                )
            )
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        return {"status": "ok", "read": read}

    @router.get("/api/team-chat/unread")
    async def team_chat_unread(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        unread = await anyio.to_thread.run_sync(lambda: auth_store.team_chat_unread_summary(user_id=user.id))
        return {"unread": unread}

    @router.get("/api/team-chat/group-announcement")
    async def team_chat_group_announcement(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        announcement = await anyio.to_thread.run_sync(lambda: auth_store.get_group_announcement(user_id=user.id))
        return {"announcement": announcement}

    @router.put("/api/team-chat/group-announcement")
    async def update_team_chat_group_announcement(
        body: Any = JSON_BODY,
        admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        payload = _ensure_dict(body)
        parsed = _validate_request(GroupAnnouncementRequest, payload)
        try:
            announcement = await anyio.to_thread.run_sync(
                lambda: auth_store.upsert_group_announcement(
                    company=parsed.company,
                    department=parsed.department,
                    content=parsed.content,
                    actor_user_id=admin.id,
                )
            )
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        return {"status": "ok", "announcement": announcement}

    @router.get("/api/team-chat/group-assets")
    async def team_chat_group_assets(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        assets = await anyio.to_thread.run_sync(lambda: auth_store.list_group_saved_items(user_id=user.id))
        return {"assets": assets}

    @router.post("/api/team-chat/group-assets")
    async def save_team_chat_group_asset(
        body: Any = JSON_BODY,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(GroupSavedItemRequest, payload)
        try:
            asset = await anyio.to_thread.run_sync(
                lambda: auth_store.save_group_item(
                    user_id=user.id,
                    generated_image_id=parsed.generated_image_id,
                    title=parsed.title,
                    note=parsed.note,
                )
            )
        except PermissionError as exc:
            raise APIError(HTTPStatus.FORBIDDEN, str(exc), code="forbidden") from exc
        return {"status": "ok", "asset": asset}

    @router.get("/api/team-chat/group-stats")
    async def team_chat_group_stats(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        stats = await anyio.to_thread.run_sync(lambda: auth_store.group_stats(user_id=user.id))
        return {"stats": stats}

    @router.get("/api/team-chat/group-summary")
    async def team_chat_group_summary(
        days: int = 7,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        summary = await anyio.to_thread.run_sync(lambda: auth_store.group_summary(user_id=user.id, days=days))
        return {"summary": summary}

    @router.get("/api/gallery")
    async def gallery(
        q: str = "",
        tag: str = "",
        favorite: bool = False,
        scope: str = "self",
        limit: int = 60,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        clean_scope = scope.strip().lower()
        target_user_id = None if user.is_admin and clean_scope == "all" else user.id
        items = await anyio.to_thread.run_sync(
            lambda: auth_store.list_gallery_items(
                viewer_user_id=user.id,
                target_user_id=target_user_id,
                query=q,
                tag=tag,
                favorite_only=favorite,
                limit=limit,
            )
        )
        return {
            "scope": "all" if target_user_id is None else "self",
            "count": len(items),
            "items": items,
        }

    @router.get("/api/jobs")
    async def generation_jobs(
        limit: int = 30,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        jobs = await anyio.to_thread.run_sync(
            lambda: auth_store.list_generation_jobs_for_user(user_id=user.id, limit=limit)
        )
        return {"scope": "self", "count": len(jobs), "jobs": jobs}

    @router.get("/api/generated-images/{generated_image_id}")
    async def generated_image_detail(
        generated_image_id: int,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        image = await anyio.to_thread.run_sync(
            lambda: auth_store.generated_image_detail_for_user(
                generated_image_id=generated_image_id,
                user_id=user.id,
            )
        )
        if image is None:
            raise APIError(HTTPStatus.NOT_FOUND, "图片不存在或无权查看", code="not_found")
        return {"image": image}

    @router.get("/api/generated-images/{generated_image_id}/versions")
    async def generated_image_versions(
        generated_image_id: int,
        limit: int = 200,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        versions = await anyio.to_thread.run_sync(
            lambda: auth_store.list_generated_image_versions_for_user(
                generated_image_id=generated_image_id,
                user_id=user.id,
                limit=limit,
            )
        )
        if versions is None:
            raise APIError(HTTPStatus.NOT_FOUND, "图片不存在或无权查看", code="not_found")
        return {
            "current_generated_image_id": generated_image_id,
            "count": len(versions),
            "versions": versions,
        }

    @router.put("/api/gallery/{generated_image_id}")
    async def update_gallery_item(
        generated_image_id: int,
        body: Any = JSON_BODY,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(GalleryUpdateRequest, payload)
        try:
            item = await anyio.to_thread.run_sync(
                lambda: auth_store.update_gallery_item(
                    user_id=user.id,
                    generated_image_id=generated_image_id,
                    is_favorite=parsed.is_favorite,
                    tags=parsed.tags,
                )
            )
        except PermissionError as exc:
            raise APIError(HTTPStatus.FORBIDDEN, str(exc), code="forbidden") from exc
        return {"status": "ok", "item": item}

    @router.get("/api/usage")
    async def usage(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        target_user_id = None if user is None or user.is_admin else user.id
        users = await anyio.to_thread.run_sync(lambda: auth_store.usage_summary(target_user_id))
        return {
            "current_user": user.public_dict() if user else None,
            "scope": "all" if target_user_id is None else "self",
            "users": users,
        }

    @router.get("/api/admin/users")
    async def admin_users(
        _admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        users = await anyio.to_thread.run_sync(auth_store.usage_summary)
        return {"users": users}

    @router.get("/api/admin/org-units")
    async def admin_org_units(
        _admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        org_units = await anyio.to_thread.run_sync(auth_store.list_organization_units)
        return {"org_units": org_units}

    @router.post("/api/admin/org-units")
    async def admin_create_org_unit(
        body: Any = JSON_BODY,
        _admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        payload = _ensure_dict(body)
        parsed = _validate_request(OrganizationUnitRequest, payload)
        try:
            org_unit = await anyio.to_thread.run_sync(
                lambda: auth_store.create_organization_unit(
                    company=parsed.company,
                    department=parsed.department,
                )
            )
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        return {"status": "ok", "org_unit": org_unit}

    @router.put("/api/admin/users/{user_id}/org")
    async def admin_update_user_org(
        user_id: int,
        body: Any = JSON_BODY,
        admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        payload = _ensure_dict(body)
        parsed = _validate_request(AdminUpdateUserOrgRequest, payload)
        try:
            updated = await anyio.to_thread.run_sync(
                lambda: auth_store.update_user_org(
                    user_id=user_id,
                    company=parsed.company,
                    department=parsed.department,
                    actor_user_id=admin.id,
                    reason=parsed.reason,
                )
            )
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        if updated is None:
            raise APIError(HTTPStatus.NOT_FOUND, "用户不存在", code="not_found")
        return {"status": "ok", "user": updated.public_dict()}

    @router.get("/api/admin/org-audit")
    async def admin_org_audit(
        _admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        events = await anyio.to_thread.run_sync(auth_store.list_organization_audit_events)
        return {"events": events}

    @router.get("/api/admin/org-stats")
    async def admin_org_stats(
        _admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        org_stats = await anyio.to_thread.run_sync(auth_store.organization_stats)
        return {"org_stats": org_stats}

    @router.get("/api/admin/password-reset-requests")
    async def admin_password_reset_requests(
        _admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        requests = await anyio.to_thread.run_sync(
            lambda: auth_store.list_password_reset_requests(status="pending", limit=100)
        )
        return {"requests": requests}

    @router.post("/api/admin/users")
    async def admin_create_user(
        body: Any = JSON_BODY,
        _admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        payload = _ensure_dict(body)
        parsed = _validate_request(AdminCreateUserRequest, payload)
        try:
            normalize_username(parsed.username)
            user = await anyio.to_thread.run_sync(
                lambda: auth_store.create_user(parsed.username, parsed.password, role=parsed.role)
            )
        except UserExistsError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "用户名已存在", code="user_exists") from exc
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        return {"status": "ok", "user": user.public_dict()}

    @router.put("/api/admin/users/{user_id}/password")
    async def admin_reset_user_password(
        user_id: int,
        body: Any = JSON_BODY,
        admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        payload = _ensure_dict(body)
        parsed = _validate_request(AdminResetPasswordRequest, payload)
        user = await anyio.to_thread.run_sync(
            lambda: auth_store.reset_user_password(
                user_id=user_id,
                password=parsed.password,
                admin_user_id=admin.id,
            )
        )
        if user is None:
            raise APIError(HTTPStatus.NOT_FOUND, "用户不存在", code="not_found")
        return {"status": "ok", "user": user.public_dict()}

    @router.delete("/api/admin/users/{user_id}")
    async def admin_delete_user(
        user_id: int,
        admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user_id == admin.id:
            raise APIError(HTTPStatus.BAD_REQUEST, "不能删除当前管理员账号", code="cannot_delete_self")
        deleted = await anyio.to_thread.run_sync(auth_store.delete_user, user_id)
        if not deleted:
            raise APIError(HTTPStatus.NOT_FOUND, "用户不存在", code="not_found")
        return {"status": "ok"}

    @router.post("/api/feedback")
    async def result_feedback(
        body: Any = JSON_BODY,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(FeedbackRequest, payload)
        try:
            feedback = await anyio.to_thread.run_sync(
                lambda: auth_store.record_feedback(
                    user_id=user.id,
                    rating=parsed.rating,
                    reason=parsed.reason,
                    prompt=parsed.prompt,
                    mode=parsed.mode,
                    model=parsed.model,
                    saved_image_path=parsed.saved_image_path,
                    saved_image_url=parsed.saved_image_url,
                    generated_image_id=parsed.generated_image_id,
                )
            )
        except PermissionError as exc:
            raise APIError(HTTPStatus.FORBIDDEN, str(exc), code="forbidden") from exc
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        return {"status": "ok", "feedback": feedback}

    @router.get("/api/feedback/summary")
    async def feedback_summary(
        _admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        return await anyio.to_thread.run_sync(auth_store.feedback_summary)

    @router.post("/api/bug-reports")
    async def create_bug_report(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(BugReportRequest, payload)
        try:
            report = await anyio.to_thread.run_sync(
                lambda: auth_store.record_bug_report(
                    user_id=user.id,
                    title=parsed.title,
                    description=parsed.description,
                    contact=parsed.contact,
                    page_url=parsed.page_url,
                    user_agent=request.headers.get("user-agent", ""),
                )
            )
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        notification = await send_bug_report_notification(settings=settings, report=report, username=user.username)
        if notification.status != report["notification_status"]:
            await anyio.to_thread.run_sync(
                lambda: auth_store.update_bug_report_notification_status(report["id"], notification.status)
            )
            report = {**report, "notification_status": notification.status}
        return {
            "status": "ok",
            "report": report,
            "notification": notification.public_dict(),
        }

    @router.get("/api/bug-reports")
    async def bug_reports(
        _admin: AuthUser = Depends(require_admin_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        reports = await anyio.to_thread.run_sync(auth_store.list_bug_reports)
        return {"reports": reports}

    @router.post("/api/shares")
    async def create_share(
        body: Any = JSON_BODY,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(ShareResultRequest, payload)
        try:
            shares = await anyio.to_thread.run_sync(
                lambda: auth_store.create_result_shares(
                    sender_user_id=user.id,
                    recipient_ids=parsed.recipient_ids,
                    prompt=parsed.prompt,
                    mode=parsed.mode,
                    model=parsed.model,
                    rating=parsed.rating,
                    saved_image_path=parsed.saved_image_path,
                    saved_image_url=parsed.saved_image_url,
                    generated_image_id=parsed.generated_image_id,
                    note=parsed.note,
                )
            )
        except PermissionError as exc:
            raise APIError(HTTPStatus.FORBIDDEN, str(exc), code="forbidden") from exc
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        return {"status": "ok", "shares": shares}

    @router.post("/api/final-images")
    async def create_final_image(
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(FinalImageRequest, payload)
        started_at = time.perf_counter()
        try:
            source_record = await anyio.to_thread.run_sync(
                lambda: auth_store.generated_image_for_user(
                    generated_image_id=parsed.generated_image_id,
                    user_id=user.id,
                )
            )
            if source_record is None:
                raise PermissionError("无权更新这张图片")
            image_part = _validate_image_size(parsed.image, settings.max_image_bytes)
            image_mime = detect_image_mime(image_part["data"])
            if image_mime != "image/png":
                raise ValueError("最终成品必须是 PNG 图片")
            saved = await anyio.to_thread.run_sync(
                lambda: save_derived_output_image(
                    data_dir=settings.data_dir,
                    outputs_dir=settings.outputs_dir,
                    source_image_path=str(source_record.get("saved_image_path") or parsed.source_saved_image_path),
                    mode=str(source_record.get("mode") or "result"),
                    image_bytes=image_part["data"],
                    image_mime=image_mime,
                    suffix="logo" if parsed.logo_overlay_applied else "final",
                    metadata={
                        "generated_image_id": parsed.generated_image_id,
                        "user_id": user.id,
                        "username": user.username,
                        "mode": source_record.get("mode") or "",
                        "model": source_record.get("model") or "",
                        "prompt": source_record.get("prompt") or "",
                        "source_saved_image_path": (
                            source_record.get("saved_image_path") or parsed.source_saved_image_path
                        ),
                        "source_saved_image_url": source_record.get("saved_image_url") or parsed.source_saved_image_url,
                        "logo_overlay_applied": parsed.logo_overlay_applied,
                        "logo_overlay_source": parsed.logo_overlay_source,
                        "logo_text_color": parsed.logo_text_color,
                    },
                )
            )
            updated = await anyio.to_thread.run_sync(
                lambda: auth_store.replace_generated_image_asset(
                    generated_image_id=parsed.generated_image_id,
                    user_id=user.id,
                    image=saved,
                    logo_overlay_applied=parsed.logo_overlay_applied,
                )
            )
        except PermissionError as exc:
            raise APIError(HTTPStatus.FORBIDDEN, str(exc), code="forbidden") from exc
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, str(exc), code="validation_error") from exc
        should_notify_final_image = bool(updated.pop("_first_logo_final_for_job", False))
        if parsed.logo_overlay_applied and should_notify_final_image:
            _spawn_notification_task(
                _send_generation_success_alert(
                    settings,
                    _build_final_image_success_alert(
                        image=updated,
                        user=user,
                        elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                    ),
                )
            )
        return {
            "status": "ok",
            "image": {
                **updated,
                "logo_overlay_applied": parsed.logo_overlay_applied,
                "logo_overlay_source": parsed.logo_overlay_source,
                "logo_text_color": parsed.logo_text_color,
            },
        }

    @router.get("/api/shares/inbox")
    async def share_inbox(
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        shares = await anyio.to_thread.run_sync(lambda: auth_store.list_shared_results_for_user(user_id=user.id))
        return {"shares": shares}

    @router.post("/api/itinerary-map/plan")
    async def itinerary_map_plan(
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        user: AuthUser | None = Depends(require_current_user),
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(ItineraryMapPlanRequest, payload)
        _ensure_itinerary_request_has_no_restricted_destination(parsed)
        return await build_itinerary_map_plan_async(
            title=parsed.title,
            subtitle=parsed.subtitle,
            route_style=parsed.route_style,
            stops=[stop.model_dump() for stop in parsed.stops],
            geocode=lambda name: geocode_place_with_settings(name, settings),
        )

    @router.post("/api/itinerary-map/render")
    async def itinerary_map_render(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
        auth_store: AuthStore = Depends(get_auth_store),
        user: AuthUser | None = Depends(require_current_user),
    ) -> JSONResponse:
        return JSONResponse(
            await _with_timing(
                "/api/itinerary-map/render",
                handle_itinerary_map_render,
                body,
                settings,
                client,
                auth_store,
                user,
                request,
            )
        )

    @router.post("/api/generate")
    async def generate(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
        auth_store: AuthStore = Depends(get_auth_store),
        user: AuthUser | None = Depends(require_current_user),
    ) -> JSONResponse:
        return JSONResponse(
            await _with_timing("/api/generate", handle_generate, body, settings, client, auth_store, user, request)
        )

    @router.post("/api/edit")
    async def edit(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
        auth_store: AuthStore = Depends(get_auth_store),
        user: AuthUser | None = Depends(require_current_user),
    ) -> JSONResponse:
        return JSONResponse(
            await _with_timing("/api/edit", handle_edit, body, settings, client, auth_store, user, request)
        )

    @router.post("/api/responses-image")
    async def responses_image(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
        auth_store: AuthStore = Depends(get_auth_store),
        user: AuthUser | None = Depends(require_current_user),
    ) -> JSONResponse:
        return JSONResponse(
            await _with_timing(
                "/api/responses-image",
                handle_responses_image,
                body,
                settings,
                client,
                auth_store,
                user,
                request,
            )
        )

    @router.post("/api/copyright-risk")
    async def copyright_risk(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
        _user: AuthUser | None = Depends(require_current_user),
    ) -> JSONResponse:
        return JSONResponse(
            await _with_timing("/api/copyright-risk", handle_copyright_risk, body, settings, client, request=request)
        )

    @router.post("/api/text-fidelity")
    async def text_fidelity(
        request: Request,
        body: Any = JSON_BODY,
        settings: Settings = Depends(get_settings),
        client: UpstreamClient = Depends(get_client),
        _user: AuthUser | None = Depends(require_current_user),
    ) -> JSONResponse:
        return JSONResponse(
            await _with_timing("/api/text-fidelity", handle_text_fidelity, body, settings, client, request=request)
        )

    return router


def _copyright_risk_prompt(parsed: CopyrightRiskRequest) -> str:
    context = parsed.context.strip()
    prompt = parsed.prompt.strip()
    return (
        "你是图片版权与商标风险审查助手。请基于用户提供的最终生成图和上下文，"
        "用中文给出简短、务实、非法律意见的风险提醒。\n"
        "重点查看：商标/Logo、赛事或活动标识、奥运/冬奥等受保护元素、名人肖像、"
        "第三方品牌、IP角色、受版权保护的艺术风格或包装版式、可识别摄影作品。\n"
        "已知前提：图片素材通常来自用户自己，用户声称有授权，所以总体风险可能不高；"
        "但仍需指出画面元素本身可能触发复核的地方。\n"
        "输出格式：\n"
        "风险等级：低/中/高\n"
        "可能风险点：用 1-4 条短句\n"
        "建议：用 1-3 条短句\n"
        "如果没有明显风险，说明“未见明显第三方侵权元素”，但提醒商用前确认授权链。\n\n"
        f"用户提示词：{prompt or '未提供'}\n"
        f"生成上下文：{context or '未提供'}"
    )


_TEXT_FIDELITY_OUTPUT_FORMAT = (
    "输出格式：\n"
    "结论：通过/不通过\n"
    "缺失或疑似错误：没有则写“无”，否则列短语\n"
    "残留旧文字：没有则写“无”，否则列短语\n"
    "说明：一句话说明。\n"
)


def _text_fidelity_prompt(parsed: TextFidelityRequest) -> str:
    contract = parsed.text_contract
    if len(parsed.images) >= 2:
        # Edit-comparison mode: image 1 is the BEFORE, image 2 the AFTER.
        # Catches the systematic drift where an AI edit silently rewrites
        # protected body text it was told to leave alone (e.g. 镶→镀).
        # Transcribe-then-diff: without forcing a character-by-character
        # transcription first, vision models routinely miss single-character
        # substitutions between two large posters.
        return (
            "你会收到两张图：第 1 张是修改前的原图，第 2 张是修改后的成图。\n"
            "请先在心里把两张图的全部可读文字逐行转写出来（标题、副标题、正文每一行、地名、日期、价格、"
            "序号、图标旁的小字、贴士），再逐行逐字对比转写结果：\n"
            "1) 除了用户明确要求修改的内容，原图里的文字必须在成图中逐字保留；"
            "特别注意单字替换和形近字/同音字（例如 镶/镀、嚣/器、末/未、己/已、账/帐、艘/艏），"
            "发现任何一处都要列出来，格式如：原文“X”被改成“Y”。\n"
            "2) 用户要求修改的部分是否已经按要求体现。\n"
            "不要在发现第一处差异后停下：必须核对完两张图的全部文字（包括正文诗句、列表小字、"
            "价格、底部服务条目）之后，一次性列出所有差异。\n"
            "只要有一处未被要求却发生变化的文字，就必须判为不通过。\n"
            f"{_TEXT_FIDELITY_OUTPUT_FORMAT}\n"
            f"用户本次修改要求：{parsed.prompt.strip() or '未提供'}\n"
            f"生成上下文：{parsed.context.strip() or '未提供'}"
        )
    required_lines = [f"- 必须出现：{item}" for item in contract.required]
    forbidden_lines = [f"- 不得出现：{item}" for item in contract.forbidden]
    if not required_lines and not forbidden_lines and parsed.prompt.strip():
        # No explicit contract (label-based extraction found nothing — common
        # for table/free-form prompts). Fall back to treating the full prompt
        # as the text source instead of vacuously passing.
        return (
            "没有单独的文字合同。请把下面的用户提示词原文当作文字来源，检查图片中所有可读文字：\n"
            "1) 图中来自原文的每个短语必须逐字一致；"
            "换字、漏字、同音替换、繁简误换、数字或符号错误都算不通过（标题允许美术字造型但不允许改字）。\n"
            "2) 原文中明显要求出现的标题、列表项、名称、价格和日期是否都出现在图中。\n"
            "3) 左上角“6人游定制旅行 / Friends & Family”是官方 LOGO，属于正常品牌元素，不要当作问题；"
            "图中如出现原文没有的装饰性短语，只在“说明”里提一句，不要因此判不通过，除非它与原文内容矛盾或包含错字。\n"
            f"{_TEXT_FIDELITY_OUTPUT_FORMAT}\n"
            f"用户提示词原文：\n{parsed.prompt.strip()}\n\n"
            f"生成上下文：{parsed.context.strip() or '未提供'}"
        )
    checks = "\n".join([*required_lines, *forbidden_lines]) or "- 未提供明确文字合同。"
    return (
        "请检查图片中文字是否满足下面的文字合同。只基于图片里可读文字判断；"
        "如果图中对应区域模糊、缺字、错字、漏字、同音替换、顺序错误，也算不通过。\n"
        f"{_TEXT_FIDELITY_OUTPUT_FORMAT}\n"
        f"文字合同：\n{checks}\n\n"
        f"用户提示词：{parsed.prompt.strip() or '未提供'}\n"
        f"生成上下文：{parsed.context.strip() or '未提供'}"
    )


_TEXT_TRANSCRIBE_SINGLE_PROMPT = (
    "请转写这张图中的所有可读文字，用于程序自动比对。\n"
    "每一行画面文字单独输出一行，按画面从上到下的顺序，逐字转写。\n"
    "绝对不要纠错、不要把你认为的错字改对、不要补全、不要翻译、不要合并行、不要加任何评论；"
    "即使某个字看起来像错别字或很少见，也必须原样写出画面里的那个字。\n"
    "只输出文字行本身，不要任何标记、编号或说明。"
)


def _transcript_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _normalize_transcript_line(line: str) -> str:
    # Ignore whitespace and punctuation-width differences so the diff only
    # fires on actual character changes.
    cleaned = re.sub(r"\s+", "", line)
    for src, dst in ((",", "，"), (":", "："), (";", "；"), ("!", "！"), ("?", "？"), ("·", "・")):
        cleaned = cleaned.replace(src, dst)
    return cleaned


_LOGO_TRANSCRIPT_MARKERS = ("6人游", "friends&family", "friends & family")


def _is_logo_transcript_line(line: str) -> bool:
    folded = line.casefold().replace(" ", "")
    return any(marker.replace(" ", "") in folded for marker in _LOGO_TRANSCRIPT_MARKERS)


def _transcript_diff_report(before_lines: list[str], after_lines: list[str], prompt: str) -> str:
    """Diff two transcripts; unrequested changes to existing text fail the check.

    The diff runs on the CONCATENATED text (line breaks stripped): transcripts
    of the same poster frequently disagree on where lines split ("24h管家："
    vs "24h" + "管家："), and a line-level diff turns that into false alarms.
    """

    prompt_normalized = _normalize_transcript_line(prompt or "")

    def _full_text(lines: list[str]) -> str:
        return "".join(
            _normalize_transcript_line(line) for line in lines if not _is_logo_transcript_line(line)
        )

    before_text = _full_text(before_lines)
    after_text = _full_text(after_lines)

    changed: list[str] = []
    missing: list[str] = []
    added_chars = 0
    matcher = difflib.SequenceMatcher(a=before_text, b=after_text, autojunk=False)
    for op, a_start, a_end, b_start, b_end in matcher.get_opcodes():
        if op == "equal":
            continue
        old = before_text[a_start:a_end]
        new = after_text[b_start:b_end]
        context_before = before_text[max(0, a_start - 4) : a_start]
        context_after = before_text[a_end : a_end + 4]
        # Changes/removals the user explicitly asked for are not violations.
        if (old and old in prompt_normalized) or (new and new in prompt_normalized):
            continue
        if op == "replace":
            changed.append(f"原文“{context_before}{old}{context_after}”被改成“{context_before}{new}{context_after}”")
        elif op == "delete":
            missing.append(f"{context_before}{old}{context_after}")
        elif op == "insert":
            added_chars += len(new)

    problems = [*changed[:8], *(f"原文缺失：“{item}”" for item in missing[:5])]
    if problems:
        listed = "\n".join(f"- {item}" for item in problems[:10])
        return (
            "结论：不通过\n"
            f"缺失或疑似错误：\n{listed}\n"
            "残留旧文字：无\n"
            "说明：程序对比了编辑前后的画面文字转写结果，以上文字在没有被要求修改的情况下发生了变化，请复核。"
        )
    note = f"成图另有约 {added_chars} 字新增文字（可能来自本次修改要求）。" if added_chars else ""
    return (
        "结论：通过\n"
        "缺失或疑似错误：无\n"
        "残留旧文字：无\n"
        f"说明：程序对比了编辑前后的画面文字转写结果，原有文字均逐字保留。{note}"
        "（提示：个别形近字的差异可能超出自动识别能力，重要交付请人工复核。）"
    )


def _text_fidelity_passed(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text or "")
    if not normalized:
        return False
    if "结论：通过" in normalized or "结论:通过" in normalized:
        return True
    failure_markers = ("结论：不通过", "结论:不通过", "不通过", "缺失", "疑似错误", "残留旧文字", "错字", "漏字")
    if any(marker in normalized for marker in failure_markers):
        return False
    return False


def _parse_team_chat_mentions(content: str) -> list[str]:
    mentions: list[str] = []
    # Normalize the full-width "\uff20" (U+FF20) that Chinese IMEs commonly produce, and
    # the full-width space, so "\uff20GPT-BOT" still triggers a mention.
    for token in content.replace("\u3000", " ").replace("\uff20", "@").split():
        if not token.startswith("@"):
            continue
        name = token[1:].strip("，,。.!！?？:：;；()（）[]【】")
        if name:
            mentions.append(name[:80])
    return list(dict.fromkeys(mentions))


def team_chat_group_title(company: str, department: str) -> str:
    clean_department = department.strip() or "未分配部门"
    return clean_department


def team_chat_group_subtitle(company: str) -> str:
    clean_company = company.strip() or "未分配公司"
    return f"{clean_company} · 部门群"


def _team_chat_display_name(user: AuthUser) -> str:
    return (user.display_name or user.username).strip()


def _team_chat_bot_was_mentioned(content: str, mentions: list[str]) -> bool:
    lowered = content.casefold().replace("＠", "@")
    return any(item.casefold() in {"gpt-bot", "gptbot", "bot"} for item in mentions) or "@gpt-bot" in lowered


def _team_chat_bot_prompt(
    *,
    user: AuthUser,
    content: str,
    room_type: str,
    recent_messages: list[dict[str, Any]],
) -> str:
    recent_lines: list[str] = []
    for message in recent_messages[-20:]:
        sender = str(message.get("sender_name") or "")
        text = str(message.get("content") or "").strip()
        if not text:
            continue
        recent_lines.append(f"{sender}: {text[:500]}")
    context = "\n".join(recent_lines) or "暂无上下文"
    return (
        "你是 PicGen 团队聊天里的 GPT-BOT，也是这个工作台的全局图片质量助手、创意总监和高端定制旅行顾问。"
        "你熟悉全球大量冷门小众但高质量的目的地、酒店、步道、海岛、酒庄、观景点、在地体验、"
        "最佳季节、抵达方式、签证/安全/预算/人群匹配，以及把这些方案转成高级旅行海报和图片提示词的方法。"
        "请用中文回复，语气专业、简洁、可信，不讲空泛鸡汤，优先给可执行建议。"
        "你可以帮助用户审视图片需求是否高级、是否符合旅行产品气质、是否适合 6 人游品牌、是否有构图/光影/质感/排版风险。"
        "平台默认尊重用户自由提示词和个性创意；Creative Brief、历史满意作品、Group 优秀资产都只能作为可选参考，"
        "不要把所有用户的提示词改成统一模板，也不要强制套用历史风格。"
        "当用户询问旅行方案时，给出清晰的目的地/体验组合、适合人群、亮点、避坑和落地建议；"
        "当用户询问制图、提示词、排版、审美、运营文案时，把旅行专业判断转成可直接使用的提示词、构图和文案建议。"
        "如果用户要求你优化提示词，请优先给“可追加短句”和“风险提醒”，保留原文个性。"
        "如果信息不足，请只提出 1-2 个关键追问，并先给一个稳妥默认方案。"
        "不要声称自己能直接操作系统或查看用户没有提供的图片。"
        "群聊中回复时要艾特提问者；私聊中可以直接回复。\n\n"
        f"房间类型：{room_type}\n"
        f"提问用户：{_team_chat_display_name(user)}（登录用户名：{user.username}）\n"
        f"最近聊天：\n{context}\n\n"
        f"用户最新消息：{content.strip()}"
    )


async def _create_team_chat_bot_reply(
    *,
    auth_store: AuthStore,
    settings: Settings,
    client: UpstreamClient,
    user: AuthUser,
    room_key: str,
    room_type: str,
    content: str,
    recent_messages: list[dict[str, Any]],
) -> dict[str, Any]:
    prefix = "" if room_type == "bot" else f"@{_team_chat_display_name(user)} "
    api_key = settings.default_api_key.strip()
    try:
        endpoint_url = validate_url(settings.default_responses_url, "Responses 文本接口 URL")
    except APIError:
        # This runs in a fire-and-forget task — raising here would swallow the
        # reply entirely. Fall back to the same friendly bot message as the
        # missing-key case so the user is not left waiting forever.
        endpoint_url = ""
    if not api_key or not endpoint_url:
        return await anyio.to_thread.run_sync(
            lambda: auth_store.create_team_chat_message(
                room_key=room_key,
                room_type=room_type,
                sender_user_id=None,
                sender_type="bot",
                sender_name=TEAM_CHAT_BOT_NAME,
                content=f"{prefix}AI 服务暂时没有配置好，我已经看到你的消息了。",
                mentions=[user.username],
            )
        )
    model = settings.default_responses_model.strip() or DEFAULT_RESPONSES_MODEL
    upstream_payload = {
        "model": model,
        "instructions": TEAM_CHAT_BOT_INSTRUCTIONS,
        **_responses_reasoning_options(model),
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": _team_chat_bot_prompt(
                            user=user,
                            content=content,
                            room_type=room_type,
                            recent_messages=recent_messages,
                        ),
                    }
                ],
            }
        ],
    }
    try:
        upstream_response = await client.run_responses(
            endpoint_url,
            api_key,
            upstream_payload,
            settings.upstream_user_agent,
        )
        reply_text = _extract_text_output(upstream_response) or "我收到了，但暂时没有组织出可靠回复。"
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "team_chat_bot_failed",
            error=redact_sensitive_text(str(exc)),
            user_id=user.id,
            username=user.username,
        )
        reply_text = "AI 服务暂时连接不上，先把问题记下来了，请稍后再试。"
    return await anyio.to_thread.run_sync(
        lambda: auth_store.create_team_chat_message(
            room_key=room_key,
            room_type=room_type,
            sender_user_id=None,
            sender_type="bot",
            sender_name=TEAM_CHAT_BOT_NAME,
            content=f"{prefix}{reply_text.strip()[:3800]}",
            mentions=[user.username],
        )
    )


def _schedule_team_chat_bot_reply(
    *,
    auth_store: AuthStore,
    settings: Settings,
    client: UpstreamClient,
    user: AuthUser,
    room_key: str,
    room_type: str,
    content: str,
    recent_messages: list[dict[str, Any]],
) -> None:
    task = _create_team_chat_bot_reply(
        auth_store=auth_store,
        settings=settings,
        client=client,
        user=user,
        room_key=room_key,
        room_type=room_type,
        content=content,
        recent_messages=recent_messages,
    )
    try:
        scheduled = asyncio.create_task(task)
    except RuntimeError:
        asyncio.run(task)
        return
    _TEAM_CHAT_BOT_TASKS.add(scheduled)

    def _forget(done_task: asyncio.Task[dict[str, Any]]) -> None:
        _TEAM_CHAT_BOT_TASKS.discard(done_task)
        try:
            done_task.result()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "team_chat_bot_task_error",
                error=redact_sensitive_text(str(exc), limit=300),
            )

    scheduled.add_done_callback(_forget)


def _extract_text_output(payload: dict[str, Any]) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    output = payload.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_text = block.get("text")
                    if isinstance(block_text, str) and block_text.strip():
                        chunks.append(block_text.strip())
            item_text = item.get("text")
            if isinstance(item_text, str) and item_text.strip():
                chunks.append(item_text.strip())
        if chunks:
            return "\n".join(chunks)

    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                maybe_text = item.get("text") or item.get("content")
                if isinstance(maybe_text, str) and maybe_text.strip():
                    return maybe_text.strip()
    return ""


async def handle_copyright_risk(
    body: Any, settings: Settings, client: UpstreamClient, user: AuthUser | None = None
) -> dict[str, Any]:
    payload = _ensure_dict(body)
    parsed = _validate_request(CopyrightRiskRequest, payload)

    endpoint_url = validate_url(
        parsed.endpoint_url or settings.default_responses_url,
        "Responses 图像接口 URL",
    )
    model = (parsed.model or settings.default_responses_model).strip() or DEFAULT_RESPONSES_MODEL
    api_key = (parsed.api_key or settings.default_api_key).strip()
    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key", code="bad_request")

    image_parts = _request_image_parts(
        image=None,
        images=parsed.images,
        max_image_bytes=settings.max_image_bytes,
    )
    content = _responses_inline_input_content(_copyright_risk_prompt(parsed), image_parts)
    upstream_payload = {
        "model": model,
        "instructions": COPYRIGHT_RISK_INSTRUCTIONS,
        **_responses_reasoning_options(model),
        "input": [
            {
                "role": "user",
                "content": content,
            }
        ],
    }
    upstream_response = await client.run_responses(
        endpoint_url, api_key, upstream_payload, settings.upstream_user_agent
    )
    return {
        "model": model,
        "risk_text": _extract_text_output(upstream_response) or "未能解析风险提醒文本。",
        "raw_response": compact_raw_response(upstream_response),
    }


async def handle_text_fidelity(
    body: Any, settings: Settings, client: UpstreamClient, user: AuthUser | None = None
) -> dict[str, Any]:
    payload = _ensure_dict(body)
    parsed = _validate_request(TextFidelityRequest, payload)

    endpoint_url = validate_url(
        parsed.endpoint_url or settings.default_responses_url,
        "Responses 图像接口 URL",
    )
    model = (parsed.model or settings.default_responses_model).strip() or DEFAULT_RESPONSES_MODEL
    api_key = (parsed.api_key or settings.default_api_key).strip()
    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key", code="bad_request")

    image_parts = _request_image_parts(
        image=None,
        images=parsed.images,
        max_image_bytes=settings.max_image_bytes,
    )
    if len(image_parts) >= 2:
        # Before/after edit comparison. Asking a vision model to "spot the
        # difference" between two posters is unreliable for single-character
        # substitutions — it flags one run and misses the next. Instead the
        # model only TRANSCRIBES (an easy, stable task) and the diff is
        # computed programmatically. The two images MUST be transcribed in
        # separate calls: in a shared context the model transcribes the second
        # image by copying the first transcript, erasing exactly the
        # single-character drift (镶→镀) this check exists to catch.
        async def _transcribe(part: dict[str, Any]) -> list[str]:
            response = await client.run_responses(
                endpoint_url,
                api_key,
                {
                    "model": model,
                    "instructions": TEXT_FIDELITY_INSTRUCTIONS,
                    **_responses_reasoning_options(model),
                    "input": [
                        {
                            "role": "user",
                            "content": _responses_inline_input_content(_TEXT_TRANSCRIBE_SINGLE_PROMPT, [part]),
                        }
                    ],
                },
                settings.upstream_user_agent,
            )
            return _transcript_lines(_extract_text_output(response) or "")

        before_lines, after_lines = await asyncio.gather(
            _transcribe(image_parts[0]), _transcribe(image_parts[1])
        )
        if before_lines and after_lines:
            fidelity_text = _transcript_diff_report(before_lines, after_lines, parsed.prompt)
            return {
                "model": model,
                "passed": _text_fidelity_passed(fidelity_text),
                "fidelity_text": fidelity_text,
                "raw_response": {
                    "before_transcript": before_lines,
                    "after_transcript": after_lines,
                },
            }
        # Transcription came back unparseable — fall through to the one-shot
        # judgment below rather than failing the check outright.

    content = _responses_inline_input_content(_text_fidelity_prompt(parsed), image_parts)
    upstream_payload = {
        "model": model,
        "instructions": TEXT_FIDELITY_INSTRUCTIONS,
        **_responses_reasoning_options(model),
        "input": [
            {
                "role": "user",
                "content": content,
            }
        ],
    }
    upstream_response = await client.run_responses(
        endpoint_url, api_key, upstream_payload, settings.upstream_user_agent
    )
    fidelity_text = _extract_text_output(upstream_response) or "未能解析文字一致性检查结果。"
    return {
        "model": model,
        "passed": _text_fidelity_passed(fidelity_text),
        "fidelity_text": fidelity_text,
        "raw_response": compact_raw_response(upstream_response),
    }


def _user_metadata(user: AuthUser | None) -> dict[str, Any]:
    if user is None:
        return {}
    return {
        "user_id": user.id,
        "username": user.username,
        "filename_prefix": user.username,
    }


def _result_image_count(result: dict[str, Any]) -> int:
    images = result.get("images")
    if isinstance(images, list):
        return len([item for item in images if isinstance(item, dict)])
    return 1 if result.get("saved_image_url") or result.get("image_data_url") or result.get("image_url") else 0


def _result_saved_bytes(result: dict[str, Any]) -> int:
    images = result.get("images")
    if isinstance(images, list):
        total = 0
        for image in images:
            if isinstance(image, dict):
                value = image.get("saved_image_bytes")
                if isinstance(value, int):
                    total += value
        return total
    value = result.get("saved_image_bytes")
    return value if isinstance(value, int) else 0


def _image_dimensions_for_size_check(image: dict[str, Any]) -> tuple[int, int] | None:
    width = image.get("saved_image_width")
    height = image.get("saved_image_height")
    if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
        return width, height
    return None


def _mark_image_size_mismatch(saved: dict[str, Any], save_context: dict[str, Any]) -> None:
    if not save_context.get("strict_size"):
        return
    requested_size = str(save_context.get("requested_size") or save_context.get("size") or "").strip()
    expected = _parse_requested_size(requested_size)
    if expected is None:
        return

    images = saved.get("images")
    candidates = [item for item in images if isinstance(item, dict)] if isinstance(images, list) else [saved]
    mismatches: list[str] = []
    first_checked: dict[str, Any] | None = None
    for image in candidates:
        actual = _image_dimensions_for_size_check(image)
        if actual is None:
            continue
        if first_checked is None:
            first_checked = image
        image["actual_size"] = f"{actual[0]}x{actual[1]}"
        image["requested_size"] = requested_size
        if actual != expected:
            actual_size = f"{actual[0]}x{actual[1]}"
            image["size_mismatch"] = True
            image["size_mismatch_message"] = (
                f"上游返回尺寸为 {actual_size}，与请求尺寸 {expected[0]}x{expected[1]} 不一致。"
                "图片已按上游原始返回保存，本地没有缩放。"
            )
            mismatches.append(actual_size)
        else:
            image["size_mismatch"] = False
    if not mismatches:
        if first_checked is not None:
            for key in (
                "actual_size",
                "requested_size",
                "size_mismatch",
                "image_size_normalized",
                "image_size_normalized_method",
                "upstream_actual_size",
                "upstream_image_width",
                "upstream_image_height",
            ):
                if key in first_checked:
                    saved[key] = first_checked[key]
        return

    # Summarize from the first candidate that actually mismatched — candidate 0
    # may be the compliant one, which would publish "size_mismatch: true" with
    # an actual_size equal to the requested size.
    saved["actual_size"] = mismatches[0]
    saved["requested_size"] = requested_size
    saved["size_mismatch"] = True
    saved["size_mismatch_actual_sizes"] = list(dict.fromkeys(mismatches))
    saved["size_mismatch_message"] = (
        f"上游返回尺寸为 {', '.join(dict.fromkeys(mismatches))}，"
        f"与请求尺寸 {expected[0]}x{expected[1]} 不一致。图片已按上游原始返回保存，本地没有缩放。"
    )


def _should_track_generation_job(path: str) -> bool:
    return path in {
        "/api/generate",
        "/api/edit",
        "/api/responses-image",
        "/api/itinerary-map/render",
    }


def _extract_itinerary_id_from_prompt(prompt: str) -> str:
    match = _ITINERARY_ID_RE.search(prompt or "")
    if not match:
        return ""
    return _clean_itinerary_id(match.group(1))


def _clean_itinerary_id(value: str) -> str:
    cleaned = str(value or "").strip()
    cleaned = cleaned.strip(" \t\r\n,，.。;；)")
    cleaned = re.sub(r"\s+", "", cleaned)
    if not cleaned:
        return ""
    return cleaned[:32]


def _resolve_itinerary_id(*, explicit_id: str | None, prompt: str) -> str:
    return _clean_itinerary_id(explicit_id or "") or _extract_itinerary_id_from_prompt(prompt)


def _append_itinerary_id_badge_prompt(prompt: str, itinerary_id: str) -> str:
    clean_id = _clean_itinerary_id(itinerary_id)
    if not clean_id:
        return prompt
    return (
        f"{prompt.rstrip()}\n\n"
        "行程 ID 角标要求：\n"
        f"- 请把“行程 ID：{clean_id}”作为克制的品牌信息角标放在画面右上角。\n"
        "- 右上角行程 ID 要和左上角 LOGO 安全区形成对称关系，字号、基线、留白和视觉重量保持协调。\n"
        "- 角标应融入整体海报风格，可使用半透明底、细线、轻微阴影或同色系文字；不要做成突兀红字、硬贴纸或大标题。\n"
        "- 不要在其它位置重复出现行程 ID。"
    )


def _job_sample_count(payload: dict[str, Any]) -> int:
    try:
        parsed = int(payload.get("sample_count") or 1)
    except (TypeError, ValueError):
        return 1
    return max(1, min(parsed, 3))


def _generate_mode(value: Any) -> str:
    mode = str(value or "").strip()
    if mode == "itinerary":
        return "itinerary"
    return "generate"


def _job_mode(path: str, payload: dict[str, Any]) -> str:
    if path == "/api/itinerary-map/render":
        return "itinerary"
    if path == "/api/generate":
        return _generate_mode(payload.get("mode"))
    if path == "/api/edit":
        return str(payload.get("mode") or "edit")
    if path == "/api/responses-image":
        fallback = "reference" if payload.get("image") or payload.get("images") else "responses"
        return str(payload.get("mode") or fallback)
    return ""


def _job_transport(path: str) -> str:
    return {
        "/api/generate": "images-generate",
        "/api/edit": "images-edit",
        "/api/responses-image": "responses-image",
        "/api/itinerary-map/render": "responses-itinerary-artwork",
    }.get(path, "")


def _job_metadata(path: str, body: Any, user: AuthUser) -> dict[str, Any]:
    payload = body if isinstance(body, dict) else {}
    prompt_mode = str(payload.get("prompt_mode") or "free")
    raw_recipe_id = str(payload.get("recipe_id") or "").strip()
    recipe = recipe_public_dict(raw_recipe_id) if raw_recipe_id else None
    recipe_id = raw_recipe_id if prompt_mode == "recipe" and recipe is not None else ""
    recipe_version = str(payload.get("recipe_version") or "").strip() if recipe_id else ""
    default_model = {
        "/api/itinerary-map/render": "responses-itinerary-artwork",
    }.get(path, "")
    default_size = {
        "/api/itinerary-map/render": ITINERARY_DEFAULT_SIZE,
    }.get(path, "")
    return {
        "request_id": get_request_id(),
        "user_id": user.id,
        "username": user.username,
        "endpoint_path": path,
        "mode": _job_mode(path, payload),
        "transport": _job_transport(path),
        "prompt": str(payload.get("prompt") or payload.get("title") or ""),
        "original_prompt": str(
            payload.get("original_prompt")
            or payload.get("prompt")
            or payload.get("title")
            or payload.get("subtitle")
            or ""
        ),
        "prompt_mode": prompt_mode,
        "recipe_id": recipe_id,
        "recipe_version": recipe_version,
        "model": str(payload.get("model") or default_model),
        "size": str(payload.get("size") or default_size),
        "sample_count": _job_sample_count(payload),
        "logo_requested": (
            bool(payload.get("logo_requested", True))
            if path == "/api/itinerary-map/render"
            else bool(payload.get("logo_requested"))
        ),
    }


def _attach_generation_record_ids(
    result: dict[str, Any],
    *,
    job_id: int,
    image_records: list[dict[str, Any]],
) -> None:
    result["generation_job_id"] = job_id
    # DB rows are only created for SAVED candidates (_result_images_for_db filters
    # out URL-only / unsaved ones), so a positional zip against the full images list
    # misaligns ids whenever any candidate is unsaved — feedback/finalize/favorite
    # would then hit the wrong image. Match by candidate_index, which both sides carry.
    records_by_candidate = {
        int(record.get("candidate_index", idx) or 0): record
        for idx, record in enumerate(image_records)
    }
    images = result.get("images")
    if isinstance(images, list):
        for idx, image in enumerate(images):
            if not isinstance(image, dict):
                continue
            image["generation_job_id"] = job_id
            record = records_by_candidate.get(int(image.get("candidate_index", idx) or 0))
            if record is not None:
                image["generated_image_id"] = record["id"]
    if image_records:
        result["generated_image_id"] = image_records[0]["id"]


async def _attach_source_generation_id(
    result: dict[str, Any],
    body: Any,
    auth_store: AuthStore | None = None,
    user: AuthUser | None = None,
) -> None:
    if not isinstance(body, dict):
        return
    source_generated_image_id = body.get("source_generated_image_id")
    if not isinstance(source_generated_image_id, int) or source_generated_image_id <= 0:
        source_generated_image_id = await _infer_source_generation_id(body, auth_store, user)
    if not isinstance(source_generated_image_id, int) or source_generated_image_id <= 0:
        return
    result["source_generated_image_id"] = source_generated_image_id
    images = result.get("images")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, dict):
                image.setdefault("source_generated_image_id", source_generated_image_id)


async def _infer_source_generation_id(
    body: dict[str, Any],
    auth_store: AuthStore | None,
    user: AuthUser | None,
) -> int | None:
    if auth_store is None or user is None:
        return None
    source_names, source_urls, source_paths = _source_image_identity_tokens(body)
    if not source_names and not source_urls and not source_paths:
        return None
    return await anyio.to_thread.run_sync(
        lambda: auth_store.resolve_generated_image_id_from_source(
            user_id=user.id,
            source_names=source_names,
            source_urls=source_urls,
            source_paths=source_paths,
        )
    )


def _source_image_identity_tokens(body: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    names: list[str] = []
    urls: list[str] = []
    paths: list[str] = []
    for key in ("source_saved_image_url", "source_original_saved_image_url"):
        value = body.get(key)
        if isinstance(value, str):
            urls.append(value)
    for key in ("source_saved_image_path", "source_original_saved_image_path"):
        value = body.get(key)
        if isinstance(value, str):
            paths.append(value)
    image_items: list[Any] = []
    image = body.get("image")
    if image is not None:
        image_items.append(image)
    images = body.get("images")
    if isinstance(images, list):
        image_items.extend(images)
    for item in image_items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str):
            names.append(name)
        saved_url = item.get("saved_image_url") or item.get("source_saved_image_url")
        if isinstance(saved_url, str):
            urls.append(saved_url)
        saved_path = item.get("saved_image_path") or item.get("source_saved_image_path")
        if isinstance(saved_path, str):
            paths.append(saved_path)
    return names, urls, paths


def _result_images(result: dict[str, Any]) -> list[dict[str, Any]]:
    images = result.get("images")
    if isinstance(images, list):
        return [image for image in images if isinstance(image, dict)]
    if result.get("saved_image_url") or result.get("saved_image_path"):
        return [result]
    return []


def _result_saved_image_urls(result: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for image in _result_images(result):
        url = str(image.get("saved_image_url") or "").strip()
        if url:
            urls.append(url)
    return urls


def _result_generated_image_ids(result: dict[str, Any], image_records: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for image in _result_images(result):
        value = image.get("generated_image_id")
        if isinstance(value, int):
            ids.append(value)
    if ids:
        return ids
    return [int(record["id"]) for record in image_records if isinstance(record.get("id"), int)]


def _result_logo_overlay_applied(result: dict[str, Any]) -> bool:
    return any(bool(image.get("logo_overlay_applied")) for image in _result_images(result))


def _build_generation_success_alert(
    *,
    path: str,
    body: Any,
    result: dict[str, Any],
    user: AuthUser,
    job_id: int,
    image_records: list[dict[str, Any]],
    elapsed_ms: float,
) -> GenerationSuccessAlert:
    payload = body if isinstance(body, dict) else {}
    return GenerationSuccessAlert(
        request_id=get_request_id(),
        job_id=job_id,
        user_id=user.id,
        username=user.username,
        method="POST",
        path=path,
        mode=str(result.get("mode") or _job_mode(path, payload) or ""),
        model=str(result.get("model") or payload.get("model") or ""),
        size=str(result.get("size") or payload.get("size") or ""),
        prompt=str(result.get("prompt") or payload.get("prompt") or ""),
        image_count=_result_image_count(result),
        candidate_count=int(result.get("candidate_count") or _result_image_count(result) or 0),
        saved_bytes=_result_saved_bytes(result),
        elapsed_ms=elapsed_ms,
        logo_requested=bool(result.get("logo_requested") or payload.get("logo_requested")),
        logo_overlay_applied=_result_logo_overlay_applied(result),
        saved_image_urls=_result_saved_image_urls(result),
        generated_image_ids=_result_generated_image_ids(result, image_records),
    )


def _build_final_image_success_alert(
    *,
    image: dict[str, Any],
    user: AuthUser,
    elapsed_ms: float,
) -> GenerationSuccessAlert:
    return GenerationSuccessAlert(
        request_id=get_request_id(),
        job_id=int(image.get("job_id") or 0),
        user_id=user.id,
        username=user.username,
        method="POST",
        path="/api/final-images",
        mode=str(image.get("mode") or ""),
        model=str(image.get("model") or ""),
        size="",
        prompt=str(image.get("prompt") or ""),
        image_count=1 if image.get("saved_image_url") else 0,
        candidate_count=1 if image.get("saved_image_url") else 0,
        saved_bytes=max(0, int(image.get("saved_image_bytes") or 0)),
        elapsed_ms=elapsed_ms,
        logo_requested=bool(image.get("logo_requested") or image.get("logo_overlay_applied")),
        logo_overlay_applied=bool(image.get("logo_overlay_applied")),
        saved_image_urls=[str(image.get("saved_image_url") or "")] if image.get("saved_image_url") else [],
        generated_image_ids=[int(image.get("id") or 0)] if image.get("id") else [],
    )


def _should_send_generation_success_alert(alert: GenerationSuccessAlert) -> bool:
    return not (alert.logo_requested and not alert.logo_overlay_applied)


# Strong references to fire-and-forget notification tasks; asyncio only keeps
# weak references, so without this a task can be garbage-collected mid-send.
_notification_tasks: set[asyncio.Task[Any]] = set()


def _spawn_notification_task(coro: Coroutine[Any, Any, Any]) -> None:
    """Send a notification off the request path.

    Success/informational notifications must never delay the response: with
    Telegram unreachable the previous inline ``await`` stalled every finished
    generation by the full notification timeout (15s) after the image was
    already saved.
    """

    task = asyncio.create_task(coro)
    _notification_tasks.add(task)
    task.add_done_callback(_notification_tasks.discard)


async def _send_generation_success_alert(settings: Settings, alert: GenerationSuccessAlert) -> None:
    result = await send_generation_success_notification(settings=settings, alert=alert)
    if result.configured and not result.sent:
        log_event(
            logger,
            logging.WARNING,
            "generation_success_notification_failed",
            status=result.status,
            error=redact_sensitive_text(result.error, limit=300),
            request_id=alert.request_id,
            job_id=alert.job_id,
        )


async def _notify_password_reset_request(settings: Settings, request_info: dict[str, Any]) -> None:
    notification = await send_password_reset_request_notification(
        settings=settings,
        request_info=request_info,
    )
    if notification.configured and not notification.sent:
        log_event(
            logger,
            logging.WARNING,
            "password_reset_notification_failed",
            status=notification.status,
            error=notification.error,
        )


async def _raise_if_client_disconnects(request: Request) -> None:
    while True:
        if await request.is_disconnected():
            raise APIError(499, "用户已中断当前生成", code="client_cancelled")
        await anyio.sleep(0.25)


async def _run_handler_until_client_disconnect(
    *,
    handler: Any,
    body: Any,
    settings: Settings,
    client: UpstreamClient,
    user: AuthUser | None,
    request: Request | None,
) -> dict[str, Any]:
    if request is None:
        return await handler(body, settings, client, user)

    result: dict[str, Any] | None = None
    error: BaseException | None = None

    async def _run_handler() -> None:
        nonlocal result, error
        try:
            result = await handler(body, settings, client, user)
        except Exception as exc:
            error = exc

    async def _watch_disconnect() -> None:
        nonlocal error
        try:
            await _raise_if_client_disconnects(request)
        except APIError as exc:
            error = exc

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(_run_handler)
        task_group.start_soon(_watch_disconnect)
        while result is None and error is None:
            await anyio.sleep(0.05)
        task_group.cancel_scope.cancel()

    if error is not None:
        raise error
    return result or {}


async def _with_timing(
    path: str,
    handler: Any,
    body: Any,
    settings: Settings,
    client: UpstreamClient,
    auth_store: AuthStore | None = None,
    user: AuthUser | None = None,
    request: Request | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    job_id: int | None = None
    log_event(logger, logging.INFO, "local_post_start", path=path)
    try:
        if auth_store is not None and user is not None and _should_track_generation_job(path):
            job_id = await anyio.to_thread.run_sync(
                lambda: auth_store.create_generation_job(**_job_metadata(path, body, user))
            )
        result = await _run_handler_until_client_disconnect(
            handler=handler,
            body=body,
            settings=settings,
            client=client,
            user=user,
            request=request,
        )
        await _attach_source_generation_id(result, body, auth_store, user)
        generation_alert: GenerationSuccessAlert | None = None
        if auth_store is not None and user is not None:
            if job_id is not None:
                elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
                image_records = await anyio.to_thread.run_sync(
                    lambda: auth_store.complete_generation_job(
                        job_id=job_id,
                        result=result,
                        elapsed_ms=elapsed_ms,
                    )
                )
                _attach_generation_record_ids(result, job_id=job_id, image_records=image_records)
                generation_alert = _build_generation_success_alert(
                    path=path,
                    body=body,
                    result=result,
                    user=user,
                    job_id=job_id,
                    image_records=image_records,
                    elapsed_ms=elapsed_ms,
                )
            await anyio.to_thread.run_sync(
                lambda: auth_store.record_usage(
                    user_id=user.id,
                    endpoint_path=path,
                    mode=str(result.get("mode") or ""),
                    image_count=_result_image_count(result),
                    saved_bytes=_result_saved_bytes(result),
                )
            )
        if generation_alert is not None and _should_send_generation_success_alert(generation_alert):
            _spawn_notification_task(_send_generation_success_alert(settings, generation_alert))
    except APIError as exc:
        error_code = exc.code
        error_message = redact_sensitive_text(exc.message, limit=1000)
        if auth_store is not None and job_id is not None:
            try:
                await anyio.to_thread.run_sync(
                    lambda: auth_store.fail_generation_job(
                        job_id=job_id,
                        elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                        error_code=error_code,
                        error_message=error_message,
                    )
                )
            except Exception as record_exc:
                log_event(
                    logger,
                    logging.ERROR,
                    "generation_job_fail_record_error",
                    path=path,
                    job_id=job_id,
                    error=type(record_exc).__name__,
                )
        log_event(
            logger,
            logging.WARNING,
            "local_post_api_error",
            path=path,
            status=exc.status,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            message=exc.message,
            code=exc.code,
        )
        raise
    except Exception as exc:
        error_code = type(exc).__name__
        error_message = str(exc)
        if auth_store is not None and job_id is not None:
            try:
                await anyio.to_thread.run_sync(
                    lambda: auth_store.fail_generation_job(
                        job_id=job_id,
                        elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                        error_code=error_code,
                        error_message=error_message,
                    )
                )
            except Exception as record_exc:
                log_event(
                    logger,
                    logging.ERROR,
                    "generation_job_fail_record_error",
                    path=path,
                    job_id=job_id,
                    error=type(record_exc).__name__,
                )
        log_event(
            logger,
            logging.ERROR,
            "local_post_unhandled",
            path=path,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            error=type(exc).__name__,
        )
        raise APIError(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "本地服务发生未预期错误",
            f"{type(exc).__name__}: {exc}",
            code="internal_error",
        ) from exc
    log_event(
        logger,
        logging.INFO,
        "local_post_ok",
        path=path,
        elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
    )
    return result


async def handle_generate(
    body: Any, settings: Settings, client: UpstreamClient, user: AuthUser | None = None
) -> dict[str, Any]:
    payload = _ensure_dict(body)
    parsed = _validate_request(GenerateRequest, payload)

    endpoint_url = validate_url(
        parsed.endpoint_url or settings.default_generate_url,
        "生成接口 URL",
    )
    model = (parsed.model or settings.default_model).strip() or settings.default_model
    size = (parsed.size or settings.default_size).strip() or settings.default_size
    api_key = (parsed.api_key or settings.default_api_key).strip()
    image_options = _highest_quality_image_options(openai_image_options(payload))
    mode = _generate_mode(parsed.mode)
    if mode != "itinerary":
        _validate_exact_image_size(size)
    strict_size = mode != "itinerary" and _strict_requested_size(size)
    original_prompt = (parsed.original_prompt or parsed.prompt).strip()
    prompt_mode = parsed.prompt_mode
    recipe_id = parsed.recipe_id or ""
    recipe_version = parsed.recipe_version or ""
    recipe = recipe_public_dict(recipe_id) if recipe_id else None
    itinerary_id = _resolve_itinerary_id(explicit_id=parsed.itinerary_id, prompt=original_prompt)
    effective_prompt = _append_itinerary_id_badge_prompt(parsed.prompt, itinerary_id)

    _ensure_no_restricted_destination_text(parsed.prompt, original_prompt)
    _ensure_not_legacy_program_layout_background_prompt(parsed.prompt, original_prompt)
    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key", code="bad_request")
    if prompt_mode == "recipe" and recipe is None:
        raise APIError(HTTPStatus.BAD_REQUEST, "请选择有效的创作配方", code="validation_error")
    if prompt_mode != "recipe":
        recipe_id = ""
        recipe_version = ""

    upstream_payload: dict[str, Any] = {
        "model": model,
        "prompt": append_restricted_destination_guard(effective_prompt),
        **image_options,
    }
    if size and size != "auto":
        upstream_payload["size"] = size
    if parsed.sample_count > 1:
        upstream_payload["n"] = parsed.sample_count

    async def _run_generate_upstream() -> dict[str, Any]:
        return await _run_json_candidates(
            client=client,
            endpoint_url=endpoint_url,
            api_key=api_key,
            payload=upstream_payload,
            user_agent=settings.upstream_user_agent,
            sample_count=parsed.sample_count,
        )

    metadata = request_metadata({**payload, **image_options}, size=size)
    lineage_metadata: dict[str, Any] = {
        "original_prompt": original_prompt,
        "effective_prompt": effective_prompt,
        "prompt_mode": prompt_mode,
    }
    if itinerary_id:
        lineage_metadata["itinerary_id"] = itinerary_id
    if recipe_id:
        lineage_metadata["recipe_id"] = recipe_id
    if recipe_version:
        lineage_metadata["recipe_version"] = recipe_version
    if recipe is not None:
        lineage_metadata["recipe_title"] = recipe["title"]
    metadata.update(lineage_metadata)

    return await _finalize_with_size_retry(
        run_upstream=_run_generate_upstream,
        sample_count=parsed.sample_count,
        settings=settings,
        client=client,
        save_context={
            "mode": mode,
            "prompt": effective_prompt,
            "model": model,
            "endpoint_url": endpoint_url,
            "transport": "images-generate",
            "strict_size": strict_size,
            "sample_count": parsed.sample_count,
            "logo_requested": parsed.logo_requested,
            **lineage_metadata,
            **_user_metadata(user),
            **metadata,
        },
        extra={
            "mode": mode,
            "prompt": effective_prompt,
            **lineage_metadata,
            **({"recipe": recipe} if recipe is not None else {}),
            "model": model,
            "logo_requested": parsed.logo_requested,
            "sample_count": parsed.sample_count,
            **({"user": user.public_dict()} if user else {}),
            **metadata,
            "endpoint_url": endpoint_url,
        },
    )


async def handle_edit(
    body: Any, settings: Settings, client: UpstreamClient, user: AuthUser | None = None
) -> dict[str, Any]:
    payload = _ensure_dict(body)
    if not payload.get("image") and not payload.get("images"):
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 image 文件", code="bad_request")
    parsed = _validate_request(EditRequest, payload)

    endpoint_url = validate_url(
        parsed.endpoint_url or settings.default_edit_url,
        "编辑接口 URL",
    )
    model = (parsed.model or settings.default_model).strip() or settings.default_model
    api_key = (parsed.api_key or settings.default_api_key).strip()
    _ensure_no_restricted_destination_text(parsed.prompt)
    itinerary_id = _resolve_itinerary_id(explicit_id=parsed.itinerary_id, prompt=parsed.prompt)
    effective_prompt = _append_itinerary_id_badge_prompt(parsed.prompt, itinerary_id)
    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key", code="bad_request")

    image_parts = _request_image_parts(
        image=parsed.image,
        images=parsed.images,
        max_image_bytes=settings.max_image_bytes,
    )
    if not image_parts:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 image 文件", code="bad_request")
    mask_part = _prepare_mask(parsed.mask, settings.max_image_bytes) if parsed.mask else None

    files_for_multipart = [*image_parts, *([mask_part] if mask_part else [])]
    size = (parsed.size or "").strip()
    _validate_exact_image_size(size)
    strict_size = _strict_requested_size(size)
    image_options = _highest_quality_image_options(openai_image_options(payload))
    fields: dict[str, Any] = {
        "model": model,
        "prompt": append_restricted_destination_guard(effective_prompt),
        **image_options,
    }
    if size and size != "auto":
        fields["size"] = size
    if parsed.sample_count > 1:
        fields["n"] = parsed.sample_count

    async def _run_edit_upstream() -> dict[str, Any]:
        return await _run_multipart_candidates(
            client=client,
            endpoint_url=endpoint_url,
            api_key=api_key,
            fields=fields,
            files=files_for_multipart,
            user_agent=settings.upstream_user_agent,
            sample_count=parsed.sample_count,
        )

    metadata = request_metadata({**payload, **image_options}, size=size or None)
    if itinerary_id:
        metadata["itinerary_id"] = itinerary_id
        metadata["effective_prompt"] = effective_prompt
    mode = (parsed.mode or "edit").strip() or "edit"
    image_metadata = _image_reference_metadata(image_parts)

    return await _finalize_with_size_retry(
        run_upstream=_run_edit_upstream,
        sample_count=parsed.sample_count,
        settings=settings,
        client=client,
        save_context={
            "mode": mode,
            "prompt": effective_prompt,
            "model": model,
            "endpoint_url": endpoint_url,
            **image_metadata,
            "mask_image_name": mask_part["filename"] if mask_part else None,
            "transport": "images-edit",
            "strict_size": strict_size,
            "sample_count": parsed.sample_count,
            "logo_requested": parsed.logo_requested,
            **_user_metadata(user),
            **metadata,
        },
        extra={
            "mode": mode,
            "prompt": effective_prompt,
            "model": model,
            "logo_requested": parsed.logo_requested,
            **metadata,
            "endpoint_url": endpoint_url,
            **image_metadata,
            "mask_image_name": mask_part["filename"] if mask_part else None,
            "sample_count": parsed.sample_count,
            **({"user": user.public_dict()} if user else {}),
        },
    )


def _responses_input_content(prompt: str, image_file_ids: list[str]) -> list[dict[str, str]]:
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
    for image_file_id in image_file_ids:
        content.append({"type": "input_image", "file_id": image_file_id})
    return content


def _responses_inline_input_content(prompt: str, image_parts: list[dict[str, Any]]) -> list[dict[str, str]]:
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
    for image_part in image_parts:
        image_b64 = base64.b64encode(image_part["data"]).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{image_part['content_type']};base64,{image_b64}",
            }
        )
    return content


async def handle_responses_image(
    body: Any, settings: Settings, client: UpstreamClient, user: AuthUser | None = None
) -> dict[str, Any]:
    payload = _ensure_dict(body)
    parsed = _validate_request(ResponsesImageRequest, payload)

    endpoint_url = validate_url(
        parsed.endpoint_url or settings.default_responses_url,
        "Responses 图像接口 URL",
    )
    model = (parsed.model or settings.default_responses_model).strip() or DEFAULT_RESPONSES_MODEL
    model = _normalize_legacy_client_responses_model(
        model,
        storage_version=parsed.responses_model_storage_version,
        default_model=settings.default_responses_model,
    )
    api_key = (parsed.api_key or settings.default_api_key).strip()
    size = (parsed.size or settings.default_size).strip() or settings.default_size
    _validate_exact_image_size(size)
    strict_size = _strict_requested_size(size)
    image_options = _highest_quality_image_options(openai_image_options(payload))

    _ensure_no_restricted_destination_text(parsed.prompt)
    itinerary_id = _resolve_itinerary_id(explicit_id=parsed.itinerary_id, prompt=parsed.prompt)
    effective_prompt = _append_itinerary_id_badge_prompt(parsed.prompt, itinerary_id)
    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key", code="bad_request")

    image_parts = _request_image_parts(
        image=parsed.image,
        images=parsed.images,
        max_image_bytes=settings.max_image_bytes,
    )
    image_parts = [part for part in image_parts if part.get("data")]

    image_file_ids: list[str] = []
    files_endpoint_url: str | None = None
    upload_error: APIError | None = None
    if image_parts:
        files_endpoint_url = sibling_endpoint_url(endpoint_url, "files")
        for image_part in image_parts:
            try:
                upload_response = await client.run_file_upload(
                    files_endpoint_url,
                    api_key,
                    image_part,
                    settings.upstream_user_agent,
                )
                image_file_id = str(upload_response.get("id") or "").strip()
                if image_file_id:
                    image_file_ids.append(image_file_id)
            except APIError as exc:
                upload_error = exc
                image_file_ids = []
                if not parsed.allow_inline_fallback:
                    raise
                log_event(
                    logger,
                    logging.WARNING,
                    "responses_image_file_upload_fallback",
                    endpoint_url=endpoint_url,
                    files_endpoint_url=files_endpoint_url,
                    filename=image_part["filename"],
                    file_bytes=len(image_part["data"]),
                    upload_error=exc.message,
                )
                break

    tool: dict[str, Any] = {"type": "image_generation"}
    if size and size != "auto":
        tool["size"] = size
    if parsed.sample_count > 1:
        tool["n"] = parsed.sample_count
    for key in ("quality", "background", "output_format", "output_compression", "moderation"):
        if key in image_options:
            tool[key] = image_options[key]
    if parsed.mask is not None:
        mask_info = _validate_image_size(parsed.mask, settings.max_image_bytes)
        mask_b64 = base64.b64encode(mask_info["data"]).decode("ascii")
        mask_mime = str(mask_info.get("content_type") or "image/png")
        tool["input_image_mask"] = {"image_url": f"data:{mask_mime};base64,{mask_b64}"}

    guarded_prompt = append_restricted_destination_guard(effective_prompt)
    if strict_size and size and size != "auto":
        # The image_generation tool's `size` param is treated as advisory by
        # some gateways (they "lazily" return a downscaled canvas). Restating
        # the requirement in the prompt measurably improves compliance.
        guarded_prompt = (
            f"{guarded_prompt.rstrip()}\n\n"
            f"画布尺寸要求：最终输出图片必须精确为 {size} 像素（宽x高），"
            "不得缩小画布、更换为其它分辨率或改变宽高比。"
        )
    upstream_payload = {
        "model": model,
        "instructions": RESPONSES_IMAGE_INSTRUCTIONS,
        **_responses_reasoning_options(model),
        "stream": True,
        "input": [
            {
                "role": "user",
                "content": (
                    _responses_input_content(guarded_prompt, image_file_ids)
                    if upload_error is None
                    else _responses_inline_input_content(guarded_prompt, image_parts)
                ),
            }
        ],
        "tools": [tool],
    }

    async def _run_responses_upstream() -> dict[str, Any]:
        try:
            return await client.run_responses(
                endpoint_url, api_key, upstream_payload, settings.upstream_user_agent
            )
        except APIError as exc:
            # `n` is not part of the official image_generation tool schema; strict
            # upstreams reject the whole request. Mirror the Images-API fallback:
            # retry once without it when the error clearly points at the field.
            if (
                "n" in tool
                and exc.status == HTTPStatus.BAD_REQUEST
                and _error_mentions_sample_count(exc)
            ):
                log_event(
                    logger,
                    logging.WARNING,
                    "responses_image_sample_count_fallback",
                    endpoint_url=endpoint_url,
                    sample_count=parsed.sample_count,
                    status=exc.status,
                    message=exc.message,
                )
                tool.pop("n", None)
                return await client.run_responses(
                    endpoint_url, api_key, upstream_payload, settings.upstream_user_agent
                )
            raise

    metadata = request_metadata({**payload, **image_options}, size=size)
    if itinerary_id:
        metadata["itinerary_id"] = itinerary_id
        metadata["effective_prompt"] = effective_prompt
    mode = (parsed.mode or ("reference" if image_parts else "responses")).strip() or "responses"
    image_metadata = _image_reference_metadata(image_parts)

    return await _finalize_with_size_retry(
        run_upstream=_run_responses_upstream,
        sample_count=parsed.sample_count,
        settings=settings,
        client=client,
        save_context={
            "mode": mode,
            "prompt": effective_prompt,
            "model": model,
            "endpoint_url": endpoint_url,
            "files_endpoint_url": files_endpoint_url,
            **image_metadata,
            "source_file_id": image_file_ids[0] if image_file_ids else None,
            "source_file_ids": image_file_ids,
            "file_upload_fallback": bool(upload_error),
            "file_upload_error": upload_error.message if upload_error else None,
            "transport": "responses-image",
            "strict_size": strict_size,
            "sample_count": parsed.sample_count,
            "logo_requested": parsed.logo_requested,
            **_user_metadata(user),
            **metadata,
        },
        extra={
            "mode": mode,
            "prompt": effective_prompt,
            "model": model,
            "logo_requested": parsed.logo_requested,
            **metadata,
            "endpoint_url": endpoint_url,
            "files_endpoint_url": files_endpoint_url,
            **image_metadata,
            "source_file_id": image_file_ids[0] if image_file_ids else None,
            "source_file_ids": image_file_ids,
            "file_upload_fallback": bool(upload_error),
            "sample_count": parsed.sample_count,
            **({"user": user.public_dict()} if user else {}),
        },
    )


async def _finalize_image_response(
    *,
    upstream_response: dict[str, Any],
    settings: Settings,
    client: UpstreamClient,
    save_context: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    fetch_remote_sync = _make_remote_fetcher(client)
    saved = await anyio.to_thread.run_sync(
        lambda: prepare_image_payload(
            upstream_response,
            data_dir=settings.data_dir,
            outputs_dir=settings.outputs_dir,
            user_agent=settings.upstream_user_agent,
            save_context=save_context,
            fetch_remote=fetch_remote_sync,
        )
    )
    # An empty upstream response (no candidates) must be a clear error, not a blank
    # 200 that gets recorded as a "succeeded" job with 0 images. The itinerary path
    # catches this code to surface its own message / fallback.
    if int(saved.get("candidate_count") or 0) <= 0:
        raise APIError(
            HTTPStatus.BAD_GATEWAY,
            "图片生成接口这次没有返回图片，请稍后重试。",
            compact_raw_response(upstream_response),
            code="upstream_no_image",
        )
    _mark_image_size_mismatch(saved, save_context)
    return {**extra, **saved}


def _saved_pixel_count(saved: dict[str, Any]) -> int:
    total = 0
    images = saved.get("images")
    for image in images if isinstance(images, list) else []:
        if isinstance(image, dict):
            width = image.get("saved_image_width")
            height = image.get("saved_image_height")
            if isinstance(width, int) and isinstance(height, int):
                total += width * height
    return total


def _discard_saved_result_files(saved: dict[str, Any]) -> None:
    """Best-effort removal of a losing retry attempt's files so retries don't
    litter the outputs dir (only the returned result gets DB records)."""

    images = saved.get("images")
    for image in images if isinstance(images, list) else []:
        if not isinstance(image, dict):
            continue
        for key in ("saved_image_path", "saved_metadata_path"):
            path_text = str(image.get(key) or "")
            if path_text:
                with suppress(OSError):
                    Path(path_text).unlink()


async def _finalize_with_size_retry(
    *,
    run_upstream: Callable[[], Awaitable[dict[str, Any]]],
    settings: Settings,
    client: UpstreamClient,
    save_context: dict[str, Any],
    extra: dict[str, Any],
    sample_count: int,
) -> dict[str, Any]:
    """Retry the (paid) upstream call when it "lazily" returns a smaller size.

    Production gateways honor exact poster sizes most of the time but
    intermittently downscale under load; a plain local upscale cannot recover
    the missing detail, so the effective fix is to try again and keep the
    attempt closest to the target. Scope is deliberately narrow: exact-size
    requests with sample_count == 1, up to size_mismatch_max_retries extra
    calls (0 disables).
    """

    max_retries = (
        settings.size_mismatch_max_retries
        if save_context.get("strict_size") and sample_count == 1
        else 0
    )
    best: dict[str, Any] | None = None
    retries_used = 0
    for attempt in range(max_retries + 1):
        try:
            upstream_response = await run_upstream()
            saved = await _finalize_image_response(
                upstream_response=upstream_response,
                settings=settings,
                client=client,
                save_context=save_context,
                extra=extra,
            )
        except APIError:
            if best is not None:
                # A retry failing outright must not discard a usable result.
                break
            raise
        retries_used = attempt
        if not saved.get("size_mismatch"):
            if best is not None:
                _discard_saved_result_files(best)
            if attempt:
                saved["size_mismatch_retries"] = attempt
            return saved
        if best is None:
            best = saved
        elif _saved_pixel_count(saved) > _saved_pixel_count(best):
            _discard_saved_result_files(best)
            best = saved
        else:
            _discard_saved_result_files(saved)
        if attempt < max_retries:
            log_event(
                logger,
                logging.WARNING,
                "size_mismatch_retry",
                requested_size=str(save_context.get("requested_size") or save_context.get("size") or ""),
                actual_size=str(saved.get("actual_size") or ""),
                attempt=attempt + 1,
                max_retries=max_retries,
            )
    assert best is not None
    if retries_used:
        best["size_mismatch_retries"] = retries_used
        retry_note = f"已自动重新生成 {retries_used} 次，上游仍未按目标尺寸返回，已保留其中最接近的一次。"
        message = str(best.get("size_mismatch_message") or "").rstrip()
        best["size_mismatch_message"] = f"{message}{retry_note}" if message else retry_note
        images = best.get("images")
        for image in images if isinstance(images, list) else []:
            if isinstance(image, dict) and image.get("size_mismatch"):
                candidate_message = str(image.get("size_mismatch_message") or "").rstrip()
                image["size_mismatch_message"] = (
                    f"{candidate_message}{retry_note}" if candidate_message else retry_note
                )
    return best


def _make_remote_fetcher(client: UpstreamClient) -> Any:
    """Bridge async image download into the sync prepare_image_payload helper.

    `prepare_image_payload` runs in a worker thread; this fetcher schedules the
    async download back onto the main event loop without blocking it.
    """

    def fetcher(url: str, user_agent: str) -> tuple[bytes, str]:
        return anyio.from_thread.run(client.fetch_image, url, user_agent)

    return fetcher


def _ensure_dict(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise APIError(HTTPStatus.BAD_REQUEST, "请求体必须是 JSON 对象", code="bad_request")
    return payload


def _validate_request(model_cls: Any, payload: dict[str, Any]) -> Any:
    try:
        return model_cls.model_validate(payload)
    except Exception as exc:
        message = _first_error_message(exc) or "请求参数无效"
        raise APIError(HTTPStatus.BAD_REQUEST, message, str(exc), code="validation_error") from exc


def _first_error_message(exc: Exception) -> str | None:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        try:
            issues = errors()
            if issues:
                first = issues[0]
                msg = first.get("msg") or first.get("message") or ""
                if isinstance(msg, str):
                    cleaned = msg.removeprefix("Value error,").strip()
                    return cleaned or None
        except Exception:
            return None
    return None


__all__ = [
    "ImageResultResponse",
    "create_router",
    "handle_edit",
    "handle_generate",
    "handle_responses_image",
]

from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from http import HTTPStatus
from pathlib import Path
from typing import Any

import anyio
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import FileResponse, JSONResponse

from . import __version__
from .auth import (
    AccountLockedError,
    AuthStore,
    AuthUser,
    InvalidCredentialsError,
    UserExistsError,
    normalize_username,
)
from .config import Settings
from .errors import APIError
from .logging_config import get_logger, get_request_id, log_event
from .notifications import send_bug_report_notification
from .schemas import (
    AdminCreateUserRequest,
    AdminResetPasswordRequest,
    AuthRequest,
    BugReportRequest,
    ConfigResponse,
    CopyrightRiskRequest,
    EditRequest,
    FeedbackRequest,
    FilePayload,
    FinalImageRequest,
    GenerateRequest,
    HealthResponse,
    ImageResultResponse,
    PasswordResetRequest,
    ReadinessResponse,
    ResponsesImageRequest,
    ShareResultRequest,
    UserPreferencesRequest,
)
from .storage import (
    detect_image_mime,
    resolve_storage_path,
    sanitize_filename,
    save_derived_output_image,
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

JSON_BODY = Body(...)
PASSWORD_RESET_REQUEST_MESSAGE = "如果账号存在，管理员会看到找回申请。请联系管理员获取新密码。"

def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_client(request: Request) -> UpstreamClient:
    return request.app.state.upstream_client


def get_auth_store(request: Request) -> AuthStore:
    return request.app.state.auth_store


def _get_session_token(request: Request, settings: Settings) -> str:
    return request.cookies.get(settings.auth_cookie_name, "").strip()


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


def _resolve_output_file(settings: Settings, relative_path: str) -> Path:
    cleaned = relative_path.strip().lstrip("/")
    output_prefix = "outputs/"
    if not cleaned.startswith(output_prefix):
        raise APIError(HTTPStatus.FORBIDDEN, "非法文件路径", code="forbidden")
    output_relative_path = cleaned[len(output_prefix) :]
    if not output_relative_path:
        raise APIError(HTTPStatus.FORBIDDEN, "非法文件路径", code="forbidden")
    target_path = resolve_storage_path(settings.outputs_dir, output_relative_path)
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".json"}
    if target_path.suffix.lower() not in allowed_suffixes:
        raise APIError(HTTPStatus.FORBIDDEN, "非法文件类型", code="forbidden")
    return target_path


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
    return exc.status in {
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
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

    deficit = sample_count - len(_candidate_items(initial))
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
            bug_report_notifications_enabled=bool(settings.bug_report_webhook_url),
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

    @router.get("/files/{relative_path:path}")
    async def files(
        relative_path: str,
        request: Request,
        user: AuthUser | None = Depends(require_current_user),
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> FileResponse:
        settings = get_settings(request)
        target_path = _resolve_output_file(settings, relative_path)
        if not target_path.is_file():
            raise APIError(HTTPStatus.NOT_FOUND, "文件不存在", code="not_found")
        if settings.auth_enabled and target_path.suffix.lower() != ".json":
            await anyio.to_thread.run_sync(
                lambda: auth_store.record_image_delivery(
                    relative_path=relative_path,
                    user_id=user.id if user else None,
                    status_code=200,
                    client_host=request.client.host if request.client else "",
                    user_agent=request.headers.get("user-agent", ""),
                )
            )
        return FileResponse(
            target_path,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
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
            user = await anyio.to_thread.run_sync(auth_store.create_user, parsed.username, parsed.password)
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
        auth_store: AuthStore = Depends(get_auth_store),
    ) -> dict[str, Any]:
        payload = _ensure_dict(body)
        parsed = _validate_request(PasswordResetRequest, payload)
        with suppress(ValueError):
            await anyio.to_thread.run_sync(
                lambda: auth_store.request_password_reset(
                    parsed.username,
                    client_host=request.client.host if request.client else "",
                    user_agent=request.headers.get("user-agent", ""),
                )
            )
        return {"status": "ok", "message": PASSWORD_RESET_REQUEST_MESSAGE}

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
    ) -> dict[str, Any]:
        if user is None:
            raise APIError(HTTPStatus.UNAUTHORIZED, "请先登录", code="unauthorized")
        payload = _ensure_dict(body)
        parsed = _validate_request(UserPreferencesRequest, payload)
        preferences = await anyio.to_thread.run_sync(
            lambda: auth_store.update_user_preferences(
                user_id=user.id,
                default_model=parsed.default_model,
                default_responses_model=parsed.default_responses_model,
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
                }
                for listed_user in users
            ]
        }

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
    model = (parsed.model or settings.default_responses_model).strip() or settings.default_responses_model
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


def _should_track_generation_job(path: str) -> bool:
    return path in {"/api/generate", "/api/edit", "/api/responses-image"}


def _job_sample_count(payload: dict[str, Any]) -> int:
    try:
        parsed = int(payload.get("sample_count") or 1)
    except (TypeError, ValueError):
        return 1
    return max(1, min(parsed, 3))


def _job_mode(path: str, payload: dict[str, Any]) -> str:
    if path == "/api/generate":
        return "generate"
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
    }.get(path, "")


def _job_metadata(path: str, body: Any, user: AuthUser) -> dict[str, Any]:
    payload = body if isinstance(body, dict) else {}
    return {
        "request_id": get_request_id(),
        "user_id": user.id,
        "username": user.username,
        "endpoint_path": path,
        "mode": _job_mode(path, payload),
        "transport": _job_transport(path),
        "prompt": str(payload.get("prompt") or ""),
        "model": str(payload.get("model") or ""),
        "size": str(payload.get("size") or ""),
        "sample_count": _job_sample_count(payload),
        "logo_requested": bool(payload.get("logo_requested")),
    }


def _attach_generation_record_ids(
    result: dict[str, Any],
    *,
    job_id: int,
    image_records: list[dict[str, Any]],
) -> None:
    result["generation_job_id"] = job_id
    images = result.get("images")
    if isinstance(images, list):
        for image, record in zip(images, image_records, strict=False):
            if not isinstance(image, dict):
                continue
            image["generation_job_id"] = job_id
            image["generated_image_id"] = record["id"]
    if image_records:
        result["generated_image_id"] = image_records[0]["id"]


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
        if auth_store is not None and user is not None:
            if job_id is not None:
                image_records = await anyio.to_thread.run_sync(
                    lambda: auth_store.complete_generation_job(
                        job_id=job_id,
                        result=result,
                        elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                    )
                )
                _attach_generation_record_ids(result, job_id=job_id, image_records=image_records)
            await anyio.to_thread.run_sync(
                lambda: auth_store.record_usage(
                    user_id=user.id,
                    endpoint_path=path,
                    mode=str(result.get("mode") or ""),
                    image_count=_result_image_count(result),
                    saved_bytes=_result_saved_bytes(result),
                )
            )
    except APIError as exc:
        error_code = exc.code
        error_message = exc.message
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
    image_options = openai_image_options(payload)

    if not api_key:
        raise APIError(HTTPStatus.BAD_REQUEST, "缺少 API Key", code="bad_request")

    upstream_payload: dict[str, Any] = {
        "model": model,
        "prompt": parsed.prompt,
        **image_options,
    }
    if size and size != "auto":
        upstream_payload["size"] = size
    if parsed.sample_count > 1:
        upstream_payload["n"] = parsed.sample_count

    upstream_response = await _run_json_candidates(
        client=client,
        endpoint_url=endpoint_url,
        api_key=api_key,
        payload=upstream_payload,
        user_agent=settings.upstream_user_agent,
        sample_count=parsed.sample_count,
    )
    metadata = request_metadata({**payload, **image_options}, size=size)

    return await _finalize_image_response(
        upstream_response=upstream_response,
        settings=settings,
        client=client,
        save_context={
            "mode": "generate",
            "prompt": parsed.prompt,
            "model": model,
            "endpoint_url": endpoint_url,
            "transport": "images-generate",
            "sample_count": parsed.sample_count,
            "logo_requested": parsed.logo_requested,
            **_user_metadata(user),
            **metadata,
        },
        extra={
            "mode": "generate",
            "prompt": parsed.prompt,
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
    image_options = openai_image_options(payload)
    fields: dict[str, Any] = {
        "model": model,
        "prompt": parsed.prompt,
        **image_options,
    }
    if size and size != "auto":
        fields["size"] = size
    if parsed.sample_count > 1:
        fields["n"] = parsed.sample_count

    upstream_response = await _run_multipart_candidates(
        client=client,
        endpoint_url=endpoint_url,
        api_key=api_key,
        fields=fields,
        files=files_for_multipart,
        user_agent=settings.upstream_user_agent,
        sample_count=parsed.sample_count,
    )
    metadata = request_metadata({**payload, **image_options}, size=size or None)
    mode = (parsed.mode or "edit").strip() or "edit"
    image_metadata = _image_reference_metadata(image_parts)

    return await _finalize_image_response(
        upstream_response=upstream_response,
        settings=settings,
        client=client,
        save_context={
            "mode": mode,
            "prompt": parsed.prompt,
            "model": model,
            "endpoint_url": endpoint_url,
            **image_metadata,
            "mask_image_name": mask_part["filename"] if mask_part else None,
            "transport": "images-edit",
            "sample_count": parsed.sample_count,
            "logo_requested": parsed.logo_requested,
            **_user_metadata(user),
            **metadata,
        },
        extra={
            "mode": mode,
            "prompt": parsed.prompt,
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


def _responses_inline_input_content(
    prompt: str, image_parts: list[dict[str, Any]]
) -> list[dict[str, str]]:
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
    model = (parsed.model or settings.default_responses_model).strip() or settings.default_responses_model
    api_key = (parsed.api_key or settings.default_api_key).strip()
    size = (parsed.size or settings.default_size).strip() or settings.default_size
    image_options = openai_image_options(payload)

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

    upstream_payload = {
        "model": model,
        "stream": True,
        "input": [
            {
                "role": "user",
                "content": (
                    _responses_input_content(parsed.prompt, image_file_ids)
                    if upload_error is None
                    else _responses_inline_input_content(parsed.prompt, image_parts)
                ),
            }
        ],
        "tools": [tool],
    }

    upstream_response = await client.run_responses(
        endpoint_url, api_key, upstream_payload, settings.upstream_user_agent
    )
    metadata = request_metadata({**payload, **image_options}, size=size)
    mode = (parsed.mode or ("reference" if image_parts else "responses")).strip() or "responses"
    image_metadata = _image_reference_metadata(image_parts)

    return await _finalize_image_response(
        upstream_response=upstream_response,
        settings=settings,
        client=client,
        save_context={
            "mode": mode,
            "prompt": parsed.prompt,
            "model": model,
            "endpoint_url": endpoint_url,
            "files_endpoint_url": files_endpoint_url,
            **image_metadata,
            "source_file_id": image_file_ids[0] if image_file_ids else None,
            "source_file_ids": image_file_ids,
            "file_upload_fallback": bool(upload_error),
            "file_upload_error": upload_error.message if upload_error else None,
            "transport": "responses-image",
            "sample_count": parsed.sample_count,
            "logo_requested": parsed.logo_requested,
            **_user_metadata(user),
            **metadata,
        },
        extra={
            "mode": mode,
            "prompt": parsed.prompt,
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
    return {**extra, **saved}


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

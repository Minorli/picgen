from __future__ import annotations

import asyncio
import errno
import json
import logging
import random
import time
from http import HTTPStatus
from typing import Any, NoReturn, Protocol

import httpx

from ..errors import APIError
from ..logging_config import get_logger, log_event
from ..redaction import redact_sensitive_text
from ..storage import detect_image_mime
from .errors import (
    classify_upstream_error,
    compact_log_text,
    extract_error_message,
    public_upstream_error_message,
)
from .payload import ensure_json_object, normalize_responses_image_payload
from .responses import parse_sse_json_events, stream_events_to_image_payload
from .transport import ascii_multipart_filename, encode_multipart, upstream_headers

logger = get_logger("picgen.upstream.client")

_RETRY_STATUS = frozenset({HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.GATEWAY_TIMEOUT})


class UpstreamClient(Protocol):
    """Protocol for swappable HTTP clients used by routes (eases testing)."""

    async def run_json(
        self, url: str, api_key: str, payload: dict[str, Any], user_agent: str
    ) -> dict[str, Any]: ...

    async def run_multipart(
        self,
        url: str,
        api_key: str,
        fields: dict[str, Any],
        files: list[dict[str, Any]],
        user_agent: str,
    ) -> dict[str, Any]: ...

    async def run_file_upload(
        self,
        url: str,
        api_key: str,
        file_part: dict[str, Any],
        user_agent: str,
        purpose: str = "vision",
    ) -> dict[str, Any]: ...

    async def run_responses(
        self,
        url: str,
        api_key: str,
        payload: dict[str, Any],
        user_agent: str,
    ) -> dict[str, Any]: ...

    async def fetch_image(self, url: str, user_agent: str) -> tuple[bytes, str]: ...

    async def aclose(self) -> None: ...


class HttpxAsyncClient:
    """Async upstream client with connection pooling.

    Non-idempotent image generation/edit POSTs are sent once to avoid duplicate
    generations and double billing. Only idempotent image downloads retry.
    """

    def __init__(
        self,
        *,
        total_timeout: float = 600.0,
        connect_timeout: float = 15.0,
        max_connections: int = 64,
        max_keepalive: int = 16,
        max_retries: int = 2,
        retry_backoff: float = 0.75,
        max_image_bytes: int = 32 * 1024 * 1024,
        http2: bool = False,
    ) -> None:
        self.total_timeout = total_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.max_image_bytes = max_image_bytes
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=total_timeout,
                write=total_timeout,
                pool=connect_timeout,
            ),
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive,
            ),
            follow_redirects=True,
            http2=http2,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # --- public API -----------------------------------------------------

    async def run_json(
        self, url: str, api_key: str, payload: dict[str, Any], user_agent: str
    ) -> dict[str, Any]:
        body_bytes = json.dumps(payload).encode("utf-8")
        log_event(
            logger,
            logging.INFO,
            "upstream_json_start",
            url=url,
            model=payload.get("model"),
            size=payload.get("size"),
            prompt_chars=len(str(payload.get("prompt") or "")),
            body_bytes=len(body_bytes),
        )
        response = await self._send(
            "POST",
            url,
            content=body_bytes,
            headers=upstream_headers(
                user_agent,
                {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            ),
            event_prefix="upstream_json",
            action="生成接口",
        )
        text = response.text
        return ensure_json_object(self._parse_json(text, "生成接口"), "生成接口")

    async def run_multipart(
        self,
        url: str,
        api_key: str,
        fields: dict[str, Any],
        files: list[dict[str, Any]],
        user_agent: str,
    ) -> dict[str, Any]:
        body, content_type = encode_multipart(fields, files)
        log_event(
            logger,
            logging.INFO,
            "upstream_multipart_start",
            url=url,
            model=fields.get("model"),
            sample_count=fields.get("n"),
            prompt_chars=len(str(fields.get("prompt") or "")),
            files=",".join(str(p.get("filename")) for p in files),
            body_bytes=len(body),
        )
        response = await self._send(
            "POST",
            url,
            content=body,
            headers=upstream_headers(
                user_agent,
                {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": content_type,
                    "Accept": "application/json",
                },
            ),
            event_prefix="upstream_multipart",
            action="编辑接口",
        )
        return ensure_json_object(self._parse_json(response.text, "编辑接口"), "编辑接口")

    async def run_file_upload(
        self,
        url: str,
        api_key: str,
        file_part: dict[str, Any],
        user_agent: str,
        purpose: str = "vision",
    ) -> dict[str, Any]:
        upload_file = {
            "field_name": "file",
            "filename": ascii_multipart_filename(
                str(file_part["filename"]), str(file_part["content_type"])
            ),
            "content_type": file_part["content_type"],
            "data": file_part["data"],
        }
        body, content_type = encode_multipart({"purpose": purpose}, [upload_file])
        log_event(
            logger,
            logging.INFO,
            "upstream_file_upload_start",
            url=url,
            purpose=purpose,
            filename=file_part["filename"],
            upload_filename=upload_file["filename"],
            content_type=upload_file["content_type"],
            file_bytes=len(upload_file["data"]),
            body_bytes=len(body),
        )
        try:
            response = await self._send(
                "POST",
                url,
                content=body,
                headers=upstream_headers(
                    user_agent,
                    {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": content_type,
                        "Accept": "application/json",
                    },
                ),
                event_prefix="upstream_file_upload",
                action="Files 上传接口",
            )
        except APIError as exc:
            if exc.status >= 500 and "broken pipe" in (exc.message or "").lower():
                raise APIError(
                    HTTPStatus.BAD_GATEWAY,
                    "Files 上传接口在接收文件时断开连接",
                    (
                        "上游 /v1/files 在文件发送过程中主动关闭连接。"
                        "PicGen 会优先使用 Files 上传；如果上传副本足够小，会自动改走小体积 inline Responses 兜底。"
                    ),
                    code="upstream_error",
                ) from exc
            raise

        parsed = ensure_json_object(
            self._parse_json(response.text, "Files 上传接口"),
            "Files 上传接口",
        )
        if not str(parsed.get("id") or "").strip():
            details = json.dumps(parsed, ensure_ascii=False, indent=2)
            raise APIError(
                HTTPStatus.BAD_GATEWAY,
                "Files 上传接口没有返回 file id",
                details[:4000],
                code="upstream_error",
            )
        return parsed

    async def run_responses(
        self, url: str, api_key: str, payload: dict[str, Any], user_agent: str
    ) -> dict[str, Any]:
        body_bytes = json.dumps(payload).encode("utf-8")
        is_stream = bool(payload.get("stream"))
        log_event(
            logger,
            logging.INFO,
            "upstream_responses_start",
            url=url,
            model=payload.get("model"),
            prompt_chars=len(json.dumps(payload.get("input") or "", ensure_ascii=False)),
            body_bytes=len(body_bytes),
            stream=is_stream,
        )
        headers = upstream_headers(
            user_agent,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream" if is_stream else "application/json",
            },
        )

        started_at = time.perf_counter()
        try:
            async with self._client.stream("POST", url, content=body_bytes, headers=headers) as response:
                if response.status_code >= 400:
                    body_text = (await response.aread()).decode("utf-8", errors="replace")
                    self._raise_for_status(
                        response.status_code,
                        body_text,
                        url=url,
                        started_at=started_at,
                        event_prefix="upstream_responses",
                        attempt=0,
                    )
                content_type = response.headers.get("content-type", "")
                body_text = (await response.aread()).decode("utf-8", errors="replace")
                if "text/event-stream" in content_type or body_text.lstrip().startswith(("event:", "data:")):
                    return stream_events_to_image_payload(
                        parse_sse_json_events(body_text),
                        url=url,
                        started_at=started_at,
                    )
                log_event(
                    logger,
                    logging.INFO,
                    "upstream_responses_ok",
                    url=url,
                    elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                    body_chars=len(body_text),
                )
                parsed = ensure_json_object(
                    self._parse_json(body_text, "Responses 图像接口"),
                    "Responses 图像接口",
                )
                if payload.get("tools"):
                    return normalize_responses_image_payload(parsed)
                return parsed
        except APIError:
            raise
        except httpx.RequestError as exc:
            self._raise_network(exc, url=url, started_at=started_at, action="Responses 图像接口")

    async def fetch_image(self, url: str, user_agent: str) -> tuple[bytes, str]:
        headers = upstream_headers(user_agent, {"Accept": "image/*"})
        action = "下载上游返回图片"
        started_at = time.perf_counter()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                image_bytes, response_mime = await self._stream_download(
                    url, headers, started_at=started_at, attempt=attempt
                )
            except APIError as exc:
                # Never retry the locally-raised "image too large" rejection —
                # it is deterministic and each retry re-downloads up to the cap.
                if (
                    attempt < self.max_retries
                    and exc.status in _RETRY_STATUS
                    and exc.code != "upstream_image_too_large"
                ):
                    await self._sleep_for_retry(attempt, url=url, status=exc.status)
                    continue
                raise
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await self._sleep_for_retry(attempt, url=url, reason="timeout")
                    continue
                self._raise_network(exc, url=url, started_at=started_at, action=action)
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await self._sleep_for_retry(attempt, url=url, reason=str(exc))
                    continue
                self._raise_network(exc, url=url, started_at=started_at, action=action)
            else:
                if not image_bytes:
                    raise APIError(
                        HTTPStatus.BAD_GATEWAY,
                        "上游返回了空图片",
                        code="upstream_error",
                    )
                mime = response_mime if response_mime.startswith("image/") else detect_image_mime(image_bytes)
                log_event(
                    logger,
                    logging.INFO,
                    "upstream_image_ok",
                    url=url,
                    elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                    bytes=len(image_bytes),
                    response_mime=response_mime or None,
                    attempts=attempt + 1,
                )
                return image_bytes, mime

        assert last_exc is not None
        self._raise_network(last_exc, url=url, started_at=started_at, action=action)
        raise RuntimeError("unreachable")  # pragma: no cover

    async def _stream_download(
        self, url: str, headers: dict[str, str], *, started_at: float, attempt: int
    ) -> tuple[bytes, str]:
        """Download a remote image, enforcing ``max_image_bytes`` so a hostile or
        malfunctioning upstream cannot exhaust memory."""

        def _too_large() -> APIError:
            return APIError(
                HTTPStatus.BAD_GATEWAY,
                f"上游返回的图片过大，超过 {self.max_image_bytes // 1024} KB 上限",
                code="upstream_image_too_large",
            )

        async with self._client.stream("GET", url, headers=headers) as response:
            if response.status_code >= 400:
                body_text = (await response.aread()).decode("utf-8", errors="replace")
                self._raise_for_status(
                    response.status_code,
                    body_text,
                    url=url,
                    started_at=started_at,
                    event_prefix="upstream_image",
                    attempt=attempt,
                )
            declared = response.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > self.max_image_bytes:
                raise _too_large()
            buffer = bytearray()
            async for chunk in response.aiter_bytes():
                buffer.extend(chunk)
                if len(buffer) > self.max_image_bytes:
                    raise _too_large()
            response_mime = response.headers.get("content-type", "").split(";", 1)[0].strip()
            return bytes(buffer), response_mime

    # --- internals ------------------------------------------------------

    async def _send(
        self,
        method: str,
        url: str,
        *,
        content: bytes | None,
        headers: dict[str, str],
        event_prefix: str,
        action: str,
    ) -> httpx.Response:
        started_at = time.perf_counter()
        try:
            response = await self._client.request(method, url, content=content, headers=headers)
        except httpx.TimeoutException as exc:
            self._raise_network(exc, url=url, started_at=started_at, action=action)
        except httpx.RequestError as exc:
            # RequestError covers NetworkError AND its siblings — notably
            # RemoteProtocolError (server closed a kept-alive connection midway),
            # which previously escaped as an unhandled 500.
            if self._is_broken_pipe(exc):
                raise APIError(
                    HTTPStatus.BAD_GATEWAY,
                    f"{action}在接收数据时断开连接",
                    code="upstream_error",
                ) from exc
            self._raise_network(exc, url=url, started_at=started_at, action=action)

        if response.status_code >= 400:
            self._raise_for_status(
                response.status_code,
                response.text,
                url=url,
                started_at=started_at,
                event_prefix=event_prefix,
                attempt=0,
            )

        log_event(
            logger,
            logging.INFO,
            f"{event_prefix}_ok",
            url=url,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            body_chars=len(response.text) if hasattr(response, "text") else None,
            attempts=1,
        )
        return response

    @staticmethod
    def _is_broken_pipe(exc: BaseException) -> bool:
        cause: BaseException | None = exc
        while cause is not None:
            if isinstance(cause, BrokenPipeError):
                return True
            errno_value = getattr(cause, "errno", None)
            if errno_value == errno.EPIPE:
                return True
            cause = cause.__cause__ or cause.__context__
        return False

    async def _sleep_for_retry(self, attempt: int, **fields: Any) -> None:
        delay = self.retry_backoff * (2**attempt) + random.uniform(0, 0.25)
        log_event(
            logger,
            logging.WARNING,
            "upstream_retry",
            attempt=attempt + 1,
            delay_ms=round(delay * 1000, 1),
            **fields,
        )
        await asyncio.sleep(delay)

    def _raise_for_status(
        self,
        status: int,
        body_text: str,
        *,
        url: str,
        started_at: float,
        event_prefix: str,
        attempt: int,
    ) -> None:
        log_event(
            logger,
            logging.WARNING,
            f"{event_prefix}_http_error",
            url=url,
            status=status,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            attempt=attempt + 1,
            body_chars=len(body_text),
            body_preview=compact_log_text(redact_sensitive_text(body_text)),
        )
        upstream_message, upstream_details = extract_error_message(body_text)
        code = classify_upstream_error(status, upstream_message, upstream_details)
        public_message = public_upstream_error_message(status, code, _action_from_event_prefix(event_prefix))
        attempts = attempt + 1
        retryable_context = event_prefix == "upstream_image"
        if retryable_context and status in _RETRY_STATUS and attempts >= self.max_retries + 1:
            public_message = f"{public_message} 已自动尝试 {attempts} 次，仍未成功。"
        detail_lines = [f"上游状态码：{status}", f"上游错误：{upstream_message}"]
        if retryable_context and status in _RETRY_STATUS and attempts >= self.max_retries + 1:
            detail_lines.append(f"上游连续返回 {status}，已自动尝试 {attempts} 次后停止。")
        if upstream_details:
            detail_lines.extend(["", upstream_details])
        raise APIError(status, public_message, "\n".join(detail_lines)[:4000], code=code)

    def _raise_network(
        self,
        exc: BaseException,
        *,
        url: str,
        started_at: float,
        action: str,
    ) -> NoReturn:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
        if isinstance(exc, httpx.TimeoutException):
            log_event(
                logger,
                logging.WARNING,
                "upstream_timeout",
                url=url,
                elapsed_ms=elapsed_ms,
                timeout_s=self.total_timeout,
                timeout_kind=type(exc).__name__,
                action=action,
            )
            # PoolTimeout/ConnectTimeout fire after the (short) connect window,
            # not the total read timeout — a message blaming "上游超过 N 秒没有
            # 返回" would misdirect diagnosis at the upstream.
            if isinstance(exc, httpx.PoolTimeout):
                detail = (
                    f"{action}排队超时：本地连接池已被占满，等待空闲连接超过阈值。\n"
                    "通常是并发生成过多；请稍后再试或提高 PICGEN_UPSTREAM_MAX_CONNECTIONS。"
                )
            elif isinstance(exc, httpx.ConnectTimeout):
                detail = f"{action}连接超时：无法在限定时间内与上游建立连接。请检查网络或上游地址。"
            else:
                detail = (
                    f"{action}超时：上游接口超过 {self.total_timeout:.0f} 秒没有返回。\n"
                    "本地服务已经等满超时阈值。请降低图片尺寸/质量，或换用没有短网关限制的上游接口。"
                )
            raise APIError(
                HTTPStatus.GATEWAY_TIMEOUT,
                "图片生成服务响应超时，请稍后再试。",
                detail,
                code="upstream_timeout",
            ) from exc
        log_event(
            logger,
            logging.WARNING,
            "upstream_network_error",
            url=url,
            elapsed_ms=elapsed_ms,
            reason=str(exc),
            action=action,
        )
        raise APIError(
            HTTPStatus.BAD_GATEWAY,
            "暂时无法连接图片生成服务，请稍后再试。",
            f"无法连接{action}: {redact_sensitive_text(str(exc), limit=1200)}",
            code="upstream_network_error",
        ) from exc

    @staticmethod
    def _parse_json(text: str, context: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise APIError(
                HTTPStatus.BAD_GATEWAY,
                "图片生成服务返回了无法解析的响应，请稍后再试。",
                f"{context} 返回了无法解析的 JSON。\n{redact_sensitive_text(text, limit=3600)}",
                code="upstream_invalid_response",
            ) from exc


def _action_from_event_prefix(event_prefix: str) -> str:
    if "multipart" in event_prefix:
        return "编辑接口"
    if "responses" in event_prefix:
        return "Responses 图像接口"
    if "image" in event_prefix:
        return "下载上游返回图片"
    return "生成接口"


# --- module-level singleton with async lifecycle -----------------------

_default_client: HttpxAsyncClient | None = None
_default_lock = asyncio.Lock()


async def get_default_client(
    *,
    total_timeout: float = 600.0,
    connect_timeout: float = 15.0,
    max_connections: int = 64,
    max_keepalive: int = 16,
    max_retries: int = 2,
    retry_backoff: float = 0.75,
    max_image_bytes: int = 32 * 1024 * 1024,
) -> HttpxAsyncClient:
    global _default_client
    async with _default_lock:
        if _default_client is None:
            _default_client = HttpxAsyncClient(
                total_timeout=total_timeout,
                connect_timeout=connect_timeout,
                max_connections=max_connections,
                max_keepalive=max_keepalive,
                max_retries=max_retries,
                retry_backoff=retry_backoff,
                max_image_bytes=max_image_bytes,
            )
    return _default_client


async def shutdown_default_client() -> None:
    global _default_client
    async with _default_lock:
        if _default_client is not None:
            await _default_client.aclose()
            _default_client = None



from __future__ import annotations

import asyncio
import errno
import json
import logging
import random
import time
from http import HTTPStatus
from typing import Any, Protocol

import anyio
import httpx

from ..errors import APIError
from ..logging_config import get_logger, log_event
from ..storage import detect_image_mime
from .errors import compact_log_text, extract_error_message
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
    """Async upstream client with connection pooling and exponential-backoff retries."""

    def __init__(
        self,
        *,
        total_timeout: float = 600.0,
        connect_timeout: float = 15.0,
        max_connections: int = 64,
        max_keepalive: int = 16,
        max_retries: int = 2,
        retry_backoff: float = 0.75,
        http2: bool = False,
    ) -> None:
        self.total_timeout = total_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
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
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with self._client.stream(
                    "POST", url, content=body_bytes, headers=headers
                ) as response:
                    if response.status_code >= 400:
                        body_text = (await response.aread()).decode("utf-8", errors="replace")
                        self._raise_for_status(
                            response.status_code,
                            body_text,
                            url=url,
                            started_at=started_at,
                            event_prefix="upstream_responses",
                            attempt=attempt,
                        )
                    content_type = response.headers.get("content-type", "")
                    body_text = (await response.aread()).decode("utf-8", errors="replace")
                    if "text/event-stream" in content_type or body_text.lstrip().startswith(
                        ("event:", "data:")
                    ):
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
            except APIError as exc:
                if attempt < self.max_retries and exc.status in _RETRY_STATUS:
                    await self._sleep_for_retry(attempt, url=url, status=exc.status)
                    continue
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await self._sleep_for_retry(attempt, url=url, reason=str(exc))
                    continue
                self._raise_network(exc, url=url, started_at=started_at, action="Responses 图像接口")

        assert last_exc is not None  # for type-checker; loop guarantees this
        self._raise_network(last_exc, url=url, started_at=started_at, action="Responses 图像接口")
        raise RuntimeError("unreachable")  # pragma: no cover

    async def fetch_image(self, url: str, user_agent: str) -> tuple[bytes, str]:
        started_at = time.perf_counter()
        response = await self._send(
            "GET",
            url,
            content=None,
            headers=upstream_headers(user_agent, {"Accept": "image/*"}),
            event_prefix="upstream_image",
            action="下载上游返回图片",
        )
        image_bytes = response.content
        if not image_bytes:
            raise APIError(
                HTTPStatus.BAD_GATEWAY,
                "上游返回了空图片",
                code="upstream_error",
            )
        response_mime = response.headers.get("content-type", "").split(";", 1)[0].strip()
        if response_mime.startswith("image/"):
            return image_bytes, response_mime
        log_event(
            logger,
            logging.DEBUG,
            "upstream_image_mime_inferred",
            url=url,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
            response_mime=response_mime,
        )
        return image_bytes, detect_image_mime(image_bytes)

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
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(
                    method, url, content=content, headers=headers
                )
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await self._sleep_for_retry(attempt, url=url, reason="timeout")
                    continue
                self._raise_network(exc, url=url, started_at=started_at, action=action)
            except httpx.NetworkError as exc:
                last_exc = exc
                if self._is_broken_pipe(exc):
                    raise APIError(
                        HTTPStatus.BAD_GATEWAY,
                        f"{action}在接收数据时断开连接",
                        code="upstream_error",
                    ) from exc
                if attempt < self.max_retries:
                    await self._sleep_for_retry(attempt, url=url, reason=str(exc))
                    continue
                self._raise_network(exc, url=url, started_at=started_at, action=action)

            if response.status_code >= 400:
                body_text = response.text
                try:
                    self._raise_for_status(
                        response.status_code,
                        body_text,
                        url=url,
                        started_at=started_at,
                        event_prefix=event_prefix,
                        attempt=attempt,
                    )
                except APIError as exc:
                    if attempt < self.max_retries and exc.status in _RETRY_STATUS:
                        await self._sleep_for_retry(attempt, url=url, status=exc.status)
                        continue
                    raise

            log_event(
                logger,
                logging.INFO,
                f"{event_prefix}_ok",
                url=url,
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 1),
                body_chars=len(response.text) if hasattr(response, "text") else None,
                attempts=attempt + 1,
            )
            return response

        assert last_exc is not None
        self._raise_network(last_exc, url=url, started_at=started_at, action=action)
        raise RuntimeError("unreachable")  # pragma: no cover

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
            body_preview=compact_log_text(body_text),
        )
        message, details = extract_error_message(body_text)
        raise APIError(status, message, details, code="upstream_error")

    def _raise_network(
        self,
        exc: BaseException,
        *,
        url: str,
        started_at: float,
        action: str,
    ) -> None:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
        if isinstance(exc, httpx.TimeoutException):
            log_event(
                logger,
                logging.WARNING,
                "upstream_timeout",
                url=url,
                elapsed_ms=elapsed_ms,
                timeout_s=self.total_timeout,
                action=action,
            )
            raise APIError(
                HTTPStatus.GATEWAY_TIMEOUT,
                f"{action}超时：上游接口超过 {self.total_timeout:.0f} 秒没有返回",
                "本地服务已经等满超时阈值。请降低图片尺寸/质量，或换用没有短网关限制的上游接口。",
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
            f"无法连接{action}: {exc}",
            code="upstream_error",
        ) from exc

    @staticmethod
    def _parse_json(text: str, context: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise APIError(
                HTTPStatus.BAD_GATEWAY,
                f"{context} 返回了无法解析的 JSON",
                text[:4000],
                code="upstream_error",
            ) from exc


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
            )
    return _default_client


async def shutdown_default_client() -> None:
    global _default_client
    async with _default_lock:
        if _default_client is not None:
            await _default_client.aclose()
            _default_client = None


# --- legacy sync wrappers used by tests --------------------------------

def run_upstream_json(
    url: str, api_key: str, payload: dict[str, Any], user_agent: str
) -> dict[str, Any]:
    return _run_sync(HttpxAsyncClient().run_json, url, api_key, payload, user_agent)


def run_upstream_multipart(
    url: str,
    api_key: str,
    fields: dict[str, Any],
    files: list[dict[str, Any]],
    user_agent: str,
) -> dict[str, Any]:
    return _run_sync(HttpxAsyncClient().run_multipart, url, api_key, fields, files, user_agent)


def run_upstream_file_upload(
    url: str,
    api_key: str,
    file_part: dict[str, Any],
    user_agent: str,
    *,
    purpose: str = "vision",
) -> dict[str, Any]:
    return _run_sync(
        HttpxAsyncClient().run_file_upload, url, api_key, file_part, user_agent, purpose
    )


def run_upstream_responses_json(
    url: str, api_key: str, payload: dict[str, Any], user_agent: str
) -> dict[str, Any]:
    return _run_sync(HttpxAsyncClient().run_responses, url, api_key, payload, user_agent)


def fetch_remote_image(url: str, user_agent: str) -> tuple[bytes, str]:
    return _run_sync(HttpxAsyncClient().fetch_image, url, user_agent)


def _run_sync(awaitable_fn: Any, *args: Any, **kwargs: Any) -> Any:
    async def _runner() -> Any:
        client = HttpxAsyncClient()
        try:
            return await awaitable_fn.__self__.__class__.__dict__[awaitable_fn.__name__](
                client, *args, **kwargs
            )
        finally:
            await client.aclose()

    return anyio.from_thread.run_sync(lambda: anyio.run(_runner)) if _in_async_context() else anyio.run(_runner)


def _in_async_context() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False

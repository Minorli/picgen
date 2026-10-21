from __future__ import annotations

from http import HTTPStatus

NO_IMAGE_ERROR_MESSAGES = {
    "no_image_output": "图片生成服务这次没有返回图片，具体原因尚未明确。请稍后手动重试。",
    "response_refusal": "上游返回了拒绝结果，但未提供明确错误代码。请检查描述后手动重试。",
    "image_tool_unfinished": "生图步骤未完成，未返回可用图片。请稍后手动重试。",
    "image_tool_failed": "上游生图步骤失败，未返回可用图片。请稍后手动重试。",
}
OUTPUT_IMAGE_POLICY_MESSAGE = "本次生成结果未通过上游安全检查，图片未交付。请调整画面要求后重试。"


class APIError(Exception):
    """Domain-level error mapped to an HTTP response.

    Attributes:
        status: HTTP status code returned to the client.
        message: Short human-readable summary for the UI.
        details: Optional structured/long-form context.
        code: Stable machine-readable error code for clients.
    """

    __slots__ = ("code", "details", "message", "status")

    def __init__(
        self,
        status: int | HTTPStatus,
        message: str,
        details: str | None = None,
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = int(status)
        self.message = message
        self.details = details
        self.code = code or _default_code(self.status)


def _default_code(status: int) -> str:
    if status == 400:
        return "bad_request"
    if status == 401:
        return "unauthorized"
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status == 413:
        return "payload_too_large"
    if status == 422:
        return "validation_error"
    if status == 429:
        return "rate_limited"
    if 500 <= status < 600:
        return "upstream_error" if status in {502, 503, 504} else "internal_error"
    return "error"

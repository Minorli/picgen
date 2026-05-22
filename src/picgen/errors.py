from __future__ import annotations

from http import HTTPStatus


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

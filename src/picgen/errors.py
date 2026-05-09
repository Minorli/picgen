from __future__ import annotations


class APIError(Exception):
    def __init__(self, status: int, message: str, details: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details

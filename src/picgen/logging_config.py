from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "apikey",
        "password",
        "secret",
        "token",
        "proxy_auth_token",
        "x-api-key",
    }
)

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(value: str) -> contextvars.Token[str]:
    return _request_id_var.set(value)


def reset_request_id(token: contextvars.Token[str]) -> None:
    _request_id_var.reset(token)


def _scrub_value(key: str, value: Any) -> Any:
    if key.lower() in _SENSITIVE_KEYS and isinstance(value, str) and value:
        if len(value) <= 8:
            return "***"
        return f"{value[:4]}…{value[-2:]}"
    return value


def _coerce(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple, set)):
        return [_coerce(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _coerce(_scrub_value(str(k), v)) for k, v in value.items()}
    return repr(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": _request_id_var.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for key, value in fields.items():
                payload[key] = _coerce(_scrub_value(key, value))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).isoformat(timespec="seconds")
        prefix = f"{ts} {record.levelname:<5} [{_request_id_var.get()}] {record.name}"
        message = record.getMessage()
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict) and fields:
            field_text = " ".join(
                f"{key}={_coerce(_scrub_value(key, value))}"
                for key, value in fields.items()
                if value is not None
            )
            if field_text:
                message = f"{message} {field_text}"
        line = f"{prefix} {message}"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


_configured = False


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    global _configured
    handler = logging.StreamHandler(stream=sys.stderr)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(ConsoleFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    if not _configured:
        configure_logging()
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, event: str, /, **fields: Any) -> None:
    """Emit an event-style log line with structured fields."""

    logger.log(level, event, extra={"fields": fields})

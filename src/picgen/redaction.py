from __future__ import annotations

import re

_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{6,}\b")
_ORG_ID_RE = re.compile(r"\borg-[A-Za-z0-9][A-Za-z0-9_-]{6,}\b")
_TELEGRAM_BOT_URL_RE = re.compile(r"(?i)(https://api\.telegram\.org/bot)[^/\s\"'<>]+")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:api_key|apikey|key|token|access_token|authorization|auth|password|secret)=)"
    r"[^&\s\"'<>]+"
)
_FIELD_SECRET_RE = re.compile(
    r"(?i)([\"']?(?:api_key|apikey|authorization|token|access_token|password|secret)[\"']?"
    r"\s*[:=]\s*[\"']?)([^\"'\s,}\]]+)"
)


def redact_sensitive_text(value: str | None, *, limit: int | None = None) -> str:
    """Mask secrets in text that may be shown to users, logs, or chat alerts."""

    if not value:
        return ""
    text = str(value)
    text = _TELEGRAM_BOT_URL_RE.sub(r"\1***", text)
    text = _QUERY_SECRET_RE.sub(r"\1***", text)
    text = _BEARER_RE.sub("Bearer ***", text)
    text = _OPENAI_KEY_RE.sub("sk-***", text)
    text = _ORG_ID_RE.sub("org-***", text)
    text = _FIELD_SECRET_RE.sub(r"\1***", text)
    if limit is not None and len(text) > limit:
        return f"{text[: max(0, limit - 3)]}..."
    return text

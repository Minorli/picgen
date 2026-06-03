from __future__ import annotations

import json
import logging

from picgen.logging_config import JsonFormatter, _redact_url_secrets


def test_redact_url_secrets_masks_sensitive_query_params() -> None:
    url = "https://host.test/v1/images?api_key=sk-secret-value&size=1024"
    redacted = _redact_url_secrets(url)
    assert "sk-secret-value" not in redacted
    assert "***" in redacted
    assert "size=1024" in redacted


def test_redact_url_secrets_leaves_plain_urls_untouched() -> None:
    url = "https://host.test/v1/images/generations"
    assert _redact_url_secrets(url) == url


def test_json_formatter_scrubs_secret_fields_and_urls() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="picgen.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="upstream_json_start",
        args=(),
        exc_info=None,
    )
    record.fields = {  # type: ignore[attr-defined]
        "url": "https://host.test/v1/images?token=abcdef123456",
        "api_key": "sk-1234567890",
    }
    payload = json.loads(formatter.format(record))
    assert "abcdef123456" not in payload["url"]
    assert payload["api_key"] != "sk-1234567890"

"""Upstream OpenAI-compatible API client utilities."""

from __future__ import annotations

from .client import (
    HttpxAsyncClient,
    UpstreamClient,
    get_default_client,
    shutdown_default_client,
)
from .errors import compact_log_text, extract_error_message
from .payload import (
    compact_raw_response,
    decode_base64_blob,
    ensure_json_object,
    extract_response_image_item,
    normalize_responses_image_payload,
    openai_image_options,
    optional_int,
    optional_string,
    prepare_image_payload,
    request_metadata,
    sibling_endpoint_url,
    validate_url,
)
from .responses import (
    event_image_base64,
    parse_sse_json_events,
    stream_events_to_image_payload,
)
from .transport import (
    ascii_multipart_filename,
    encode_multipart,
    upstream_headers,
)

__all__ = [
    "HttpxAsyncClient",
    "UpstreamClient",
    "ascii_multipart_filename",
    "compact_log_text",
    "compact_raw_response",
    "decode_base64_blob",
    "encode_multipart",
    "ensure_json_object",
    "event_image_base64",
    "extract_error_message",
    "extract_response_image_item",
    "get_default_client",
    "normalize_responses_image_payload",
    "openai_image_options",
    "optional_int",
    "optional_string",
    "parse_sse_json_events",
    "prepare_image_payload",
    "request_metadata",
    "shutdown_default_client",
    "sibling_endpoint_url",
    "stream_events_to_image_payload",
    "upstream_headers",
    "validate_url",
]

## ADDED Requirements

### Requirement: Streamed Body Limit Enforcement

The service SHALL reject oversized write requests even when the client omits or understates `Content-Length`.

#### Scenario: Chunked request exceeds configured limit

- **GIVEN** `max_request_body_bytes` is configured
- **WHEN** an API request body exceeds that limit while being read from the ASGI receive stream
- **THEN** PicGen SHALL stop processing the request
- **AND** SHALL return HTTP 413 with code `payload_too_large`.

### Requirement: Compact Raw Upstream Preview

The service SHALL not return full upstream base64 image payloads inside `raw_response`.

#### Scenario: Upstream returns image base64

- **GIVEN** the upstream response contains `b64_json`, `result`, `partial_image_b64`, `image_b64`, `image_url`, or `url` image fields
- **WHEN** PicGen builds the browser response
- **THEN** those fields in `raw_response` SHALL be replaced with compact placeholders
- **AND** first-image compatibility fields and persisted output images SHALL continue to work.

### Requirement: Unknown Image Type Safety

The service SHALL not label unknown image bytes as PNG.

#### Scenario: Image bytes have no recognized signature

- **GIVEN** image bytes are not PNG, JPEG, GIF, or WebP
- **WHEN** PicGen detects the MIME type or chooses a storage extension
- **THEN** PicGen SHALL use `application/octet-stream` and `.bin`
- **AND** SHALL emit a warning log for unknown MIME values.

### Requirement: Browser Key Storage Disclosure

The UI SHALL disclose that browser-saved API keys are stored locally and not shown back to the user.

#### Scenario: User views connection settings

- **GIVEN** the connection settings are visible
- **WHEN** API key configuration is displayed
- **THEN** the helper text SHALL state that browser-saved keys remain in local browser storage only
- **AND** SHALL state that the input is write-only and existing keys are not displayed.

### Requirement: Content Security Policy

The service SHALL send a conservative Content Security Policy header.

#### Scenario: Browser loads the application

- **WHEN** PicGen returns HTML or static assets
- **THEN** the response SHALL include a Content-Security-Policy header that limits script, style, image, connect, frame, object, and base URI sources to those required by the local app.

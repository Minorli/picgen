# Proposal: Review Hardening Follow-up

## Summary

Address the remaining actionable items from the external review after the 0.9.2 architecture merge. Most P0/P1 findings are already covered by 0.9.2; this change tightens the still-valid edge cases around request body streaming limits, raw upstream response size, unknown image MIME handling, browser key messaging, and security headers.

## Problem

The review report was written against the pre-0.9.2 tree. After syncing to the merged 0.9.2 main branch, the following major findings are already resolved:

- `src/picgen/upstream.py` is split into an upstream package.
- `image[]` was replaced by `image`.
- upstream timeout is configurable and defaults to 1200 seconds.
- `scripts/check.sh` runs `mypy src`.
- routing is async and uses `httpx.AsyncClient`.
- body size limits, rate limiting, security headers, request IDs, optional proxy auth, atomic storage, readiness checks, Docker assets, OpenAPI docs, and expanded tests are present.

The remaining gaps are smaller but still worth fixing before the next release.

## Goals

- Enforce request body size limits while streaming the ASGI request body, not only through `Content-Length`.
- Avoid returning full upstream `b64_json` payloads in `raw_response`.
- Treat unknown image bytes and MIME types as `application/octet-stream` / `.bin` instead of pretending they are PNG.
- Add CSP and explicit API key local-storage wording.
- Preserve current user-facing image workflows and API response compatibility.

## Non-Goals

- Do not redo the completed 0.9.2 async/httpx/middleware refactor.
- Do not split the frontend into modules in this patch.
- Do not change generated image quality or compress user images for generation/editing.

## Review Disposition

- P0 #1-#4: resolved in 0.9.2, except local untracked `__pycache__` cleanup is environmental and not source-controlled.
- P1 #5-#10: resolved in 0.9.2.
- P2 #11-#13, #17-#18, #22-#27: resolved or substantially addressed in 0.9.2.
- P2 #14-#16 and frontend #20-#21: addressed by this change.

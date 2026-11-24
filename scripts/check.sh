#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

uv run ruff check .
uv run mypy src
if command -v node >/dev/null 2>&1; then
  node --check static/app.js
  node --check static/logo-placement.mjs
  node --check static/responses-settings.mjs
  node --check static/url-safety.mjs
  node --check static/simple-preview.mjs
  node --check static/admin-console.mjs
fi
uv run pytest

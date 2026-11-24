#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PICGEN_HOST="${PICGEN_HOST:-127.0.0.1}"
export PICGEN_PORT="${PICGEN_PORT:-8000}"

exec uv run picgen --host "$PICGEN_HOST" --port "$PICGEN_PORT"

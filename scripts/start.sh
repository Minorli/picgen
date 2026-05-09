#!/usr/bin/env bash
set -euo pipefail

export PICGEN_HOST="${PICGEN_HOST:-127.0.0.1}"
export PICGEN_PORT="${PICGEN_PORT:-8000}"

uv run picgen --host "$PICGEN_HOST" --port "$PICGEN_PORT"

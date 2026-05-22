#!/usr/bin/env bash
# Production server launcher.
set -euo pipefail

export PICGEN_HOST="${PICGEN_HOST:-0.0.0.0}"
export PICGEN_PORT="${PICGEN_PORT:-8000}"
export PICGEN_LOG_FORMAT="${PICGEN_LOG_FORMAT:-json}"
export PICGEN_LOG_LEVEL="${PICGEN_LOG_LEVEL:-INFO}"

WORKERS="${PICGEN_WORKERS:-2}"

exec uv run picgen \
  --host "$PICGEN_HOST" \
  --port "$PICGEN_PORT" \
  --workers "$WORKERS" \
  --log-level "$PICGEN_LOG_LEVEL" \
  --log-format "$PICGEN_LOG_FORMAT"

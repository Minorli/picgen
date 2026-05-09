#!/usr/bin/env bash
set -euo pipefail

export PICGEN_HOST="${PICGEN_HOST:-127.0.0.1}"
export PICGEN_PORT="${PICGEN_PORT:-8000}"

uv run uvicorn picgen.main:app --reload --host "$PICGEN_HOST" --port "$PICGEN_PORT"

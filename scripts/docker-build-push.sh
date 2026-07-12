#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-minorli/picgen}"
VERSION="${VERSION:-0.1.62}"
PLATFORM="${PLATFORM:-linux/amd64}"

docker buildx build \
  --platform "${PLATFORM}" \
  --tag "${IMAGE}:${VERSION}" \
  --push \
  "$@" \
  .

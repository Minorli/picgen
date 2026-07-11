FROM ghcr.io/astral-sh/uv:0.11.28 AS uv

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install the exact locked runtime dependency graph first for layer caching.
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable \
    && python -m compileall -q /app/src

COPY static ./static
COPY scripts ./scripts
RUN chmod +x scripts/*.sh

# Drop privileges
RUN groupadd --gid 10001 picgen \
    && useradd --uid 10001 --gid picgen --home /app --shell /usr/sbin/nologin picgen \
    && mkdir -p /app/data \
    && chown -R picgen:picgen /app
USER picgen

ENV PICGEN_HOST=0.0.0.0 \
    PICGEN_PORT=8000 \
    PICGEN_LOG_FORMAT=json \
    PICGEN_ROOT_DIR=/app \
    PICGEN_STATIC_DIR=/app/static \
    PICGEN_DATA_DIR=/app/data \
    PICGEN_ENV_FILE=/app/data/.env \
    PICGEN_DEFAULT_GENERATE_URL=https://sub.tidba.com/v1/images/generations \
    PICGEN_DEFAULT_EDIT_URL=https://sub.tidba.com/v1/images/edits \
    PICGEN_DEFAULT_RESPONSES_URL=https://sub.tidba.com/v1/responses

VOLUME ["/app/data"]

EXPOSE 8000

# Probe the configured port, not a hardcoded 8000 — overriding PICGEN_PORT
# used to leave a working container permanently "unhealthy".
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PICGEN_PORT', '8000'), timeout=3).read()" || exit 1

ENTRYPOINT ["python", "-m", "picgen.cli"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-format", "json"]

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install only the runtime dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install "fastapi>=0.115.0" "uvicorn[standard]>=0.30.0" "httpx>=0.27.0" \
                   "pydantic>=2.7.0" "pydantic-settings>=2.4.0" "anyio>=4.4.0" \
    && pip install --no-deps . \
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

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()" || exit 1

ENTRYPOINT ["python", "-m", "picgen.cli"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-format", "json"]

# LEADFORGE API. Build from the repository root:
#   docker build -f services/api/Dockerfile -t leadforge-api .
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first for better layer caching.
COPY packages/core /app/packages/core
COPY services/api /app/services/api
RUN pip install /app/packages/core /app/services/api

# Migrations ship with the API image so a one-off container can run them.
COPY database /app/database

RUN useradd --create-home --uid 10001 leadforge
USER leadforge

ENV ENVIRONMENT=production LOG_JSON=true PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=4)"

CMD ["python", "-m", "leadforge_api"]

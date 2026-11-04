# LEADFORGE background worker. Build from the repository root:
#   docker build -f services/worker/Dockerfile -t leadforge-worker .
# Phase 2 will add Playwright + Chromium for website audits (see docs/ARCHITECTURE.md).
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY packages/core /app/packages/core
COPY services/worker /app/services/worker
RUN pip install /app/packages/core /app/services/worker

RUN useradd --create-home --uid 10001 leadforge
USER leadforge

ENV ENVIRONMENT=production LOG_JSON=true
# The worker handles SIGTERM by finishing its current job before exiting;
# give it time to do so (match LEASE_SECONDS for long jobs).
STOPSIGNAL SIGTERM

CMD ["python", "-m", "leadforge_worker"]

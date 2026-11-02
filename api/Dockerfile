# syntax=docker/dockerfile:1
# Multi-stage image for assess-api (FastAPI). Built ONLY on GitHub runners (no Docker on dev machines).

FROM python:3.12-slim-bookworm AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:3.12-slim-bookworm AS runtime
ARG GIT_SHA=local
LABEL org.opencontainers.image.revision=$GIT_SHA \
      org.opencontainers.image.title="assess-api" \
      org.opencontainers.image.source="https://github.com/Siddharajparkar/We_Select-"

# Microsoft ODBC Driver 18 for SQL Server (required by pyodbc) + unixODBC runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates unixodbc \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production PORT=8080 GIT_SHA=$GIT_SHA

RUN useradd --system --uid 10001 --no-create-home appuser
WORKDIR /srv
# app/ includes migrations/sql/*.sql (the SQL files must be in the image)
COPY app ./app
USER appuser
EXPOSE 8080
# Migrations run in the app lifespan BEFORE the server accepts traffic; a bad DATABASE_URL exits non-zero.
# Shutdown budget: 8 s for open requests + up to 20 s for running background jobs (JOB_SHUTDOWN_GRACE_SECONDS) < 30 s
# Container Apps termination grace period.
CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 8"]

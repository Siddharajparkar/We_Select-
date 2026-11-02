"""Application factory and entrypoint.

Run:  ``uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080``
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import ConfigError, Settings, load_settings
from .core.clock import Clock, SystemClock
from .core.errors import AppError
from .core.logging import logger
from .jobs.engine import JobEngine
from .jobs.handlers import default_handlers
from .middleware import RequestContextMiddleware
from .providers import Providers, create_providers
from .repositories import Repositories, create_repositories
from .routes import assessments, generation, health, platform, users
from .routes import auth as auth_routes
from .security.passwords import PasswordService
from .services.auth import AuthService
from .services.rate_limit import SlidingWindowLimiter
from .telemetry import configure_telemetry

API_PREFIX = "/api/v1"


def _envelope(err: AppError) -> JSONResponse:
    headers = {"Retry-After": str(err.retry_after)} if err.retry_after else None
    return JSONResponse(err.to_dict(), status_code=err.status, headers=headers)


def create_app(
    settings: Settings | None = None,
    *,
    repos: Repositories | None = None,
    providers: Providers | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Build the FastAPI app. Dependencies can be injected (tests); otherwise built from settings."""
    if settings is None:
        try:
            settings = load_settings()
        except ConfigError as exc:
            # Names/rules only - never values.
            logger.error("invalid configuration", problems=str(exc))
            raise SystemExit(1) from None

    # Telemetry must be configured BEFORE the FastAPI instance exists so requests are auto-instrumented.
    # (No-op when APPLICATIONINSIGHTS_CONNECTION_STRING is empty; never raises.)
    configure_telemetry(settings)

    clock = clock or SystemClock()
    owns_repos = repos is None
    repos = repos or create_repositories(
        settings.REPO_BACKEND, database_url=settings.DATABASE_URL, schema=settings.DB_SCHEMA, clock=clock
    )
    providers = providers or create_providers(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.REPO_BACKEND == "sql" and owns_repos:
            from .migrations.runner import run_migrations

            # Fail fast: an exception here makes uvicorn exit non-zero before it accepts traffic.
            await asyncio.to_thread(run_migrations, repos.db.engine, settings.DB_SCHEMA)
            logger.info("config ok", repo_backend=settings.REPO_BACKEND, ai=settings.AI_MODE,
                        email=settings.EMAIL_MODE, files=settings.FILES_MODE, version=settings.GIT_SHA)  # fmt: skip
        ensure = getattr(providers.files, "ensure_container", None)
        if callable(ensure) and settings.FILES_MODE == "azurite":
            await asyncio.to_thread(ensure)
        engine: JobEngine = app.state.jobs
        if settings.JOB_LOOP_ENABLED:
            await asyncio.to_thread(engine.recover_stuck)
            engine.start()
        yield
        await engine.stop()
        repos.db.dispose()
        logger.info("shutdown complete")

    app = FastAPI(
        title="AI Candidate Assessment Platform API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/api/v1/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/v1/openapi.json",
    )
    app.state.settings = settings
    app.state.repos = repos
    app.state.providers = providers
    app.state.clock = clock
    app.state.passwords = PasswordService(
        settings.ARGON2_MEMORY_KIB, settings.ARGON2_TIME_COST, settings.ARGON2_PARALLELISM
    )
    app.state.auth = AuthService(repos, clock, app.state.passwords, settings.SESSION_SECRET)
    app.state.platform_limiter = SlidingWindowLimiter(clock, limit=10, window_seconds=60)  # per IP (4.6)

    app.state.jobs = JobEngine(repos, providers, settings, clock, default_handlers())

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _envelope(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details: list[Any] = [
            {"path": ".".join(str(p) for p in e.get("loc", ()) if p != "body"), "message": e.get("msg", "invalid")}
            for e in exc.errors()
        ]
        return _envelope(AppError.bad_request("Request validation failed", details))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _envelope(AppError(404, "NOT_FOUND", "Route not found"))
        if exc.status_code == 405:
            return _envelope(AppError(405, "METHOD_NOT_ALLOWED", "Method not allowed"))
        return _envelope(AppError(exc.status_code, "HTTP_ERROR", str(exc.detail)))

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth_routes.router, prefix=API_PREFIX)
    app.include_router(platform.router, prefix=API_PREFIX)
    app.include_router(users.router, prefix=API_PREFIX)
    app.include_router(assessments.router, prefix=API_PREFIX)
    app.include_router(generation.router, prefix=API_PREFIX)

    # Outermost: request id, security headers, body limit, access log, last-resort 500 boundary.
    app.add_middleware(RequestContextMiddleware, app_version=settings.GIT_SHA)
    return app


def run() -> None:  # pragma: no cover - convenience for `python -m app.main`
    import uvicorn

    s = load_settings()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - container listens on all interfaces; ingress is Container Apps
        port=s.PORT,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":  # pragma: no cover
    run()

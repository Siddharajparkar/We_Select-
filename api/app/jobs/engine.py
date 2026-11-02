"""Background job engine (Prompt A 7): DB-backed queue, polled every few seconds, in-process.

* ``tick`` claims up to ``max_concurrent`` jobs (never more than that run at once) and runs each in a worker thread.
* Failures are retried up to ``max_attempts`` with ``run_after = now + base * attempts``; permanent errors
  (``NonRetryableJobError``) fail at once with a readable message.
* Jobs left ``running`` by a dead worker are re-queued (or failed) after ``stuck_seconds``, at start and every minute.
* Logs carry ids, types, durations and counts only - never prompts, job descriptions or answers.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import uuid4

from ..config import Settings
from ..core.clock import Clock
from ..core.logging import logger
from ..providers import Providers
from ..repositories import Repositories
from ..repositories.models import Job

SWEEP_EVERY_SECONDS = 60


class JobError(Exception):
    """A handler failure with a message a person can read. ``retryable`` decides whether to try again."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "JOB_FAILED",
        retryable: bool = True,
        retry_after: float | None = None,
        tokens_used: int = 0,
    ) -> None:
        super().__init__(message)
        self.message, self.code, self.retryable = message, code, retryable
        self.retry_after, self.tokens_used = retry_after, tokens_used


class NonRetryableJobError(JobError):
    def __init__(self, message: str, *, code: str = "JOB_FAILED", tokens_used: int = 0) -> None:
        super().__init__(message, code=code, retryable=False, tokens_used=tokens_used)


@dataclass
class JobContext:
    job: Job
    repos: Repositories
    providers: Providers
    settings: Settings
    clock: Clock


@dataclass
class JobOutcome:
    result: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0


Handler = Callable[[JobContext], JobOutcome]


class JobEngine:
    def __init__(
        self,
        repos: Repositories,
        providers: Providers,
        settings: Settings,
        clock: Clock,
        handlers: dict[str, Handler],
        *,
        worker_id: str | None = None,
    ) -> None:
        self.repos, self.providers, self.settings, self.clock = repos, providers, settings, clock
        self.handlers = handlers
        self.worker_id = worker_id or f"worker-{uuid4().hex[:8]}"
        self.max_concurrent = settings.JOB_MAX_CONCURRENT
        self._inflight: set[asyncio.Task[None]] = set()
        self._loop_task: asyncio.Task[None] | None = None
        self._wake: asyncio.Event | None = None
        self._stopping = False
        self._last_sweep = 0.0
        self._ticking = False
        self.peak_concurrency = 0  # observed maximum, for tests and diagnostics

    # ── one job ─────────────────────────────────────────────────────────────────────────
    def execute(self, job: Job) -> str:
        """Run one claimed job to completion; never raises. Returns the resulting status."""
        started = time.perf_counter()
        base: dict[str, Any] = {
            "job_id": job.id,
            "job_type": job.type,
            "tenant_id": job.tenant_id,
            "attempt": job.attempts,
        }
        logger.info("job_started", **base)
        handler = self.handlers.get(job.type)
        try:
            if handler is None:
                raise NonRetryableJobError(f"No handler is registered for '{job.type}' jobs", code="NO_HANDLER")
            outcome = handler(JobContext(job, self.repos, self.providers, self.settings, self.clock))
            self.repos.jobs.complete(job.id, outcome.result, outcome.tokens_used)
            logger.info("job_done", **base, tokens=outcome.tokens_used, durationMs=_ms(started))
            return "done"
        except JobError as exc:
            delay = (
                exc.retry_after if exc.retry_after is not None else self.settings.JOB_RETRY_BASE_SECONDS * job.attempts
            )
            status = self.repos.jobs.fail(
                job.id, exc.message, retryable=exc.retryable, delay_seconds=delay, code=exc.code,
                tokens_used=exc.tokens_used,
            )  # fmt: skip
        except Exception as exc:
            logger.error("job_crashed", **base, error_type=type(exc).__name__)
            status = self.repos.jobs.fail(
                job.id,
                "Something went wrong while processing this job.",
                retryable=True,
                delay_seconds=self.settings.JOB_RETRY_BASE_SECONDS * job.attempts,
                code="INTERNAL",
            )
        logger.info("job_retry" if status == "queued" else "job_failed", **base, durationMs=_ms(started))
        return status

    # ── maintenance ─────────────────────────────────────────────────────────────────────
    def recover_stuck(self) -> int:
        cutoff = self.clock.now() - timedelta(seconds=self.settings.JOB_STUCK_SECONDS)
        fixed = self.repos.jobs.requeue_stuck(cutoff)
        for jid, status in fixed:
            logger.warn("job_recovered", job_id=jid, new_status=status)
        return len(fixed)

    # ── synchronous driver (tests, scripts) ─────────────────────────────────────────────
    def drain(self, limit: int = 1000) -> int:
        """Claim and run jobs one after another until none is due. Returns how many ran."""
        n = 0
        while n < limit:
            job = self.repos.jobs.claim_next(self.worker_id)
            if job is None:
                break
            self.execute(job)
            n += 1
        return n

    # ── async loop ──────────────────────────────────────────────────────────────────────
    async def tick(self) -> int:
        """One scheduling pass. Not re-entrant: an overlapping call returns 0. Returns jobs started."""
        if self._ticking:
            return 0
        self._ticking = True
        started = 0
        try:
            now = time.monotonic()
            if now - self._last_sweep >= SWEEP_EVERY_SECONDS or self._last_sweep == 0.0:
                self._last_sweep = now
                await asyncio.to_thread(self.recover_stuck)
            while not self._stopping and len(self._inflight) < self.max_concurrent:
                job = await asyncio.to_thread(self.repos.jobs.claim_next, self.worker_id)
                if job is None:
                    break
                task = asyncio.create_task(self._run(job))
                self._inflight.add(task)
                task.add_done_callback(self._inflight.discard)
                self.peak_concurrency = max(self.peak_concurrency, len(self._inflight))
                started += 1
        except Exception as exc:
            logger.error("job_tick_failed", error_type=type(exc).__name__)
        finally:
            self._ticking = False
        return started

    async def _run(self, job: Job) -> None:
        await asyncio.to_thread(self.execute, job)

    async def wait_idle(self, timeout: float | None = None) -> None:
        pending = list(self._inflight)
        if pending:
            await asyncio.wait(pending, timeout=timeout)

    async def _loop(self) -> None:
        wake = self._wake
        assert wake is not None
        while not self._stopping:
            await self.tick()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wake.wait(), self.settings.JOB_TICK_SECONDS)

    def start(self) -> None:
        if self._loop_task is None:
            self._stopping = False
            self._wake = asyncio.Event()
            self._loop_task = asyncio.create_task(self._loop())
            logger.info("job_loop_started", worker=self.worker_id, max_concurrent=self.max_concurrent)

    async def stop(self) -> None:
        """Graceful shutdown: stop claiming, let running jobs finish for up to the grace period."""
        self._stopping = True
        if self._loop_task is not None and self._wake is not None:
            # Let the current tick finish (it may be inside a database call on a worker thread):
            # cancelling it would leave that thread running while the connection pool is disposed.
            self._wake.set()
            done, _ = await asyncio.wait({self._loop_task}, timeout=self.settings.JOB_SHUTDOWN_GRACE_SECONDS)
            if not done:
                self._loop_task.cancel()
            self._loop_task = None
        await self.wait_idle(self.settings.JOB_SHUTDOWN_GRACE_SECONDS)
        left = len(self._inflight)
        logger.info("job_loop_stopped", unfinished=left)


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)

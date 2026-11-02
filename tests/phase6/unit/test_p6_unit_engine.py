"""Phase 6 unit: the job engine (claim, retry back-off, stuck recovery, concurrency, shutdown)."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import timedelta

import pytest

from app.config import load_settings
from app.core.clock import FakeClock
from app.jobs.engine import JobContext, JobEngine, JobError, JobOutcome, NonRetryableJobError
from app.providers import create_providers
from app.repositories import Repositories


@pytest.fixture
def cfg():  # type: ignore[no-untyped-def]
    return load_settings(JOB_TICK_SECONDS=0.01, JOB_SHUTDOWN_GRACE_SECONDS=2, JOB_LOOP_ENABLED=False)


@pytest.fixture
def tenant(repos: Repositories):  # type: ignore[no-untyped-def]
    return repos.tenants.create(name="T")


def make_engine(repos, cfg, clock, handler, worker="w1"):  # type: ignore[no-untyped-def]
    return JobEngine(repos, create_providers(cfg), cfg, clock, {"generate": handler}, worker_id=worker)


def enqueue(repos, tenant, n=1, **kw):  # type: ignore[no-untyped-def]
    ref = "11111111-1111-4111-8111-111111111111"
    return [repos.jobs.enqueue(tenant.id, type="generate", ref_id=ref, payload={"n": i}, **kw) for i in range(n)]


def get(repos, tenant, job):  # type: ignore[no-untyped-def]
    return repos.jobs.find_by_id(tenant.id, job.id)


def ok(ctx: JobContext) -> JobOutcome:
    return JobOutcome({"seen": ctx.job.payload["n"]}, tokens_used=7)


def test_success_marks_done_with_result_and_tokens(repos, cfg, clock, tenant) -> None:  # type: ignore[no-untyped-def]
    (j,) = enqueue(repos, tenant)
    assert make_engine(repos, cfg, clock, ok).drain() == 1
    d = get(repos, tenant, j)
    assert d.status == "done" and d.result == {"seen": 0} and d.tokens_used == 7 and d.attempts == 1
    assert d.started_at == clock.now() and d.locked_by is None and d.error is None


def test_unknown_job_type_fails_at_once_with_readable_message(repos, cfg, clock, tenant) -> None:  # type: ignore[no-untyped-def]
    j = repos.jobs.enqueue(tenant.id, type="mark", ref_id="11111111-1111-4111-8111-111111111111", payload={})
    make_engine(repos, cfg, clock, ok).drain()
    d = get(repos, tenant, j)
    assert d.status == "failed" and "No handler" in (d.error or "") and d.result == {"code": "NO_HANDLER"}


def test_retry_backoff_is_5_seconds_times_attempt_then_fails_after_three(repos, cfg, clock, tenant) -> None:  # type: ignore[no-untyped-def]
    def flaky(ctx: JobContext) -> JobOutcome:
        raise JobError("The AI service took too long to answer.", code="AI_TIMEOUT")

    (j,) = enqueue(repos, tenant)
    eng = make_engine(repos, cfg, clock, flaky)
    eng.drain()
    d = get(repos, tenant, j)
    assert d.status == "queued" and d.attempts == 1 and d.run_after == clock.now() + timedelta(seconds=5)
    assert d.error == "The AI service took too long to answer."
    assert eng.drain() == 0  # not due yet
    clock.advance(seconds=4.9)
    assert eng.drain() == 0
    clock.advance(seconds=0.2)
    eng.drain()
    d = get(repos, tenant, j)
    assert d.status == "queued" and d.attempts == 2 and d.run_after == clock.now() + timedelta(seconds=10)
    clock.advance(seconds=10)
    eng.drain()
    d = get(repos, tenant, j)
    assert d.status == "failed" and d.attempts == 3 and d.result == {"code": "AI_TIMEOUT"}
    assert eng.drain() == 0


def test_retry_after_from_provider_overrides_backoff(repos, cfg, clock, tenant) -> None:  # type: ignore[no-untyped-def]
    def busy(ctx: JobContext) -> JobOutcome:
        raise JobError("busy", retry_after=42)

    (j,) = enqueue(repos, tenant)
    make_engine(repos, cfg, clock, busy).drain()
    assert get(repos, tenant, j).run_after == clock.now() + timedelta(seconds=42)


def test_non_retryable_error_fails_immediately_and_keeps_tokens(repos, cfg, clock, tenant) -> None:  # type: ignore[no-untyped-def]
    def bad(ctx: JobContext) -> JobOutcome:
        raise NonRetryableJobError("nope", code="AI_OUTPUT_INVALID", tokens_used=33)

    (j,) = enqueue(repos, tenant)
    make_engine(repos, cfg, clock, bad).drain()
    d = get(repos, tenant, j)
    assert (
        d.status == "failed" and d.attempts == 1 and d.tokens_used == 33 and d.result == {"code": "AI_OUTPUT_INVALID"}
    )


def test_unexpected_exception_is_retried_with_a_generic_message_and_no_details(
    repos, cfg, clock, tenant, capsys
) -> None:  # type: ignore[no-untyped-def]
    def crash(ctx: JobContext) -> JobOutcome:
        raise RuntimeError("SECRET-DETAIL password=hunter2")

    (j,) = enqueue(repos, tenant)
    make_engine(repos, cfg, clock, crash).drain()
    d = get(repos, tenant, j)
    assert d.status == "queued" and d.error == "Something went wrong while processing this job."
    out = capsys.readouterr()
    assert "hunter2" not in out.out + out.err and "SECRET-DETAIL" not in out.out + out.err


def test_jobs_run_oldest_first_and_across_tenants(repos, cfg, clock) -> None:  # type: ignore[no-untyped-def]
    a, b = repos.tenants.create(name="A"), repos.tenants.create(name="B")
    order: list[str] = []

    def rec(ctx: JobContext) -> JobOutcome:
        order.append(ctx.job.tenant_id)
        return JobOutcome()

    ref = "11111111-1111-4111-8111-111111111111"
    repos.jobs.enqueue(a.id, type="generate", ref_id=ref, payload={})
    clock.advance(seconds=1)
    repos.jobs.enqueue(b.id, type="generate", ref_id=ref, payload={})
    make_engine(repos, cfg, clock, rec).drain()
    assert order == [a.id, b.id]


def test_stuck_running_jobs_are_requeued_after_five_minutes_or_failed_when_out_of_attempts(
    repos, cfg, clock, tenant
) -> None:  # type: ignore[no-untyped-def]
    (fresh, spent) = enqueue(repos, tenant, 2)
    for _ in range(2):  # claim both -> running
        repos.jobs.claim_next("dead-worker")
    repos.jobs.fail(spent.id, "x", retryable=True)  # attempts=1 -> back to queued...
    repos.jobs.claim_next("dead-worker")  # ...running again (attempts=2)
    repos.jobs.fail(spent.id, "x")
    repos.jobs.claim_next("dead-worker")  # attempts=3 == max, running
    eng = make_engine(repos, cfg, clock, ok)
    clock.advance(seconds=299)
    assert eng.recover_stuck() == 0
    clock.advance(seconds=2)
    assert eng.recover_stuck() == 2
    assert get(repos, tenant, fresh).status == "queued" and get(repos, tenant, spent).status == "failed"
    assert "worker restarted" in (get(repos, tenant, spent).error or "")
    assert eng.drain() == 1  # the re-queued one runs now


def test_two_engines_never_run_the_same_job_twice(repos, cfg, clock, tenant) -> None:  # type: ignore[no-untyped-def]
    enqueue(repos, tenant, 50)
    ran: list[int] = []
    lock = threading.Lock()

    def rec(ctx: JobContext) -> JobOutcome:
        with lock:
            ran.append(ctx.job.payload["n"])
        return JobOutcome()

    engines = [make_engine(repos, cfg, clock, rec, worker=f"w{i}") for i in range(2)]
    threads = [threading.Thread(target=e.drain) for e in engines]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(ran) == list(range(50))


def test_never_more_than_three_jobs_at_once_and_ticks_do_not_overlap(repos, cfg, clock, tenant) -> None:  # type: ignore[no-untyped-def]
    js = enqueue(repos, tenant, 8)
    active = {"now": 0, "peak": 0}
    lock = threading.Lock()

    def slow(ctx: JobContext) -> JobOutcome:
        with lock:
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
        time.sleep(0.15)
        with lock:
            active["now"] -= 1
        return JobOutcome()

    eng = make_engine(repos, cfg, clock, slow)

    async def go() -> None:
        assert await eng.tick() == 3  # the three slots were filled, five jobs stay queued
        assert await eng.tick() == 0  # every slot busy: nothing more is claimed
        for _ in range(300):
            await eng.wait_idle()
            if await eng.tick() == 0 and not eng._inflight:
                break

    asyncio.run(go())
    assert active["peak"] <= 3 and eng.peak_concurrency == 3
    assert [get(repos, tenant, j).status for j in js] == ["done"] * 8


def test_overlapping_tick_is_a_noop(repos, cfg, clock, tenant) -> None:  # type: ignore[no-untyped-def]
    eng = make_engine(repos, cfg, clock, ok)
    eng._ticking = True
    assert asyncio.run(eng.tick()) == 0


def test_graceful_stop_lets_running_jobs_finish_and_stops_claiming(repos, cfg, clock, tenant) -> None:  # type: ignore[no-untyped-def]
    js = enqueue(repos, tenant, 2)
    started = threading.Event()

    def slow(ctx: JobContext) -> JobOutcome:
        started.set()
        time.sleep(0.3)
        return JobOutcome()

    eng = make_engine(repos, cfg, clock, slow)

    async def go() -> None:
        eng.start()
        for _ in range(100):
            await asyncio.sleep(0.02)
            if started.is_set():
                break
        await eng.stop()

    asyncio.run(go())
    statuses = sorted(get(repos, tenant, j).status for j in js)
    assert "running" not in statuses  # anything claimed was allowed to finish
    assert eng._loop_task is None


def test_loop_processes_jobs_end_to_end(repos, cfg, clock, tenant) -> None:  # type: ignore[no-untyped-def]
    js = enqueue(repos, tenant, 4)
    eng = make_engine(repos, cfg, clock, ok)

    async def go() -> None:
        eng.start()
        for _ in range(200):
            await asyncio.sleep(0.02)
            if all(get(repos, tenant, j).status == "done" for j in js):
                break
        await eng.stop()

    asyncio.run(go())
    assert [get(repos, tenant, j).status for j in js] == ["done"] * 4


def test_sleeping_clock_helper_is_fake(clock: FakeClock) -> None:
    before = clock.now()
    clock.advance(seconds=3)
    assert clock.now() - before == timedelta(seconds=3)


def test_memory_database_dispose_waits_for_a_running_statement(mem_repos: Repositories) -> None:
    """Regression: closing the shared SQLite connection under a running statement crashed the interpreter."""
    db = mem_repos.db
    finished = threading.Event()
    with db.begin():  # a statement is "running" on this thread
        t = threading.Thread(target=lambda: (db.dispose(), finished.set()))
        t.start()
        assert not finished.wait(0.2)  # dispose is blocked while we hold the connection
    assert finished.wait(2)
    t.join()

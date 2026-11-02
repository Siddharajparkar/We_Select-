"""Phase 6 integration: the real background loop started by the application lifespan."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from app.config import load_settings
from app.core.clock import SystemClock
from app.main import create_app
from app.providers import create_providers
from app.repositories import create_repositories
from conftest import API, PASSWORD

JD = " ".join(f"skill{i}" for i in range(120))


def test_lifespan_starts_the_loop_and_jobs_complete_without_manual_draining() -> None:
    s = load_settings(ARGON2_MEMORY_KIB=1024, ARGON2_TIME_COST=1, JOB_TICK_SECONDS=0.05, JOB_LOOP_ENABLED=True)
    clock = SystemClock()
    app = create_app(s, repos=create_repositories("memory", clock=clock), providers=create_providers(s), clock=clock)
    with TestClient(app, base_url="https://testserver") as c:
        r = c.post(
            f"{API}/platform/tenants", headers={"X-Platform-Key": s.PLATFORM_KEY},
            json={"name": "L", "adminName": "A", "adminEmail": "a@loop.example", "password": PASSWORD},
        )  # fmt: skip
        assert r.status_code == 201
        assert c.post(f"{API}/auth/login", json={"email": "a@loop.example", "password": PASSWORD}).status_code == 200
        aid = c.post(
            f"{API}/assessments",
            json={"title": "T", "jobDescription": JD, "durationMinutes": 30, "passingScore": 50,
                  "sections": [{"type": "mcq", "domain": "Go", "difficulty": "easy", "count": 6}]},
        ).json()["id"]  # fmt: skip
        jid = c.post(f"{API}/assessments/{aid}/generate", json={}).json()["jobId"]
        job: dict[str, Any] = {}
        deadline = time.time() + 10
        while time.time() < deadline:
            job = c.get(f"{API}/jobs/{jid}").json()
            if job["status"] in ("done", "failed"):
                break
            time.sleep(0.05)
        assert job["status"] == "done", job
        assert len(c.get(f"{API}/assessments/{aid}/questions").json()) == 6
    assert app.state.jobs._loop_task is None  # stopped cleanly on shutdown


def test_loop_disabled_leaves_jobs_queued() -> None:
    s = load_settings(ARGON2_MEMORY_KIB=1024, ARGON2_TIME_COST=1, JOB_LOOP_ENABLED=False)
    clock = SystemClock()
    app = create_app(s, repos=create_repositories("memory", clock=clock), providers=create_providers(s), clock=clock)
    with TestClient(app):
        assert app.state.jobs._loop_task is None

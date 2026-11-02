"""Phase 6 E2E: a real uvicorn process with the background job loop, fake AI, over real HTTP."""

from __future__ import annotations

import re
import time

import httpx
import pytest

pytestmark = pytest.mark.e2e
API = "/api/v1"
KEY = "dev-only-platform-key-change-me-00000"
PW = "correct-horse-9"
JD = " ".join(f"requirement{i}" for i in range(130))
SECTIONS = [
    {"type": "mcq", "domain": "Python", "difficulty": "easy", "count": 7},
    {"type": "cognitive", "domain": "Logic", "difficulty": "medium", "count": 2},
    {"type": "descriptive", "domain": "Design", "difficulty": "hard", "count": 1},
]


def tenant(base: str, tag: str) -> dict[str, str]:
    email = f"{tag}@p6.e2e.example"
    r = httpx.post(
        f"{base}{API}/platform/tenants", headers={"X-Platform-Key": KEY},
        json={"name": f"P6-{tag}", "adminName": "Admin", "adminEmail": email, "password": PW},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    lr = httpx.post(f"{base}{API}/auth/login", json={"email": email, "password": PW})
    return {"Cookie": f"sid={re.search(r'sid=([^;]+)', lr.headers['set-cookie']).group(1)}"}  # type: ignore[union-attr]


@pytest.fixture(scope="module")
def sessions(live_server: str) -> dict[str, dict[str, str]]:
    return {"a": tenant(live_server, "a"), "b": tenant(live_server, "b")}


def wait_job(base: str, h: dict[str, str], jid: str) -> dict:  # type: ignore[type-arg]
    deadline = time.time() + 20
    while time.time() < deadline:
        j = httpx.get(f"{base}{API}/jobs/{jid}", headers=h).json()
        if j["status"] in ("done", "failed"):
            return j  # type: ignore[no-any-return]
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_generate_review_approve_over_real_http(live_server: str, sessions: dict[str, dict[str, str]]) -> None:
    a = sessions["a"]
    aid = httpx.post(
        f"{live_server}{API}/assessments", headers=a,
        json={"title": "E2E", "jobDescription": JD, "durationMinutes": 30, "passingScore": 50, "sections": SECTIONS},
    ).json()["id"]  # fmt: skip
    r = httpx.post(f"{live_server}{API}/assessments/{aid}/generate", headers=a, json={})
    assert r.status_code == 202
    job = wait_job(live_server, a, r.json()["jobId"])
    assert job["status"] == "done" and job["result"]["questionsCreated"] == 10 and job["tokensUsed"] > 0
    qs = httpx.get(f"{live_server}{API}/assessments/{aid}/questions", headers=a).json()
    assert len(qs) == 10 and len({q["body"] for q in qs}) == 10  # 7 mcq came from two batches (5 + 2), no repeats
    ok = httpx.post(f"{live_server}{API}/assessments/{aid}/approve", headers=a)
    assert ok.status_code == 200 and ok.json()["questionCount"] == 10
    assert httpx.get(f"{live_server}{API}/assessments/{aid}", headers=a).json()["status"] == "approved"


def test_other_tenant_cannot_see_the_job_or_questions(live_server: str, sessions: dict[str, dict[str, str]]) -> None:
    a, b = sessions["a"], sessions["b"]
    aid = httpx.post(
        f"{live_server}{API}/assessments", headers=a,
        json={"title": "E2E2", "jobDescription": JD, "durationMinutes": 30, "passingScore": 50, "sections": SECTIONS[:1]},
    ).json()["id"]  # fmt: skip
    jid = httpx.post(f"{live_server}{API}/assessments/{aid}/generate", headers=a, json={}).json()["jobId"]
    assert httpx.get(f"{live_server}{API}/jobs/{jid}", headers=b).status_code == 404
    assert httpx.get(f"{live_server}{API}/assessments/{aid}/questions", headers=b).status_code == 404
    assert wait_job(live_server, a, jid)["status"] == "done"

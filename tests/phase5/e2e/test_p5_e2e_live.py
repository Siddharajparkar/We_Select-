"""Phase 5 E2E: real uvicorn process, multipart upload over real HTTP, memory blob store."""

from __future__ import annotations

import re

import httpx
import pytest

from helpers_pdf import JD_TEXT, make_pdf

pytestmark = pytest.mark.e2e
API = "/api/v1"
KEY = "dev-only-platform-key-change-me-00000"
PW = "correct-horse-9"
BODY = {
    "title": "E2E Assessment",
    "jobDescription": "Short text",
    "durationMinutes": 45,
    "passingScore": 50,
    "sections": [{"type": "mcq", "domain": "Python", "difficulty": "easy", "count": 3}],
}


def tenant(base: str, tag: str) -> dict[str, str]:
    email = f"{tag}@p5.e2e.example"
    r = httpx.post(
        f"{base}{API}/platform/tenants", headers={"X-Platform-Key": KEY},
        json={"name": f"P5-{tag}", "adminName": "Admin", "adminEmail": email, "password": PW},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    lr = httpx.post(f"{base}{API}/auth/login", json={"email": email, "password": PW})
    sid = re.search(r"sid=([^;]+)", lr.headers["set-cookie"]).group(1)  # type: ignore[union-attr]
    return {"Cookie": f"sid={sid}"}  # type: ignore[return-value]


@pytest.fixture(scope="module")
def sessions(live_server: str) -> dict[str, dict[str, str]]:
    return {"a": tenant(live_server, "a"), "b": tenant(live_server, "b")}


def test_full_lifecycle_over_real_http(live_server: str, sessions: dict[str, dict[str, str]]) -> None:
    a = sessions["a"]
    aid = httpx.post(f"{live_server}{API}/assessments", json=BODY, headers=a).json()["id"]
    assert [r["id"] for r in httpx.get(f"{live_server}{API}/assessments", headers=a).json()] == [aid]

    up = httpx.post(
        f"{live_server}{API}/assessments/{aid}/jd-file",
        headers=a,
        files={"file": ("spec.pdf", make_pdf(JD_TEXT), "application/pdf")},
    )
    assert up.status_code == 200 and "FastAPI" in up.json()["jobDescription"] and up.json()["wordCount"] > 30
    g = httpx.get(f"{live_server}{API}/assessments/{aid}", headers=a).json()
    assert g["jdFileName"] == "spec.pdf" and g["jobDescription"] == up.json()["jobDescription"]

    patched = httpx.patch(f"{live_server}{API}/assessments/{aid}", headers=a, json={"title": "Renamed"}).json()
    assert patched["title"] == "Renamed" and patched["warnings"] == []

    assert httpx.delete(f"{live_server}{API}/assessments/{aid}", headers=a).status_code == 204
    assert httpx.get(f"{live_server}{API}/assessments/{aid}", headers=a).status_code == 404


def test_cross_tenant_is_404_over_real_http(live_server: str, sessions: dict[str, dict[str, str]]) -> None:
    a, b = sessions["a"], sessions["b"]
    aid = httpx.post(f"{live_server}{API}/assessments", json=BODY, headers=a).json()["id"]
    for method, suffix in (("get", ""), ("delete", ""), ("post", "/close")):
        assert getattr(httpx, method)(f"{live_server}{API}/assessments/{aid}{suffix}", headers=b).status_code == 404
    r = httpx.post(
        f"{live_server}{API}/assessments/{aid}/jd-file", headers=b, files={"file": ("x.txt", JD_TEXT.encode())}
    )
    assert r.status_code == 404


def test_size_limits_over_real_http(live_server: str, sessions: dict[str, dict[str, str]]) -> None:
    a = sessions["a"]
    aid = httpx.post(f"{live_server}{API}/assessments", json=BODY, headers=a).json()["id"]
    url = f"{live_server}{API}/assessments/{aid}/jd-file"
    over = httpx.post(url, headers=a, files={"file": ("big.txt", b"a" * (2 * 1024 * 1024 + 1))})
    assert over.status_code == 400 and "2 MB" in over.json()["error"]["message"]
    huge = httpx.post(url, headers=a, files={"file": ("huge.txt", b"a" * (3 * 1024 * 1024))}, timeout=30)
    assert huge.status_code == 413
    assert (
        httpx.post(f"{live_server}{API}/assessments", headers=a, content=b"x" * 1_100_000).status_code == 413
    )  # still 1 MB elsewhere

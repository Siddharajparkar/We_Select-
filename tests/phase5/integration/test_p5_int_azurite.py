"""Phase 5 integration against Azurite (CI tier T2): the upload route really writes and removes blobs."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.providers import create_providers
from app.repositories import create_repositories
from conftest import API, PASSWORD
from helpers_pdf import JD_TEXT, make_pdf

pytestmark = pytest.mark.azurite


def test_upload_replace_and_delete_hit_real_blob_storage(clock) -> None:  # type: ignore[no-untyped-def]
    cs = os.environ.get("AZURITE_CONNECTION_STRING")
    if not cs:
        pytest.skip("AZURITE_CONNECTION_STRING not set")
    s = load_settings(
        FILES_MODE="azurite", BLOB_CONNECTION_STRING=cs, BLOB_CONTAINER="jd-files-p5",
        ARGON2_MEMORY_KIB=1024, ARGON2_TIME_COST=1,
    )  # fmt: skip
    providers = create_providers(s)
    providers.files.ensure_container()  # type: ignore[attr-defined]
    app = create_app(s, repos=create_repositories("memory", clock=clock), providers=providers, clock=clock)
    c = TestClient(app, base_url="https://testserver")
    r = c.post(
        f"{API}/platform/tenants", headers={"X-Platform-Key": s.PLATFORM_KEY},
        json={"name": "Az", "adminName": "A", "adminEmail": "a@azurite.example", "password": PASSWORD},
    )  # fmt: skip
    tenant_id = r.json()["tenantId"]
    c.post(f"{API}/auth/login", json={"email": "a@azurite.example", "password": PASSWORD})
    body = {"title": "T", "durationMinutes": 30, "passingScore": 50,
            "sections": [{"type": "mcq", "domain": "x", "difficulty": "easy", "count": 1}]}  # fmt: skip
    aid = c.post(f"{API}/assessments", json=body).json()["id"]

    assert c.post(f"{API}/assessments/{aid}/jd-file", files={"file": ("one.pdf", make_pdf(JD_TEXT))}).status_code == 200
    p1 = f"{tenant_id}/{aid}/one.pdf"
    assert providers.files.get_jd(p1).startswith(b"%PDF-")

    assert c.post(f"{API}/assessments/{aid}/jd-file", files={"file": ("two.txt", JD_TEXT.encode())}).status_code == 200
    p2 = f"{tenant_id}/{aid}/two.txt"
    assert providers.files.get_jd(p2) == JD_TEXT.encode()
    with pytest.raises(Exception, match="(?i)not ?found|BlobNotFound"):
        providers.files.get_jd(p1)  # the replaced file is gone

    assert c.delete(f"{API}/assessments/{aid}").status_code == 204
    with pytest.raises(Exception, match="(?i)not ?found|BlobNotFound"):
        providers.files.get_jd(p2)

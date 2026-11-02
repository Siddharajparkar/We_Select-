"""Phase 5 integration: endpoints 8-14 over HTTP (in-memory repositories + in-memory blob store)."""

from __future__ import annotations

import pytest

from app.providers.files_memory import MemoryFilesProvider
from app.repositories import Repositories
from conftest import API, Account
from helpers_pdf import JD_TEXT, make_pdf

BODY = {
    "title": "Backend Engineer",
    "jobDescription": "We need a backend engineer.",
    "durationMinutes": 60,
    "passingScore": 60,
    "sections": [
        {"type": "mcq", "domain": "Python", "difficulty": "medium", "count": 10},
        {"type": "descriptive", "domain": "System design", "difficulty": "hard", "count": 2},
    ],
}


@pytest.fixture
def files(app) -> MemoryFilesProvider:  # type: ignore[no-untyped-def]
    f = app.state.providers.files
    assert isinstance(f, MemoryFilesProvider)
    return f


def make(acct: Account, **over: object) -> str:
    r = acct.client.post(f"{API}/assessments", json={**BODY, **over})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def upload(acct: Account, aid: str, name: str, content: bytes, ctype: str = "application/octet-stream"):  # type: ignore[no-untyped-def]
    return acct.client.post(f"{API}/assessments/{aid}/jd-file", files={"file": (name, content, ctype)})


def set_status(repos: Repositories, acct: Account, aid: str, status: str) -> None:
    repos.assessments.update(acct.tenant_id, aid, status=status)


# ── create / get / list ─────────────────────────────────────────────────────────────────────
def test_create_returns_id_and_draft_and_is_audited(tenant_a: Account, repos: Repositories) -> None:
    r = tenant_a.client.post(f"{API}/assessments", json=BODY)
    assert r.status_code == 201 and r.json()["status"] == "draft"
    aid = r.json()["id"]
    assert [e.action for e in repos.audit.list_by_entity(tenant_a.tenant_id, "assessment", aid)] == [
        "assessment.create"
    ]


def test_get_returns_the_full_object(tenant_a: Account) -> None:
    aid = make(tenant_a)
    g = tenant_a.client.get(f"{API}/assessments/{aid}").json()
    assert g["title"] == "Backend Engineer" and g["status"] == "draft" and g["jdFileName"] is None
    assert g["jobDescription"] == BODY["jobDescription"] and g["sections"] == BODY["sections"]
    assert g["durationMinutes"] == 60 and g["passingScore"] == 60 and g["createdBy"] == tenant_a.admin_id


def test_create_without_job_description_is_allowed(tenant_a: Account) -> None:
    body = {k: v for k, v in BODY.items() if k != "jobDescription"}
    r = tenant_a.client.post(f"{API}/assessments", json=body)
    assert r.status_code == 201
    assert tenant_a.client.get(f"{API}/assessments/{r.json()['id']}").json()["jobDescription"] is None


@pytest.mark.parametrize(
    "over",
    [
        {"title": ""},
        {"durationMinutes": 4},
        {"passingScore": 101},
        {"sections": []},
        {"jobDescription": "a" * 20_001},
        {"sections": [{"type": "mcq", "domain": "x", "difficulty": "easy", "count": 21}]},
        {"sections": [{"type": "mcq", "domain": "x", "difficulty": "easy", "count": 20}] * 3},  # 60 total
    ],
)
def test_create_validation_400_with_details(tenant_a: Account, over: dict[str, object]) -> None:
    r = tenant_a.client.post(f"{API}/assessments", json={**BODY, **over})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR" and r.json()["error"]["details"]


def test_list_has_counts_status_filter_and_newest_first(tenant_a: Account, repos: Repositories) -> None:
    a1, a2 = make(tenant_a, title="One"), make(tenant_a, title="Two")
    added, _, _ = repos.participants.create_many(
        tenant_a.tenant_id, a1, [{"name": f"P{i}", "email": f"p{i}@x.example"} for i in range(3)]
    )
    q = repos.questions.create(
        tenant_a.tenant_id, assessment_id=a1, type="mcq", body="q", options=list("ABCD"), correct_answer="A"
    )
    att = repos.attempts.create(
        tenant_a.tenant_id,
        participant_id=added[0].id,
        assessment_id=a1,
        attempt_token_hash="h" * 64,
        deadline_at=repos.clock.now(),
    )
    repos.attempts.update_status(tenant_a.tenant_id, att.id, "submitted")
    assert q
    rows = tenant_a.client.get(f"{API}/assessments").json()
    by_title = {r["title"]: r for r in rows}
    assert by_title["One"]["participantCount"] == 3 and by_title["One"]["submittedCount"] == 1
    assert by_title["Two"]["participantCount"] == 0 and by_title["Two"]["submittedCount"] == 0
    assert set(rows[0]) == {"id", "title", "status", "participantCount", "submittedCount", "createdAt"}
    set_status(repos, tenant_a, a2, "approved")
    assert [r["title"] for r in tenant_a.client.get(f"{API}/assessments?status=approved").json()] == ["Two"]
    assert [r["title"] for r in tenant_a.client.get(f"{API}/assessments?status=draft").json()] == ["One"]


def test_list_invalid_status_is_400(tenant_a: Account) -> None:
    assert tenant_a.client.get(f"{API}/assessments?status=bogus").status_code == 400


# ── patch ───────────────────────────────────────────────────────────────────────────────────
def test_patch_draft_changes_only_the_given_fields(tenant_a: Account) -> None:
    aid = make(tenant_a)
    r = tenant_a.client.patch(f"{API}/assessments/{aid}", json={"title": "Renamed", "durationMinutes": 90})
    assert r.status_code == 200
    b = r.json()
    assert b["title"] == "Renamed" and b["durationMinutes"] == 90 and b["passingScore"] == 60
    assert b["sections"] == BODY["sections"] and b["warnings"] == []


def test_patch_can_clear_the_job_description_with_null(tenant_a: Account) -> None:
    aid = make(tenant_a)
    r = tenant_a.client.patch(f"{API}/assessments/{aid}", json={"jobDescription": None})
    assert r.status_code == 200 and r.json()["jobDescription"] is None


def test_patch_validation(tenant_a: Account) -> None:
    aid = make(tenant_a)
    for body in ({}, {"title": None}, {"passingScore": 200}, {"sections": []}):
        assert tenant_a.client.patch(f"{API}/assessments/{aid}", json=body).status_code == 400


@pytest.mark.parametrize("status", ["approved", "open", "closed"])
def test_patch_non_draft_is_409(tenant_a: Account, repos: Repositories, status: str) -> None:
    aid = make(tenant_a)
    set_status(repos, tenant_a, aid, status)
    r = tenant_a.client.patch(f"{API}/assessments/{aid}", json={"title": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


def test_changing_sections_warns_about_kept_ai_questions(tenant_a: Account, repos: Repositories) -> None:
    aid = make(tenant_a)
    repos.questions.create_many(
        tenant_a.tenant_id,
        [
            {
                "assessment_id": aid,
                "section_index": 0,
                "type": "mcq",
                "body": f"q{i}",
                "options": list("ABCD"),
                "correct_answer": "A",
                "source": "ai",
            }
            for i in range(3)
        ]
        + [
            {
                "assessment_id": aid,
                "section_index": 1,
                "type": "descriptive",
                "body": "d",
                "rubric": "r",
                "source": "custom",
            }
        ],
    )
    new_sections = [{**BODY["sections"][0], "count": 5}, BODY["sections"][1]]  # type: ignore[index]
    r = tenant_a.client.patch(f"{API}/assessments/{aid}", json={"sections": new_sections})
    assert r.status_code == 200
    assert (
        len(r.json()["warnings"]) == 1
        and "Section 1" in r.json()["warnings"][0]
        and "3 existing" in r.json()["warnings"][0]
    )
    assert len(repos.questions.list_by_assessment(tenant_a.tenant_id, aid)) == 4  # nothing deleted
    same = tenant_a.client.patch(f"{API}/assessments/{aid}", json={"sections": new_sections})
    assert same.json()["warnings"] == []  # unchanged sections: no warning


# ── delete ──────────────────────────────────────────────────────────────────────────────────
def test_delete_draft_204_then_404(tenant_a: Account) -> None:
    aid = make(tenant_a)
    assert tenant_a.client.delete(f"{API}/assessments/{aid}").status_code == 204
    assert tenant_a.client.get(f"{API}/assessments/{aid}").status_code == 404


@pytest.mark.parametrize("status", ["approved", "open", "closed"])
def test_delete_non_draft_is_409(tenant_a: Account, repos: Repositories, status: str) -> None:
    aid = make(tenant_a)
    set_status(repos, tenant_a, aid, status)
    assert tenant_a.client.delete(f"{API}/assessments/{aid}").status_code == 409
    assert tenant_a.client.get(f"{API}/assessments/{aid}").status_code == 200


def test_delete_removes_questions_and_the_blob(
    tenant_a: Account, repos: Repositories, files: MemoryFilesProvider
) -> None:
    aid = make(tenant_a)
    upload(tenant_a, aid, "jd.txt", JD_TEXT.encode())
    repos.questions.create(
        tenant_a.tenant_id, assessment_id=aid, type="mcq", body="q", options=list("ABCD"), correct_answer="B"
    )
    assert files.store
    assert tenant_a.client.delete(f"{API}/assessments/{aid}").status_code == 204
    assert files.store == {} and repos.questions.list_by_assessment(tenant_a.tenant_id, aid) == []


def test_delete_survives_a_blob_failure(
    tenant_a: Account, files: MemoryFilesProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    aid = make(tenant_a)
    upload(tenant_a, aid, "jd.txt", JD_TEXT.encode())
    monkeypatch.setattr(files, "delete_jd", lambda _p: (_ for _ in ()).throw(RuntimeError("storage down")))
    assert tenant_a.client.delete(f"{API}/assessments/{aid}").status_code == 204  # best effort, logged


# ── jd-file upload ──────────────────────────────────────────────────────────────────────────
def test_upload_txt_sets_text_and_file_name(tenant_a: Account, files: MemoryFilesProvider) -> None:
    aid = make(tenant_a)
    r = upload(tenant_a, aid, "jd.txt", JD_TEXT.encode(), "text/plain")
    assert r.status_code == 200
    b = r.json()
    assert b["fileName"] == "jd.txt" and b["wordCount"] > 30 and "FastAPI" in b["jobDescription"]
    g = tenant_a.client.get(f"{API}/assessments/{aid}").json()
    assert g["jdFileName"] == "jd.txt" and g["jobDescription"] == b["jobDescription"]
    assert (
        list(files.store) == [f"{tenant_a.tenant_id}/{aid}/jd.txt"]
        and files.store[f"{tenant_a.tenant_id}/{aid}/jd.txt"] == JD_TEXT.encode()
    )


def test_upload_pdf_extracts_text(tenant_a: Account, files: MemoryFilesProvider) -> None:
    aid = make(tenant_a)
    r = upload(tenant_a, aid, "Job Spec.pdf", make_pdf(JD_TEXT), "application/pdf")
    assert r.status_code == 200 and "FastAPI" in r.json()["jobDescription"]
    assert f"{tenant_a.tenant_id}/{aid}/Job Spec.pdf" in files.store


def test_replacing_the_file_removes_the_old_blob(tenant_a: Account, files: MemoryFilesProvider) -> None:
    aid = make(tenant_a)
    upload(tenant_a, aid, "first.txt", JD_TEXT.encode())
    upload(tenant_a, aid, "second.pdf", make_pdf(JD_TEXT))
    assert list(files.store) == [f"{tenant_a.tenant_id}/{aid}/second.pdf"]
    assert tenant_a.client.get(f"{API}/assessments/{aid}").json()["jdFileName"] == "second.pdf"


def test_replacing_with_the_same_name_keeps_one_blob(tenant_a: Account, files: MemoryFilesProvider) -> None:
    aid = make(tenant_a)
    upload(tenant_a, aid, "jd.txt", JD_TEXT.encode())
    upload(tenant_a, aid, "jd.txt", (JD_TEXT + "\nNew requirement: Azure experience.").encode())
    assert len(files.store) == 1 and b"New requirement" in next(iter(files.store.values()))


def test_path_traversal_in_the_file_name_cannot_escape_the_prefix(
    tenant_a: Account, files: MemoryFilesProvider
) -> None:
    aid = make(tenant_a)
    r = upload(tenant_a, aid, "../../other/evil.txt", JD_TEXT.encode())
    assert r.status_code == 200
    (path,) = files.store
    assert (
        path.startswith(f"{tenant_a.tenant_id}/{aid}/")
        and path.count("/") == 2
        and "/.." not in path.replace(f"/{aid}/", "", 1)
    )


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("evil.pdf", b"MZ\x90\x00not a pdf"),
        ("a.txt", b"abc\x00def"),
        ("a.txt", "caf\xe9".encode("latin-1")),
        ("a.docx", b"PK\x03\x04"),
        ("a.exe", b"%PDF-1.4"),
    ],
)
def test_wrong_type_is_400_and_nothing_is_stored(
    tenant_a: Account, files: MemoryFilesProvider, name: str, content: bytes
) -> None:
    aid = make(tenant_a)
    r = upload(tenant_a, aid, name, content, "application/pdf")  # the client's mime type is never trusted
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert files.store == {}


def test_corrupt_or_empty_pdf_is_422(tenant_a: Account, files: MemoryFilesProvider) -> None:
    aid = make(tenant_a)
    for content in (b"%PDF-1.4\ngarbage", make_pdf("")):
        r = upload(tenant_a, aid, "scan.pdf", content)
        assert r.status_code == 422 and r.json()["error"]["code"] == "FILE_UNREADABLE"
        assert "Paste" in r.json()["error"]["message"]
    assert files.store == {}


def test_text_over_20000_chars_is_422_not_truncated(tenant_a: Account, files: MemoryFilesProvider) -> None:
    aid = make(tenant_a)
    r = upload(tenant_a, aid, "big.txt", b"a" * 20_001)
    assert r.status_code == 422 and "20,000" in r.json()["error"]["message"] and files.store == {}
    assert upload(tenant_a, aid, "ok.txt", b"a" * 20_000).status_code == 200


def test_file_size_limit_is_exactly_2_mb(tenant_a: Account, files: MemoryFilesProvider) -> None:
    aid = make(tenant_a)
    two_mb = 2 * 1024 * 1024
    ok = upload(tenant_a, aid, "ok.txt", b"word " * 10 + b"a" * 100)  # control: small file works
    assert ok.status_code == 200
    r = upload(tenant_a, aid, "big.txt", b"a" * (two_mb + 1))
    assert (
        r.status_code == 400
        and r.json()["error"]["code"] == "VALIDATION_ERROR"
        and "2 MB" in r.json()["error"]["message"]
    )
    r = upload(tenant_a, aid, "exact.txt", b"a" * two_mb)  # exactly 2 MB passes size check, then fails the text limit
    assert r.status_code == 422


def test_absurdly_large_body_is_413(tenant_a: Account) -> None:
    aid = make(tenant_a)
    r = upload(tenant_a, aid, "huge.txt", b"a" * (3 * 1024 * 1024))
    assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_missing_file_field_is_400(tenant_a: Account) -> None:
    aid = make(tenant_a)
    r = tenant_a.client.post(f"{API}/assessments/{aid}/jd-file", data={"x": "y"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_upload_to_a_non_draft_is_409(tenant_a: Account, repos: Repositories, files: MemoryFilesProvider) -> None:
    aid = make(tenant_a)
    set_status(repos, tenant_a, aid, "approved")
    r = upload(tenant_a, aid, "jd.txt", JD_TEXT.encode())
    assert r.status_code == 409 and files.store == {}


def test_failed_db_update_removes_the_new_blob(
    tenant_a: Account, repos: Repositories, files: MemoryFilesProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    aid = make(tenant_a)
    monkeypatch.setattr(repos.assessments, "update", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    client = tenant_a.client
    client.raise_server_exceptions = False
    r = upload(tenant_a, aid, "jd.txt", JD_TEXT.encode())
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL"
    assert files.store == {}  # no orphan blob


def test_upload_is_audited(tenant_a: Account, repos: Repositories) -> None:
    aid = make(tenant_a)
    upload(tenant_a, aid, "jd.txt", JD_TEXT.encode())
    assert "assessment.jd_upload" in [
        e.action for e in repos.audit.list_by_entity(tenant_a.tenant_id, "assessment", aid)
    ]


# ── close ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status", ["approved", "open"])
def test_close_from_approved_or_open(tenant_a: Account, repos: Repositories, status: str) -> None:
    aid = make(tenant_a)
    set_status(repos, tenant_a, aid, status)
    r = tenant_a.client.post(f"{API}/assessments/{aid}/close")
    assert r.status_code == 200 and r.json() == {"id": aid, "status": "closed"}
    assert tenant_a.client.get(f"{API}/assessments/{aid}").json()["status"] == "closed"
    assert "assessment.close" in [e.action for e in repos.audit.list_by_entity(tenant_a.tenant_id, "assessment", aid)]


@pytest.mark.parametrize("status", ["draft", "closed"])
def test_close_from_draft_or_closed_is_409(tenant_a: Account, repos: Repositories, status: str) -> None:
    aid = make(tenant_a)
    set_status(repos, tenant_a, aid, status)
    assert tenant_a.client.post(f"{API}/assessments/{aid}/close").status_code == 409


# ── roles ───────────────────────────────────────────────────────────────────────────────────
def test_recruiter_and_admin_can_use_every_endpoint(tenant_a: Account, recruiter: Account, repos: Repositories) -> None:
    aid = make(recruiter)
    assert recruiter.client.get(f"{API}/assessments").status_code == 200
    assert tenant_a.client.get(f"{API}/assessments/{aid}").status_code == 200  # admin sees the recruiter's assessment
    assert recruiter.client.patch(f"{API}/assessments/{aid}", json={"title": "r"}).status_code == 200
    assert upload(recruiter, aid, "jd.txt", JD_TEXT.encode()).status_code == 200
    set_status(repos, tenant_a, aid, "approved")
    assert recruiter.client.post(f"{API}/assessments/{aid}/close").status_code == 200


def test_anonymous_gets_401_everywhere(new_client, tenant_a: Account) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    c = new_client()
    calls = [
        c.post(f"{API}/assessments", json=BODY),
        c.get(f"{API}/assessments"),
        c.get(f"{API}/assessments/{aid}"),
        c.patch(f"{API}/assessments/{aid}", json={"title": "x"}),
        c.delete(f"{API}/assessments/{aid}"),
        c.post(f"{API}/assessments/{aid}/jd-file", files={"file": ("a.txt", b"x")}),
        c.post(f"{API}/assessments/{aid}/close"),
    ]
    assert [r.status_code for r in calls] == [401] * 7


def test_malformed_id_is_400_unknown_is_404(tenant_a: Account) -> None:
    unknown = "00000000-0000-4000-8000-000000000000"
    for method, suffix in (("get", ""), ("patch", ""), ("delete", ""), ("post", "/close"), ("post", "/jd-file")):
        kw = {"json": {"title": "x"}} if method == "patch" else {}
        assert getattr(tenant_a.client, method)(f"{API}/assessments/not-a-uuid{suffix}", **kw).status_code == 400
        r = getattr(tenant_a.client, method)(
            f"{API}/assessments/{unknown}{suffix}",
            **({"files": {"file": ("a.txt", b"x" * 40)}} if suffix == "/jd-file" else kw),
        )
        assert r.status_code == 404, (method, suffix, r.status_code)


# ── cross-tenant ────────────────────────────────────────────────────────────────────────────
def test_tenant_b_cannot_touch_tenant_a_assessments(
    tenant_a: Account, tenant_b: Account, files: MemoryFilesProvider
) -> None:
    aid = make(tenant_a)
    upload(tenant_a, aid, "jd.txt", JD_TEXT.encode())
    before = dict(files.store)
    b = tenant_b.client
    assert b.get(f"{API}/assessments/{aid}").status_code == 404
    assert b.patch(f"{API}/assessments/{aid}", json={"title": "pwned"}).status_code == 404
    assert b.delete(f"{API}/assessments/{aid}").status_code == 404
    assert upload(tenant_b, aid, "evil.txt", JD_TEXT.encode()).status_code == 404
    assert b.post(f"{API}/assessments/{aid}/close").status_code == 404
    assert files.store == before  # nothing written to or removed from A's prefix
    g = tenant_a.client.get(f"{API}/assessments/{aid}").json()
    assert g["title"] == "Backend Engineer" and g["status"] == "draft" and g["jdFileName"] == "jd.txt"


def test_lists_never_show_other_tenants(tenant_a: Account, tenant_b: Account) -> None:
    ids_a = {make(tenant_a, title=f"A{i}") for i in range(2)}
    ids_b = {make(tenant_b, title="B0")}
    assert {r["id"] for r in tenant_a.client.get(f"{API}/assessments").json()} == ids_a
    assert {r["id"] for r in tenant_b.client.get(f"{API}/assessments").json()} == ids_b

"""Phase 6 integration: endpoints 15-16 (generate + jobs) with the job engine driven synchronously."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from app.providers.ai_fake import FakeAiProvider
from app.providers.ports import GeneratedQuestion, GenerateQuestionsInput, ProviderError
from conftest import API, Account

JD = " ".join(f"skill{i}" for i in range(120))  # 120 words
SECTIONS = [
    {"type": "mcq", "domain": "Python", "difficulty": "medium", "count": 3},
    {"type": "descriptive", "domain": "System design", "difficulty": "hard", "count": 2},
]


def make(acct: Account, jd: str | None = JD, sections: list[dict[str, Any]] | None = None) -> str:
    body = {"title": "Backend", "jobDescription": jd, "durationMinutes": 60, "passingScore": 60,
            "sections": sections or SECTIONS}  # fmt: skip
    r = acct.client.post(f"{API}/assessments", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def gen(acct: Account, aid: str, body: dict[str, Any] | None = None):  # type: ignore[no-untyped-def]
    return acct.client.post(f"{API}/assessments/{aid}/generate", json=body or {})


def job(acct: Account, jid: str) -> dict[str, Any]:
    r = acct.client.get(f"{API}/jobs/{jid}")
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def run_jobs(app) -> int:  # type: ignore[no-untyped-def]
    return app.state.jobs.drain()  # type: ignore[no-any-return]


def questions(acct: Account, aid: str) -> list[dict[str, Any]]:
    return acct.client.get(f"{API}/assessments/{aid}/questions").json()  # type: ignore[no-any-return]


@pytest.fixture
def ai(app) -> FakeAiProvider:  # type: ignore[no-untyped-def]
    f = app.state.providers.ai
    assert isinstance(f, FakeAiProvider)
    return f


# ── happy path ──────────────────────────────────────────────────────────────────────────────
def test_generate_returns_202_queued_job_then_creates_all_sections(tenant_a: Account, app, ai) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    r = gen(tenant_a, aid)
    assert r.status_code == 202 and r.json()["status"] == "queued"
    jid = r.json()["jobId"]
    assert job(tenant_a, jid)["status"] == "queued"
    assert questions(tenant_a, aid) == []  # nothing happens before the engine runs
    assert run_jobs(app) == 1
    j = job(tenant_a, jid)
    assert j["status"] == "done" and j["error"] is None and j["tokensUsed"] == 250 and j["attempts"] == 1
    assert j["result"]["questionsCreated"] == 5 and j["result"]["warnings"] == []
    qs = questions(tenant_a, aid)
    assert [q["sectionIndex"] for q in qs] == [0, 0, 0, 1, 1]
    assert {q["source"] for q in qs} == {"ai"} and {q["status"] for q in qs} == {"draft"}
    mcq = qs[0]
    assert len(mcq["options"]) == 4 and mcq["correctAnswer"] in "ABCD" and mcq["explanation"] and mcq["maxScore"] == 1
    assert mcq["rubric"] is None and mcq["wordLimit"] is None
    d = qs[3]
    assert d["options"] is None and d["rubric"] and d["maxScore"] == 10 and d["wordLimit"] == 250
    assert [q["position"] for q in qs[:3]] == [0, 1, 2]
    assert ai.call_count == 2  # one call per section (counts below the batch size)


def test_ai_receives_the_jd_and_section_settings(tenant_a: Account, app, ai) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    gen(tenant_a, aid)
    run_jobs(app)
    first, second = ai.calls
    assert first.job_description == JD and (first.type, first.domain, first.difficulty, first.count) == (
        "mcq", "Python", "medium", 3,
    )  # fmt: skip
    assert (second.type, second.count) == ("descriptive", 2)


def test_large_sections_are_requested_in_batches_of_five(tenant_a: Account, app, ai) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a, sections=[{"type": "mcq", "domain": "Go", "difficulty": "easy", "count": 12}])
    gen(tenant_a, aid)
    run_jobs(app)
    assert [c.count for c in ai.calls] == [5, 5, 2]
    assert len(questions(tenant_a, aid)) == 12


def test_audit_entry_for_generate(tenant_a: Account, repos) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    jid = gen(tenant_a, aid).json()["jobId"]
    ev = repos.audit.list_by_entity(tenant_a.tenant_id, "assessment", aid)
    assert "assessment.generate" in [e.action for e in ev]
    assert next(e for e in ev if e.action == "assessment.generate").details["jobId"] == jid


# ── selection, replacement (R8) and partial results (R7) ───────────────────────────────────
def test_only_selected_sections_are_generated(tenant_a: Account, app, ai) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    gen(tenant_a, aid, {"sectionIndexes": [1]})
    run_jobs(app)
    assert {q["sectionIndex"] for q in questions(tenant_a, aid)} == {1}
    assert [c.type for c in ai.calls] == ["descriptive"]


def test_regenerating_replaces_ai_draft_questions_and_keeps_custom_ones(tenant_a: Account, app, ai) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    gen(tenant_a, aid)
    run_jobs(app)
    old = {q["id"] for q in questions(tenant_a, aid)}
    custom = tenant_a.client.post(
        f"{API}/assessments/{aid}/questions",
        json={"sectionIndex": 0, "type": "mcq", "body": "My own question?", "options": ["w", "x", "y", "z"], "correctAnswer": "C"},
    )  # fmt: skip
    assert custom.status_code == 201
    ai.calls.clear()
    jid = gen(tenant_a, aid, {"sectionIndexes": [0]}).json()["jobId"]
    run_jobs(app)
    qs = questions(tenant_a, aid)
    sec0 = [q for q in qs if q["sectionIndex"] == 0]
    assert ai.calls[0].count == 2  # 3 configured - 1 custom kept
    assert len(sec0) == 3 and any(q["id"] == custom.json()["id"] for q in sec0)
    assert not ({q["id"] for q in sec0 if q["source"] == "ai"} & old)  # AI ones are new
    assert {q["id"] for q in qs if q["sectionIndex"] == 1} <= old  # untouched section kept
    assert job(tenant_a, jid)["result"]["sections"][0]["requested"] == 2


def test_fewer_questions_than_requested_are_kept_with_a_warning(tenant_a: Account, app, ai) -> None:  # type: ignore[no-untyped-def]
    ai.script = [
        [
            GeneratedQuestion("mcq", f"Question number {i} about topic{i}x", ["a", "b", "c", "d"], "A", "e")
            for i in (1, 2)
        ]
    ]
    ai.partial_count = 0  # every later call returns nothing: the section stays short
    aid = make(tenant_a, sections=[SECTIONS[0]])
    jid = gen(tenant_a, aid).json()["jobId"]
    run_jobs(app)
    j = job(tenant_a, jid)
    assert j["status"] == "done" and j["result"]["questionsCreated"] == 2
    assert j["result"]["warnings"] == ["Section 1: only 2 of 3 questions could be generated."]


def test_duplicates_of_kept_questions_are_dropped(tenant_a: Account, app, ai) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a, sections=[SECTIONS[0]])
    custom = {"sectionIndex": 0, "type": "mcq", "body": "What is the time complexity of binary search on sorted data",
              "options": ["O(1)", "O(n)", "O(log n)", "O(n^2)"], "correctAnswer": "C"}  # fmt: skip
    tenant_a.client.post(f"{API}/assessments/{aid}/questions", json=custom)

    def same(text: str) -> GeneratedQuestion:
        return GeneratedQuestion("mcq", text, ["a", "b", "c", "d"], "A", "e")

    ai.script = [[same(custom["body"] + "?"), same("Name the HTTP verb used to create a resource"),
                  same("Which keyword defines a generator function in the language")]]  # fmt: skip
    jid = gen(tenant_a, aid).json()["jobId"]
    run_jobs(app)
    j = job(tenant_a, jid)
    assert j["result"]["sections"][0]["duplicatesDropped"] == 1
    assert len(questions(tenant_a, aid)) == 3  # 1 custom + 2 new (needed 2)


# ── failures: retries, messages, atomicity ─────────────────────────────────────────────────
def test_transient_failure_is_retried_after_5_seconds(tenant_a: Account, app, ai, clock) -> None:  # type: ignore[no-untyped-def]
    ai.fail_count = 1
    aid = make(tenant_a, sections=[SECTIONS[0]])
    jid = gen(tenant_a, aid).json()["jobId"]
    run_jobs(app)
    j = job(tenant_a, jid)
    assert j["status"] == "queued" and j["attempts"] == 1 and "temporarily unavailable" in j["error"]
    assert run_jobs(app) == 0
    clock.advance(seconds=5)
    run_jobs(app)
    j = job(tenant_a, jid)
    assert j["status"] == "done" and j["attempts"] == 2 and j["error"] is None
    assert len(questions(tenant_a, aid)) == 3


def test_timeout_fails_after_three_attempts_with_readable_message_and_no_questions(
    tenant_a: Account, app, ai, clock
) -> None:  # type: ignore[no-untyped-def]
    ai.simulate_timeout = True
    aid = make(tenant_a)
    jid = gen(tenant_a, aid).json()["jobId"]
    for _ in range(3):
        run_jobs(app)
        clock.advance(seconds=30)
    j = job(tenant_a, jid)
    assert j["status"] == "failed" and j["attempts"] == 3 and j["errorCode"] == "AI_TIMEOUT"
    assert j["error"] == "The AI service took too long to answer." and j["result"] is None
    assert questions(tenant_a, aid) == []


def test_rate_limit_is_retried_using_the_provider_delay(tenant_a: Account, app, ai, clock, repos) -> None:  # type: ignore[no-untyped-def]
    ai.simulate_429 = True
    aid = make(tenant_a, sections=[SECTIONS[0]])
    jid = gen(tenant_a, aid).json()["jobId"]
    run_jobs(app)
    stored = repos.jobs.find_by_id(tenant_a.tenant_id, jid)
    assert stored.status == "queued" and stored.run_after == clock.now() + timedelta(seconds=2)  # type: ignore[union-attr]
    assert "busy" in job(tenant_a, jid)["error"]


def test_invalid_ai_output_fails_without_retry_as_ai_output_invalid(tenant_a: Account, app, ai) -> None:  # type: ignore[no-untyped-def]
    ai.return_invalid_json = True
    aid = make(tenant_a)
    jid = gen(tenant_a, aid).json()["jobId"]
    run_jobs(app)
    j = job(tenant_a, jid)
    assert j["status"] == "failed" and j["attempts"] == 1 and j["errorCode"] == "AI_OUTPUT_INVALID"
    assert "3 attempts" in j["error"]


def test_a_failure_in_a_later_section_leaves_no_partial_questions(tenant_a: Account, app, ai, clock) -> None:  # type: ignore[no-untyped-def]
    class FailSecond(FakeAiProvider):
        def generate_questions_with_usage(self, data: GenerateQuestionsInput):  # type: ignore[no-untyped-def]
            if data.type == "descriptive":
                raise ProviderError("down", "UPSTREAM")
            return super().generate_questions_with_usage(data)

    app.state.providers.ai = FailSecond()
    aid = make(tenant_a)
    jid = gen(tenant_a, aid).json()["jobId"]
    run_jobs(app)
    assert job(tenant_a, jid)["status"] == "queued"
    assert questions(tenant_a, aid) == []  # section 1 had been generated but was not saved


def test_approving_before_the_job_runs_makes_the_job_fail_cleanly(tenant_a: Account, app, repos) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a, sections=[SECTIONS[0]])
    jid = gen(tenant_a, aid).json()["jobId"]
    repos.assessments.update(tenant_a.tenant_id, aid, status="approved")
    run_jobs(app)
    j = job(tenant_a, jid)
    assert j["status"] == "failed" and j["errorCode"] == "CONFLICT" and "approved" in j["error"]
    assert questions(tenant_a, aid) == []


def test_assessment_deleted_before_the_job_runs(tenant_a: Account, app) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    jid = gen(tenant_a, aid).json()["jobId"]
    assert tenant_a.client.delete(f"{API}/assessments/{aid}").status_code == 204
    run_jobs(app)
    assert job(tenant_a, jid)["errorCode"] == "NOT_FOUND"


# ── request checks, in the specified order ─────────────────────────────────────────────────
def test_unknown_assessment_404_malformed_400(tenant_a: Account) -> None:
    assert gen(tenant_a, "00000000-0000-4000-8000-000000000000").status_code == 404
    r = gen(tenant_a, "not-a-uuid")
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_non_draft_is_409(tenant_a: Account, repos) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    repos.assessments.update(tenant_a.tenant_id, aid, status="approved")
    r = gen(tenant_a, aid)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


@pytest.mark.parametrize("words,status", [(0, 422), (1, 422), (99, 422), (100, 202), (101, 202)])
def test_jd_must_have_at_least_100_words(tenant_a: Account, words: int, status: int) -> None:
    aid = make(tenant_a, jd=" ".join(["w"] * words) if words else None)
    r = gen(tenant_a, aid)
    assert r.status_code == status
    if status == 422:
        assert r.json()["error"]["code"] == "JD_TOO_SHORT"


@pytest.mark.parametrize("bad", [[], [2], [-1], [0, 0], [0, 5], ["a"], [1.5], "0", {"a": 1}])
def test_invalid_section_indexes_are_400(tenant_a: Account, bad: Any) -> None:
    aid = make(tenant_a)
    r = gen(tenant_a, aid, {"sectionIndexes": bad})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_check_order_409_then_422_then_400_then_429(tenant_a: Account, repos, settings) -> None:  # type: ignore[no-untyped-def]
    short = make(tenant_a, jd="too short")
    assert gen(tenant_a, short, {"sectionIndexes": [9]}).status_code == 422  # JD before indexes
    repos.assessments.update(tenant_a.tenant_id, short, status="approved")
    assert gen(tenant_a, short, {"sectionIndexes": [9]}).status_code == 409  # status before JD
    ok = make(tenant_a)
    for _ in range(settings.DAILY_GENERATION_LIMIT):
        assert gen(tenant_a, ok).status_code == 202
    assert gen(tenant_a, ok, {"sectionIndexes": [9]}).status_code == 400  # indexes before the cap
    assert gen(tenant_a, ok).status_code == 429


def test_daily_cap_is_20_per_tenant_per_utc_day_with_retry_after(tenant_a: Account, tenant_b: Account, clock) -> None:  # type: ignore[no-untyped-def]
    a, b = make(tenant_a), make(tenant_b)
    for _ in range(20):
        assert gen(tenant_a, a).status_code == 202
    r = gen(tenant_a, a)
    assert r.status_code == 429 and r.json()["error"]["code"] == "DAILY_AI_LIMIT"
    assert r.headers["retry-after"] == str(12 * 3600)  # clock starts at 12:00 UTC
    assert gen(tenant_b, b).status_code == 202  # other tenants are unaffected
    clock.advance(hours=12)  # next UTC day (the old session has idled out, so sign in again)
    assert (
        tenant_a.client.post(
            f"{API}/auth/login", json={"email": tenant_a.email, "password": tenant_a.password}
        ).status_code
        == 200
    )
    assert gen(tenant_a, a).status_code == 202


def test_token_allowance_also_blocks_generation(tenant_a: Account, app, ai, repos) -> None:  # type: ignore[no-untyped-def]
    app.state.settings.AI_DAILY_TOKEN_CAP = 300
    aid = make(tenant_a)
    gen(tenant_a, aid)
    run_jobs(app)  # spends 250 tokens
    assert gen(tenant_a, aid).status_code == 202
    ai.tokens_per_question = 1000
    run_jobs(app)  # pushes the day's total past the cap
    r = gen(tenant_a, aid)
    assert r.status_code == 429 and r.json()["error"]["code"] == "DAILY_AI_LIMIT"


# ── jobs endpoint ───────────────────────────────────────────────────────────────────────────
def test_job_endpoint_shape(tenant_a: Account, app) -> None:  # type: ignore[no-untyped-def]
    jid = gen(tenant_a, make(tenant_a)).json()["jobId"]
    run_jobs(app)
    j = job(tenant_a, jid)
    assert set(j) == {"id", "type", "status", "attempts", "maxAttempts", "result", "error", "errorCode",
                      "tokensUsed", "createdAt", "updatedAt"}  # fmt: skip
    assert j["type"] == "generate" and j["maxAttempts"] == 3 and j["createdAt"].endswith("Z")


def test_job_unknown_or_malformed(tenant_a: Account) -> None:
    assert tenant_a.client.get(f"{API}/jobs/00000000-0000-4000-8000-000000000000").status_code == 404
    assert tenant_a.client.get(f"{API}/jobs/xyz").status_code == 400


# ── tenant isolation and access ─────────────────────────────────────────────────────────────
def test_other_tenant_cannot_generate_or_read_jobs(tenant_a: Account, tenant_b: Account) -> None:
    aid = make(tenant_a)
    jid = gen(tenant_a, aid).json()["jobId"]
    assert gen(tenant_b, aid).status_code == 404
    assert tenant_b.client.get(f"{API}/jobs/{jid}").status_code == 404
    assert tenant_b.client.get(f"{API}/assessments/{aid}/questions").status_code == 404


def test_endpoints_require_a_session(new_client, tenant_a: Account) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    anon = new_client()
    zero = "00000000-0000-4000-8000-000000000000"
    for method, path in [
        ("post", f"/assessments/{aid}/generate"), ("get", f"/jobs/{zero}"), ("get", f"/assessments/{aid}/questions"),
        ("post", f"/assessments/{aid}/questions"), ("patch", f"/questions/{zero}"), ("delete", f"/questions/{zero}"),
        ("post", f"/questions/{zero}/regenerate"), ("post", f"/assessments/{aid}/approve"),
    ]:  # fmt: skip
        r = getattr(anon, method)(f"{API}{path}")
        assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED", (method, path)


def test_recruiters_can_generate(recruiter: Account, tenant_a: Account, app) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    r = gen(recruiter, aid)
    assert r.status_code == 202
    run_jobs(app)
    assert job(recruiter, r.json()["jobId"])["status"] == "done"

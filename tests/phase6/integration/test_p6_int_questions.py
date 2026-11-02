"""Phase 6 integration: endpoints 17-22 (questions CRUD, regenerate, approve)."""

from __future__ import annotations

from typing import Any

import pytest

from app.providers.ai_fake import FakeAiProvider
from conftest import API, Account

JD = " ".join(f"skill{i}" for i in range(120))
SECTIONS = [
    {"type": "mcq", "domain": "Python", "difficulty": "medium", "count": 2},
    {"type": "descriptive", "domain": "Design", "difficulty": "hard", "count": 1},
]
MCQ = {"sectionIndex": 0, "type": "mcq", "body": "Which keyword starts a function?",
       "options": ["def", "fun", "func", "lambda"], "correctAnswer": "A", "explanation": "def defines functions."}  # fmt: skip
DESC = {"sectionIndex": 1, "type": "descriptive", "body": "Explain idempotency.", "rubric": "Mentions retries and safety.",
        "maxScore": 6, "wordLimit": 120}  # fmt: skip


def make(acct: Account, sections: list[dict[str, Any]] | None = None, jd: str = JD) -> str:
    r = acct.client.post(
        f"{API}/assessments",
        json={"title": "T", "jobDescription": jd, "durationMinutes": 30, "passingScore": 50, "sections": sections or SECTIONS},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    return r.json()["id"]


def add(acct: Account, aid: str, body: dict[str, Any]):  # type: ignore[no-untyped-def]
    return acct.client.post(f"{API}/assessments/{aid}/questions", json=body)


def fill(acct: Account, aid: str) -> list[str]:
    """Complete the default sections with custom questions; returns their ids."""
    ids = [add(acct, aid, {**MCQ, "body": f"Custom question {i} about topic{i}"}).json()["id"] for i in range(2)]
    ids.append(add(acct, aid, DESC).json()["id"])
    return ids


def generate_all(acct: Account, app, aid: str) -> None:  # type: ignore[no-untyped-def]
    assert acct.client.post(f"{API}/assessments/{aid}/generate", json={}).status_code == 202
    app.state.jobs.drain()


# ── list / add ──────────────────────────────────────────────────────────────────────────────
def test_empty_list_then_add_custom_questions(tenant_a: Account) -> None:
    aid = make(tenant_a)
    assert tenant_a.client.get(f"{API}/assessments/{aid}/questions").json() == []
    r = add(tenant_a, aid, MCQ)
    assert r.status_code == 201
    q = r.json()
    assert q["source"] == "custom" and q["status"] == "draft" and q["maxScore"] == 1 and q["position"] == 0
    assert q["options"] == MCQ["options"] and q["correctAnswer"] == "A" and q["explanation"] == MCQ["explanation"]
    d = add(tenant_a, aid, DESC).json()
    assert d["maxScore"] == 6 and d["wordLimit"] == 120 and d["rubric"] and d["options"] is None
    assert [x["id"] for x in tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()] == [q["id"], d["id"]]


def test_descriptive_defaults(tenant_a: Account) -> None:
    aid = make(tenant_a)
    d = add(tenant_a, aid, {k: v for k, v in DESC.items() if k not in ("maxScore", "wordLimit")}).json()
    assert d["maxScore"] == 10 and d["wordLimit"] == 250


def test_positions_increase_within_a_section(tenant_a: Account) -> None:
    aid = make(tenant_a)
    positions = [add(tenant_a, aid, {**MCQ, "body": f"Question {i} topic{i}"}).json()["position"] for i in range(3)]
    assert positions == [0, 1, 2]


@pytest.mark.parametrize(
    "patch",
    [
        {"options": ["a", "b", "c"]}, {"options": ["a", "b", "c", "d", "e"]}, {"options": ["a", "A", "c", "d"]},
        {"options": ["a", "b", "c", ""]}, {"options": None}, {"correctAnswer": "E"}, {"correctAnswer": None},
        {"body": ""}, {"body": "x" * 2001}, {"sectionIndex": 2}, {"sectionIndex": -1},
        {"type": "descriptive"},  # does not match the section type
        {"type": "essay"}, {"rubric": "too short"}, {"wordLimit": 100},
    ],
)  # fmt: skip
def test_invalid_custom_mcq_is_400(tenant_a: Account, patch: dict[str, Any]) -> None:
    aid = make(tenant_a)
    r = add(tenant_a, aid, {**MCQ, **patch})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR", r.text


def test_objective_question_may_carry_an_explicit_score(tenant_a: Account) -> None:
    r = add(tenant_a, make(tenant_a), {**MCQ, "maxScore": 5})
    assert r.status_code == 201 and r.json()["maxScore"] == 5


@pytest.mark.parametrize(
    "patch",
    [{"rubric": None}, {"rubric": "short"}, {"options": ["a", "b", "c", "d"]}, {"correctAnswer": "A"},
     {"maxScore": 0}, {"maxScore": 21}, {"wordLimit": 5}, {"wordLimit": 2001}],
)  # fmt: skip
def test_invalid_custom_descriptive_is_400(tenant_a: Account, patch: dict[str, Any]) -> None:
    aid = make(tenant_a)
    body = {k: v for k, v in {**DESC, **patch}.items() if v is not None}
    assert add(tenant_a, aid, body).status_code == 400


def test_unknown_assessment_and_malformed_id(tenant_a: Account) -> None:
    assert add(tenant_a, "00000000-0000-4000-8000-000000000000", MCQ).status_code == 404
    assert add(tenant_a, "nope", MCQ).status_code == 400
    assert tenant_a.client.get(f"{API}/assessments/nope/questions").status_code == 400


def test_section_cap_is_20_and_total_cap_is_40(tenant_a: Account) -> None:
    aid = make(tenant_a, sections=[{"type": "mcq", "domain": "x", "difficulty": "easy", "count": 1}] * 3)
    for i in range(20):
        assert add(tenant_a, aid, {**MCQ, "body": f"Q{i} unique{i}"}).status_code == 201
    r = add(tenant_a, aid, {**MCQ, "body": "one too many"})
    assert r.status_code == 409 and "at most 20" in r.json()["error"]["message"]
    for i in range(20):
        assert add(tenant_a, aid, {**MCQ, "sectionIndex": 1, "body": f"S{i} other{i}"}).status_code == 201
    r = add(tenant_a, aid, {**MCQ, "sectionIndex": 2, "body": "forty-first"})
    assert r.status_code == 409 and "at most 40" in r.json()["error"]["message"]


# ── patch / delete ──────────────────────────────────────────────────────────────────────────
def test_patch_changes_only_the_given_fields(tenant_a: Account) -> None:
    aid = make(tenant_a)
    qid = add(tenant_a, aid, MCQ).json()["id"]
    r = tenant_a.client.patch(f"{API}/questions/{qid}", json={"body": "New text?", "correctAnswer": "C"})
    assert r.status_code == 200
    q = r.json()
    assert q["body"] == "New text?" and q["correctAnswer"] == "C" and q["options"] == MCQ["options"]
    assert q["explanation"] == MCQ["explanation"] and q["source"] == "custom"
    q = tenant_a.client.patch(f"{API}/questions/{qid}", json={"options": ["1", "2", "3", "4"]}).json()
    assert q["options"] == ["1", "2", "3", "4"]
    assert tenant_a.client.patch(f"{API}/questions/{qid}", json={"explanation": None}).json()["explanation"] is None


def test_patch_keeps_ai_provenance(tenant_a: Account, app) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    generate_all(tenant_a, app, aid)
    q = tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()[0]
    r = tenant_a.client.patch(f"{API}/questions/{q['id']}", json={"body": "Edited by a human"})
    assert r.json()["source"] == "ai" and r.json()["body"] == "Edited by a human"


@pytest.mark.parametrize(
    "body",
    [{}, {"body": None}, {"body": ""}, {"options": ["a", "b"]}, {"correctAnswer": "Z"}, {"rubric": "no rubric on mcq here"},
     {"wordLimit": 100}, {"maxScore": 99}, {"unknown": 1}],
)  # fmt: skip
def test_invalid_patch_is_400(tenant_a: Account, body: dict[str, Any]) -> None:
    aid = make(tenant_a)
    qid = add(tenant_a, aid, MCQ).json()["id"]
    r = tenant_a.client.patch(f"{API}/questions/{qid}", json=body)
    # unknown fields are ignored by the model, which leaves an empty change set -> still a 400
    assert r.status_code == 400, r.text


def test_descriptive_patch_rules(tenant_a: Account) -> None:
    aid = make(tenant_a)
    qid = add(tenant_a, aid, DESC).json()["id"]
    ok = tenant_a.client.patch(f"{API}/questions/{qid}", json={"rubric": "A better and longer rubric", "maxScore": 12})
    assert ok.status_code == 200 and ok.json()["maxScore"] == 12
    assert tenant_a.client.patch(f"{API}/questions/{qid}", json={"options": ["a", "b", "c", "d"]}).status_code == 400
    assert tenant_a.client.patch(f"{API}/questions/{qid}", json={"correctAnswer": "A"}).status_code == 400


def test_delete_then_gone(tenant_a: Account) -> None:
    aid = make(tenant_a)
    qid = add(tenant_a, aid, MCQ).json()["id"]
    assert tenant_a.client.delete(f"{API}/questions/{qid}").status_code == 204
    assert tenant_a.client.delete(f"{API}/questions/{qid}").status_code == 404
    assert tenant_a.client.patch(f"{API}/questions/{qid}", json={"body": "x"}).status_code == 404
    assert tenant_a.client.get(f"{API}/assessments/{aid}/questions").json() == []


def test_unknown_and_malformed_question_ids(tenant_a: Account) -> None:
    zero = "00000000-0000-4000-8000-000000000000"
    for call in (
        lambda i: tenant_a.client.patch(f"{API}/questions/{i}", json={"body": "x"}),
        lambda i: tenant_a.client.delete(f"{API}/questions/{i}"),
        lambda i: tenant_a.client.post(f"{API}/questions/{i}/regenerate"),
    ):
        assert call(zero).status_code == 404
        assert call("bad").status_code == 400


def test_audit_trail_for_question_changes(tenant_a: Account, repos) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    qid = add(tenant_a, aid, MCQ).json()["id"]
    tenant_a.client.patch(f"{API}/questions/{qid}", json={"body": "again?"})
    tenant_a.client.delete(f"{API}/questions/{qid}")
    actions = [e.action for e in repos.audit.list_by_entity(tenant_a.tenant_id, "question", qid)]
    assert sorted(actions) == ["question.create", "question.delete", "question.update"]


# ── regenerate ──────────────────────────────────────────────────────────────────────────────
def test_regenerate_replaces_content_in_place_keeping_id_and_position(tenant_a: Account, app) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    generate_all(tenant_a, app, aid)
    before = tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()
    target = before[1]
    r = tenant_a.client.post(f"{API}/questions/{target['id']}/regenerate")
    assert r.status_code == 202 and r.json()["status"] == "queued"
    app.state.jobs.drain()
    job = tenant_a.client.get(f"{API}/jobs/{r.json()['jobId']}").json()
    assert job["status"] == "done" and job["result"]["questionId"] == target["id"]
    after = tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()
    assert [q["id"] for q in after] == [q["id"] for q in before]  # same ids, same order
    new = after[1]
    assert new["body"] != target["body"] and new["position"] == target["position"] and new["source"] == "ai"
    assert [q["body"] for q in after if q["id"] != target["id"]] == [
        q["body"] for q in before if q["id"] != target["id"]
    ]


def test_regenerating_a_descriptive_question(tenant_a: Account, app) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    generate_all(tenant_a, app, aid)
    d = next(q for q in tenant_a.client.get(f"{API}/assessments/{aid}/questions").json() if q["type"] == "descriptive")
    tenant_a.client.post(f"{API}/questions/{d['id']}/regenerate")
    app.state.jobs.drain()
    d2 = next(q for q in tenant_a.client.get(f"{API}/assessments/{aid}/questions").json() if q["id"] == d["id"])
    assert d2["body"] != d["body"] and d2["rubric"] and d2["options"] is None


def test_custom_questions_cannot_be_regenerated(tenant_a: Account) -> None:
    aid = make(tenant_a)
    qid = add(tenant_a, aid, MCQ).json()["id"]
    r = tenant_a.client.post(f"{API}/questions/{qid}/regenerate")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


def test_regenerate_needs_a_long_enough_jd_and_counts_toward_the_daily_cap(
    tenant_a: Account, app, repos, settings
) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    generate_all(tenant_a, app, aid)
    qid = tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()[0]["id"]
    repos.assessments.update(tenant_a.tenant_id, aid, job_description="short")
    r = tenant_a.client.post(f"{API}/questions/{qid}/regenerate")
    assert r.status_code == 422 and r.json()["error"]["code"] == "JD_TOO_SHORT"
    repos.assessments.update(tenant_a.tenant_id, aid, job_description=JD)
    for _ in range(settings.DAILY_GENERATION_LIMIT - 1):  # 1 already used by generate_all
        assert tenant_a.client.post(f"{API}/questions/{qid}/regenerate").status_code == 202
    assert tenant_a.client.post(f"{API}/questions/{qid}/regenerate").status_code == 429


def test_regenerate_failure_leaves_the_question_untouched(tenant_a: Account, app) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    generate_all(tenant_a, app, aid)
    before = tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()
    app.state.providers.ai.return_invalid_json = True
    jid = tenant_a.client.post(f"{API}/questions/{before[0]['id']}/regenerate").json()["jobId"]
    app.state.jobs.drain()
    assert tenant_a.client.get(f"{API}/jobs/{jid}").json()["errorCode"] == "AI_OUTPUT_INVALID"
    assert tenant_a.client.get(f"{API}/assessments/{aid}/questions").json() == before


# ── approve ─────────────────────────────────────────────────────────────────────────────────
def test_approve_requires_questions(tenant_a: Account) -> None:
    r = tenant_a.client.post(f"{API}/assessments/{make(tenant_a)}/approve")
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_QUESTIONS"


def test_approve_requires_each_section_to_match_its_configured_count(tenant_a: Account) -> None:
    aid = make(tenant_a)
    add(tenant_a, aid, MCQ)
    r = tenant_a.client.post(f"{API}/assessments/{aid}/approve")
    err = r.json()["error"]
    assert r.status_code == 409 and err["code"] == "SECTION_INCOMPLETE"
    assert {d["path"]: d["message"] for d in err["details"]} == {
        "sections[0]": "has 1 of 2 questions", "sections[1]": "has 0 of 1 questions",
    }  # fmt: skip
    fill_ids = [
        add(tenant_a, aid, {**MCQ, "body": "Second topic2"}).json()["id"],
        add(tenant_a, aid, DESC).json()["id"],
    ]
    add(tenant_a, aid, {**MCQ, "body": "Extra beyond count topic3"})  # 3 of 2
    r = tenant_a.client.post(f"{API}/assessments/{aid}/approve")
    assert r.status_code == 409 and r.json()["error"]["details"][0]["message"] == "has 3 of 2 questions"
    tenant_a.client.delete(f"{API}/questions/{fill_ids[0]}")
    assert tenant_a.client.post(f"{API}/assessments/{aid}/approve").status_code == 200


def test_approve_marks_everything_approved_and_renumbers_positions(tenant_a: Account, repos) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    ids = fill(tenant_a, aid)
    tenant_a.client.delete(f"{API}/questions/{ids[0]}")
    add(tenant_a, aid, {**MCQ, "body": "Replacement topic9"})  # positions are now 1, 2 in section 0 -> gap at 0
    r = tenant_a.client.post(f"{API}/assessments/{aid}/approve")
    assert r.status_code == 200 and r.json() == {"id": aid, "status": "approved", "questionCount": 3}
    qs = tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()
    assert [q["position"] for q in qs] == [1, 2, 3] and {q["status"] for q in qs} == {"approved"}
    assert [q["sectionIndex"] for q in qs] == [0, 0, 1]
    assert tenant_a.client.get(f"{API}/assessments/{aid}").json()["status"] == "approved"
    assert "assessment.approve" in [e.action for e in repos.audit.list_by_entity(tenant_a.tenant_id, "assessment", aid)]


def test_everything_is_frozen_after_approval(tenant_a: Account, app) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    generate_all(tenant_a, app, aid)
    assert tenant_a.client.post(f"{API}/assessments/{aid}/approve").status_code == 200
    qid = tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()[0]["id"]
    calls = [
        tenant_a.client.post(f"{API}/assessments/{aid}/approve"),
        tenant_a.client.post(f"{API}/assessments/{aid}/generate", json={}),
        tenant_a.client.post(f"{API}/assessments/{aid}/questions", json=MCQ),
        tenant_a.client.patch(f"{API}/questions/{qid}", json={"body": "late edit"}),
        tenant_a.client.delete(f"{API}/questions/{qid}"),
        tenant_a.client.post(f"{API}/questions/{qid}/regenerate"),
        tenant_a.client.patch(f"{API}/assessments/{aid}", json={"title": "x"}),
        tenant_a.client.delete(f"{API}/assessments/{aid}"),
    ]
    assert [c.status_code for c in calls] == [409] * 8
    assert tenant_a.client.get(f"{API}/assessments/{aid}/questions").status_code == 200  # reading still works


def test_full_review_flow_generate_edit_replace_approve(tenant_a: Account, app) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    generate_all(tenant_a, app, aid)
    qs = tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()
    tenant_a.client.patch(f"{API}/questions/{qs[0]['id']}", json={"body": "Tweaked wording"})
    tenant_a.client.delete(f"{API}/questions/{qs[1]['id']}")
    assert tenant_a.client.post(f"{API}/assessments/{aid}/approve").status_code == 409  # now 1 of 2
    add(tenant_a, aid, {**MCQ, "body": "My own addition topic77"})
    r = tenant_a.client.post(f"{API}/assessments/{aid}/approve")
    assert r.status_code == 200 and r.json()["questionCount"] == 3
    # the approved assessment can now be closed (Phase 5 rule)
    assert tenant_a.client.post(f"{API}/assessments/{aid}/close").status_code == 200


# ── isolation ───────────────────────────────────────────────────────────────────────────────
def test_other_tenant_gets_404_on_every_question_endpoint(tenant_a: Account, tenant_b: Account, app) -> None:  # type: ignore[no-untyped-def]
    aid = make(tenant_a)
    generate_all(tenant_a, app, aid)
    qid = tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()[0]["id"]
    c = tenant_b.client
    assert [
        c.get(f"{API}/assessments/{aid}/questions").status_code,
        c.post(f"{API}/assessments/{aid}/questions", json=MCQ).status_code,
        c.patch(f"{API}/questions/{qid}", json={"body": "hack"}).status_code,
        c.delete(f"{API}/questions/{qid}").status_code,
        c.post(f"{API}/questions/{qid}/regenerate").status_code,
        c.post(f"{API}/assessments/{aid}/approve").status_code,
    ] == [404] * 6
    still = tenant_a.client.get(f"{API}/assessments/{aid}/questions").json()
    assert len(still) == 3 and all(q["body"] != "hack" for q in still)


def test_recruiter_can_manage_questions(recruiter: Account, tenant_a: Account) -> None:
    aid = make(tenant_a)
    assert add(recruiter, aid, MCQ).status_code == 201
    assert isinstance(FakeAiProvider(), FakeAiProvider)

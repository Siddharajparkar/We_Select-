"""Phase 6 live checks: AI generation jobs, question review and approval (endpoints 15-22).

Locally the server runs the fake AI. Against Azure these checks call the real model, so they only run
with ``--with-ai true`` (a handful of GPT-4o calls, well inside the daily allowance)."""

from __future__ import annotations

import time

JD = " ".join(
    [
        "Senior Backend Engineer. We are hiring an engineer to design, build and operate Python web services on",
        "Azure. You will own REST APIs written with FastAPI, model relational data in SQL Server, write background",
        "jobs, add automated tests, review code, and improve reliability, security and observability of production",
        "systems. Strong communication, mentoring and a habit of measuring results are important. Experience with",
        "containers, continuous delivery pipelines, structured logging and incident response is a clear advantage",
        "for this role and for the team that you will join as an experienced individual contributor.",
        "The team values clear written design documents, small reviewed changes, honest estimates, calm on-call",
        "rotations, careful handling of customer data, and steady improvement of tooling that other engineers use.",
    ]
)
assert len(JD.split()) >= 100  # the API refuses shorter job descriptions
SECTIONS = [
    {"type": "mcq", "domain": "Python", "difficulty": "medium", "count": 3},
    {"type": "descriptive", "domain": "System design", "difficulty": "medium", "count": 1},
]
P = "/api/v1"


def _gate(ctx):  # type: ignore[no-untyped-def]
    if ctx.target != "local" and not ctx.with_ai:
        raise ctx.Skip("real AI is only exercised with --with-ai true")


def _sid(ctx, tag="A"):  # type: ignore[no-untyped-def]
    return ctx.state[tag]["sid"]


def _wait(ctx, jid, timeout=120):  # type: ignore[no-untyped-def]
    deadline = time.time() + timeout
    job = {}
    while time.time() < deadline:
        r = ctx.request("GET", f"{P}/jobs/{jid}", _sid(ctx))
        assert r.status_code == 200, f"job poll: {r.status_code}"
        job = r.json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(1)
    raise AssertionError(f"job {jid} still {job.get('status')} after {timeout}s")


def _new_assessment(ctx, jd=JD):  # type: ignore[no-untyped-def]
    r = ctx.request("POST", f"{P}/assessments", _sid(ctx),
                    json={"title": "P6 E2E", "jobDescription": jd, "durationMinutes": 30, "passingScore": 50,
                          "sections": SECTIONS})  # fmt: skip
    assert r.status_code == 201, f"create: {r.status_code}"
    return r.json()["id"]


def generate_all_sections(ctx):  # type: ignore[no-untyped-def]
    _gate(ctx)
    aid = _new_assessment(ctx)
    ctx.state["p6_assessment"] = aid
    r = ctx.request("POST", f"{P}/assessments/{aid}/generate", _sid(ctx), json={})
    assert r.status_code == 202 and r.json()["status"] == "queued", f"generate: {r.status_code} {r.text[:100]}"
    job = _wait(ctx, r.json()["jobId"])
    assert job["status"] == "done", f"job ended {job['status']}: {job.get('error')}"
    assert job["result"]["questionsCreated"] == 4, f"created: {job['result']}"
    qs = ctx.request("GET", f"{P}/assessments/{aid}/questions", _sid(ctx)).json()
    assert [q["type"] for q in qs] == ["mcq", "mcq", "mcq", "descriptive"], "unexpected question mix"
    assert all(len(q["options"]) == 4 and q["correctAnswer"] in "ABCD" for q in qs[:3])
    assert qs[3]["rubric"] and qs[3]["maxScore"] >= 1


def request_checks_in_order(ctx):  # type: ignore[no-untyped-def]
    _gate(ctx)
    short = _new_assessment(ctx, jd="far too short")
    r = ctx.request("POST", f"{P}/assessments/{short}/generate", _sid(ctx), json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "JD_TOO_SHORT", f"short jd: {r.status_code}"
    aid = ctx.state["p6_assessment"]
    r = ctx.request("POST", f"{P}/assessments/{aid}/generate", _sid(ctx), json={"sectionIndexes": [7]})
    assert r.status_code == 400, f"bad index: {r.status_code}"
    zero = "00000000-0000-4000-8000-000000000000"
    assert ctx.request("POST", f"{P}/assessments/{zero}/generate", _sid(ctx), json={}).status_code == 404


def review_edit_regenerate(ctx):  # type: ignore[no-untyped-def]
    _gate(ctx)
    aid = ctx.state["p6_assessment"]
    qs = ctx.request("GET", f"{P}/assessments/{aid}/questions", _sid(ctx)).json()
    first = qs[0]
    r = ctx.request("PATCH", f"{P}/questions/{first['id']}", _sid(ctx), json={"body": "Edited by a reviewer?"})
    assert r.status_code == 200 and r.json()["body"] == "Edited by a reviewer?"
    second = qs[1]
    rg = ctx.request("POST", f"{P}/questions/{second['id']}/regenerate", _sid(ctx))
    assert rg.status_code == 202, f"regenerate: {rg.status_code}"
    assert _wait(ctx, rg.json()["jobId"])["status"] == "done"
    after = ctx.request("GET", f"{P}/assessments/{aid}/questions", _sid(ctx)).json()
    assert [q["id"] for q in after] == [q["id"] for q in qs], "regenerate must keep ids and order"
    assert after[1]["body"] != second["body"], "regenerated question is unchanged"


def approve_flow_and_freeze(ctx):  # type: ignore[no-untyped-def]
    _gate(ctx)
    aid = ctx.state["p6_assessment"]
    qs = ctx.request("GET", f"{P}/assessments/{aid}/questions", _sid(ctx)).json()
    assert ctx.request("DELETE", f"{P}/questions/{qs[2]['id']}", _sid(ctx)).status_code == 204
    r = ctx.request("POST", f"{P}/assessments/{aid}/approve", _sid(ctx))
    assert r.status_code == 409 and r.json()["error"]["code"] == "SECTION_INCOMPLETE", f"approve short: {r.status_code}"
    custom = {"sectionIndex": 0, "type": "mcq", "body": "Which statement ends a loop early?",
              "options": ["break", "pass", "skip", "stop"], "correctAnswer": "A"}  # fmt: skip
    assert ctx.request("POST", f"{P}/assessments/{aid}/questions", _sid(ctx), json=custom).status_code == 201
    ok = ctx.request("POST", f"{P}/assessments/{aid}/approve", _sid(ctx))
    assert ok.status_code == 200 and ok.json()["questionCount"] == 4, f"approve: {ok.status_code} {ok.text[:100]}"
    qid = ctx.request("GET", f"{P}/assessments/{aid}/questions", _sid(ctx)).json()[0]["id"]
    assert ctx.request("PATCH", f"{P}/questions/{qid}", _sid(ctx), json={"body": "late"}).status_code == 409
    assert ctx.request("POST", f"{P}/assessments/{aid}/generate", _sid(ctx), json={}).status_code == 409


def other_tenant_gets_404(ctx):  # type: ignore[no-untyped-def]
    _gate(ctx)
    aid = ctx.state["p6_assessment"]
    qid = ctx.request("GET", f"{P}/assessments/{aid}/questions", _sid(ctx)).json()[0]["id"]
    b = _sid(ctx, "B")
    for method, path in [
        ("GET", f"/assessments/{aid}/questions"), ("POST", f"/assessments/{aid}/generate"),
        ("POST", f"/assessments/{aid}/approve"), ("PATCH", f"/questions/{qid}"), ("DELETE", f"/questions/{qid}"),
        ("POST", f"/questions/{qid}/regenerate"),
    ]:  # fmt: skip
        kw = {"json": {"body": "x"}} if method in ("PATCH", "POST") else {}
        r = ctx.request(method, f"{P}{path}", b, **kw)
        assert r.status_code == 404, f"{method} {path}: {r.status_code}"


CHECKS = [generate_all_sections, request_checks_in_order, review_edit_regenerate, approve_flow_and_freeze,
          other_tenant_gets_404]  # fmt: skip

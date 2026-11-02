"""Phase 2: repository contract suite.

Runs on the in-memory backend (SQLite with enforced FKs/uniques/checks) always, and on a real
SQL Server too when TEST_DATABASE_URL is set (CI tier T2) - see the ``repos`` fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.ids import new_id
from app.repositories import Repositories
from app.repositories.models import RepositoryError


# ── Tenants / users / isolation ────────────────────────────────────────────────────────────
def test_tenant_roundtrip_and_list(repos: Repositories) -> None:
    a = repos.tenants.create(name="Alpha")
    b = repos.tenants.create(name="Beta")
    assert repos.tenants.find_by_id(a.id).name == "Alpha"  # type: ignore[union-attr]
    assert repos.tenants.find_by_id(new_id()) is None
    assert {t.name for t in repos.tenants.list()} == {"Alpha", "Beta"}
    assert a.status == "active" and b.id != a.id


def test_users_are_isolated_between_tenants(repos: Repositories) -> None:
    a, b = repos.tenants.create(name="A"), repos.tenants.create(name="B")
    alice = repos.users.create(a.id, name="Alice", email="alice@alpha.com", password_hash="h", role="admin")
    assert repos.users.find_by_id(a.id, alice.id).email == "alice@alpha.com"  # type: ignore[union-attr]
    assert repos.users.find_by_id(b.id, alice.id) is None
    assert repos.users.list(b.id) == []
    assert repos.users.update(b.id, alice.id, name="Hacked") is None
    assert repos.users.find_by_id(a.id, alice.id).name == "Alice"  # type: ignore[union-attr]


def test_user_update_allows_only_name_role_status(repos: Repositories) -> None:
    t = repos.tenants.create(name="A")
    u = repos.users.create(t.id, name="U", email="u@a.com", password_hash="h", role="reviewer")
    upd = repos.users.update(
        t.id, u.id, name="New", role="recruiter", status="disabled", email="evil@x.com", password_hash="z"
    )
    assert (upd.name, upd.role, upd.status, upd.email, upd.password_hash) == (
        "New",
        "recruiter",
        "disabled",
        "u@a.com",
        "h",
    )  # type: ignore[union-attr]


def test_email_is_globally_unique_across_tenants_case_insensitively_R1(repos: Repositories) -> None:
    a, b = repos.tenants.create(name="A"), repos.tenants.create(name="B")
    repos.users.create(a.id, name="Alice", email="Shared@Example.com", password_hash="h", role="recruiter")
    with pytest.raises(RepositoryError, match="EMAIL_EXISTS"):
        repos.users.create(b.id, name="Bob", email="shared@example.COM", password_hash="h", role="reviewer")
    assert repos.users.find_by_email(" SHARED@example.com ").name == "Alice"  # type: ignore[union-attr]
    assert repos.users.find_by_email("nobody@example.com") is None


def test_user_enums_are_enforced_by_the_database(repos: Repositories) -> None:
    t = repos.tenants.create(name="A")
    with pytest.raises(RepositoryError, match="CONSTRAINT_VIOLATION"):
        repos.users.create(t.id, name="X", email="x@a.com", password_hash="h", role="superuser")


def test_user_for_missing_tenant_violates_fk(repos: Repositories) -> None:
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        repos.users.create(new_id(), name="X", email="x@a.com", password_hash="h", role="admin")


# ── Tenant id guard on every tenant-scoped function ────────────────────────────────────────
BAD_TENANTS = ["", "   ", "not-a-uuid", None, 123]


@pytest.mark.parametrize("bad", BAD_TENANTS)
def test_every_tenant_scoped_function_rejects_missing_or_malformed_tenant_id(repos: Repositories, bad: object) -> None:
    i = new_id()
    now = datetime.now(UTC)
    calls = [
        lambda: repos.users.create(bad, name="n", email="e@x.com", password_hash="h", role="admin"),  # type: ignore[arg-type]
        lambda: repos.users.find_by_id(bad, i),  # type: ignore[arg-type]
        lambda: repos.users.list(bad),  # type: ignore[arg-type]
        lambda: repos.users.update(bad, i, name="x"),  # type: ignore[arg-type]
        lambda: repos.sessions.create(bad, user_id=i, token_hash="t", expires_at=now),  # type: ignore[arg-type]
        lambda: repos.sessions.delete_by_user_id(bad, i),  # type: ignore[arg-type]
        lambda: repos.assessments.create(bad, title="t", sections=[], created_by=i),  # type: ignore[arg-type]
        lambda: repos.assessments.find_by_id(bad, i),  # type: ignore[arg-type]
        lambda: repos.assessments.list(bad),  # type: ignore[arg-type]
        lambda: repos.assessments.update(bad, i, title="x"),  # type: ignore[arg-type]
        lambda: repos.assessments.delete(bad, i),  # type: ignore[arg-type]
        lambda: repos.questions.create(bad, assessment_id=i, type="mcq", body="b"),  # type: ignore[arg-type]
        lambda: repos.questions.create_many(bad, []),  # type: ignore[arg-type]
        lambda: repos.questions.find_by_id(bad, i),  # type: ignore[arg-type]
        lambda: repos.questions.list_by_assessment(bad, i),  # type: ignore[arg-type]
        lambda: repos.questions.update(bad, i, body="x"),  # type: ignore[arg-type]
        lambda: repos.questions.delete(bad, i),  # type: ignore[arg-type]
        lambda: repos.questions.delete_by_assessment_and_source(bad, i, 0, "ai"),  # type: ignore[arg-type]
        lambda: repos.participants.create_many(bad, i, []),  # type: ignore[arg-type]
        lambda: repos.participants.list_by_assessment(bad, i),  # type: ignore[arg-type]
        lambda: repos.participants.find_by_id(bad, i),  # type: ignore[arg-type]
        lambda: repos.participants.update_token(bad, i, None, None),  # type: ignore[arg-type]
        lambda: repos.participants.update_invite_status(bad, i, "sent"),  # type: ignore[arg-type]
        lambda: repos.participants.delete(bad, i),  # type: ignore[arg-type]
        lambda: repos.attempts.create(bad, participant_id=i, assessment_id=i, attempt_token_hash="h", deadline_at=now),  # type: ignore[arg-type]
        lambda: repos.attempts.find_by_id(bad, i),  # type: ignore[arg-type]
        lambda: repos.attempts.find_by_participant_id(bad, i),  # type: ignore[arg-type]
        lambda: repos.attempts.update_status(bad, i, "submitted"),  # type: ignore[arg-type]
        lambda: repos.attempts.update_scores(bad, i, score=1, max_score=2, percent=50, passed=True),  # type: ignore[arg-type]
        lambda: repos.attempts.list_by_assessment(bad, i),  # type: ignore[arg-type]
        lambda: repos.responses.upsert(bad, attempt_id=i, question_id=i, answer_text="a"),  # type: ignore[arg-type]
        lambda: repos.responses.list_by_attempt(bad, i),  # type: ignore[arg-type]
        lambda: repos.scores.upsert(bad, attempt_id=i, question_id=i, score=1, max_score=1, source="auto"),  # type: ignore[arg-type]
        lambda: repos.scores.list_by_attempt(bad, i),  # type: ignore[arg-type]
        lambda: repos.jobs.enqueue(bad, type="generate", ref_id=i, payload={}),  # type: ignore[arg-type]
        lambda: repos.jobs.find_by_id(bad, i),  # type: ignore[arg-type]
        lambda: repos.jobs.count_daily_generations(bad, now),  # type: ignore[arg-type]
        lambda: repos.audit.log(bad, action="a", entity_type="e", entity_id=i),  # type: ignore[arg-type]
        lambda: repos.audit.list_by_entity(bad, "e", i),  # type: ignore[arg-type]
    ]
    for call in calls:
        with pytest.raises(ValueError, match="tenantId required"):
            call()


# ── Sessions ───────────────────────────────────────────────────────────────────────────────
def test_sessions_resolve_by_hash_across_tenants_and_delete(repos: Repositories, clock) -> None:  # type: ignore[no-untyped-def]
    t = repos.tenants.create(name="Session Corp")
    u = repos.users.create(t.id, name="Dev", email="dev@session.com", password_hash="h", role="admin")
    s = repos.sessions.create(
        t.id, user_id=u.id, token_hash="token-hash-123456789", expires_at=clock.now() + timedelta(days=1)
    )
    assert s.user_id == u.id
    got = repos.system.find_session_by_token_hash("token-hash-123456789")
    assert got is not None and got["user"].id == u.id and got["tenant"].id == t.id
    assert repos.sessions.delete_by_token_hash("token-hash-123456789") is True
    assert repos.sessions.delete_by_token_hash("token-hash-123456789") is False
    assert repos.system.find_session_by_token_hash("token-hash-123456789") is None


def test_session_token_hash_must_be_unique_and_user_must_belong_to_tenant(repos: Repositories, clock) -> None:  # type: ignore[no-untyped-def]
    a, b = repos.tenants.create(name="A"), repos.tenants.create(name="B")
    ua = repos.users.create(a.id, name="A", email="a@a.com", password_hash="h", role="admin")
    exp = clock.now() + timedelta(hours=1)
    repos.sessions.create(a.id, user_id=ua.id, token_hash="dup", expires_at=exp)
    with pytest.raises(RepositoryError, match="Duplicate tokenHash"):
        repos.sessions.create(a.id, user_id=ua.id, token_hash="dup", expires_at=exp)
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        repos.sessions.create(b.id, user_id=ua.id, token_hash="other", expires_at=exp)  # user is tenant A's


def test_delete_sessions_by_user_is_tenant_scoped(repos: Repositories, clock) -> None:  # type: ignore[no-untyped-def]
    a, b = repos.tenants.create(name="A"), repos.tenants.create(name="B")
    ua = repos.users.create(a.id, name="A", email="a@a.com", password_hash="h", role="admin")
    exp = clock.now() + timedelta(hours=1)
    for i in range(3):
        repos.sessions.create(a.id, user_id=ua.id, token_hash=f"h{i}", expires_at=exp)
    assert repos.sessions.delete_by_user_id(b.id, ua.id) == 0
    assert repos.sessions.delete_by_user_id(a.id, ua.id) == 3


# ── Login attempts ─────────────────────────────────────────────────────────────────────────
def test_login_attempt_failure_counting_window(repos: Repositories, clock) -> None:  # type: ignore[no-untyped-def]
    start = clock.now()
    repos.login_attempts.record(email="X@Example.com", ip_address="1.2.3.4", success=False)
    clock.advance_minutes(5)
    repos.login_attempts.record(email="x@example.com", ip_address="1.2.3.4", success=False)
    repos.login_attempts.record(email="x@example.com", ip_address="1.2.3.4", success=True)
    assert repos.login_attempts.count_recent_failures("x@example.com", start) == 2
    assert repos.login_attempts.count_recent_failures("x@example.com", start + timedelta(minutes=1)) == 1
    assert repos.login_attempts.count_recent_failures("other@example.com", start) == 0


# ── Assessments & questions: composite tenant integrity ────────────────────────────────────
def test_assessment_roundtrip_json_sections_and_list_counts(world) -> None:  # type: ignore[no-untyped-def]
    r, t = world.repos, world.tenant
    a = r.assessments.find_by_id(t.id, world.assessment.id)
    assert a.sections == [{"type": "mcq", "domain": "Python", "difficulty": "easy", "count": 2}]
    assert (a.duration_minutes, a.passing_score, a.status) == (60, 60, "draft")
    items = r.assessments.list(t.id)
    assert len(items) == 1 and items[0].participant_count == 1 and items[0].submitted_count == 0
    assert r.assessments.list(t.id, status="open") == []


def test_assessment_update_and_check_constraints(world) -> None:  # type: ignore[no-untyped-def]
    r, t, a = world.repos, world.tenant, world.assessment
    upd = r.assessments.update(
        t.id, a.id, title="New", status="approved", passing_score=75, sections=[{"type": "mcq", "count": 5}]
    )
    assert (upd.title, upd.status, upd.passing_score, upd.sections) == (
        "New",
        "approved",
        75,
        [{"type": "mcq", "count": 5}],
    )
    for bad in ({"duration_minutes": 1}, {"duration_minutes": 241}, {"passing_score": 101}, {"status": "weird"}):
        with pytest.raises(RepositoryError, match="CONSTRAINT_VIOLATION"):
            r.assessments.update(t.id, a.id, **bad)


def test_assessments_are_invisible_and_immutable_to_other_tenants(world) -> None:  # type: ignore[no-untyped-def]
    r, a = world.repos, world.assessment
    other = r.tenants.create(name="Other")
    assert r.assessments.find_by_id(other.id, a.id) is None
    assert r.assessments.list(other.id) == []
    assert r.assessments.update(other.id, a.id, title="Hacked") is None
    assert r.assessments.delete(other.id, a.id) is False
    assert r.assessments.find_by_id(world.tenant.id, a.id).title == "Backend Engineer"


def test_assessment_creator_must_belong_to_the_same_tenant(world) -> None:  # type: ignore[no-untyped-def]
    r = world.repos
    other = r.tenants.create(name="Other")
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        r.assessments.create(other.id, title="x", sections=[], created_by=world.user.id)


def test_question_cannot_point_at_another_tenants_assessment(world) -> None:  # type: ignore[no-untyped-def]
    r = world.repos
    other = r.tenants.create(name="Other")
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        r.questions.create(other.id, assessment_id=world.assessment.id, type="mcq", body="Hacked", source="custom")


def test_question_roundtrip_update_and_isolation(world) -> None:  # type: ignore[no-untyped-def]
    r, t, q = world.repos, world.tenant, world.question
    got = r.questions.find_by_id(t.id, q.id)
    assert got.options == ["A", "B", "C", "D"] and got.max_score == 5 and got.source == "custom"
    upd = r.questions.update(t.id, q.id, body="New body", options=["1", "2"], max_score=8, position=3)
    assert (upd.body, upd.options, upd.max_score, upd.position) == ("New body", ["1", "2"], 8, 3)
    other = r.tenants.create(name="Other")
    assert r.questions.find_by_id(other.id, q.id) is None
    assert r.questions.update(other.id, q.id, body="x") is None
    assert r.questions.delete(other.id, q.id) is False
    assert r.questions.list_by_assessment(other.id, world.assessment.id) == []


def test_question_checks_and_ordering(world) -> None:  # type: ignore[no-untyped-def]
    r, t, a = world.repos, world.tenant, world.assessment
    with pytest.raises(RepositoryError):
        r.questions.create(t.id, assessment_id=a.id, type="mcq", body="b", max_score=21)
    with pytest.raises(RepositoryError):
        r.questions.create(t.id, assessment_id=a.id, type="essay", body="b")
    r.questions.create_many(t.id, [
        {"assessment_id": a.id, "type": "descriptive", "body": "s1p2", "section_index": 1, "position": 2},
        {"assessment_id": a.id, "type": "descriptive", "body": "s1p1", "section_index": 1, "position": 1},
        {"assessment_id": a.id, "type": "mcq", "body": "s0p0", "section_index": 0, "position": 0, "source": "ai"},
    ])  # fmt: skip
    bodies = [q.body for q in r.questions.list_by_assessment(t.id, a.id)]
    # ordered by (section_index, position): the pre-existing section-0 question (position 0) comes first,
    # then s0p0 (also section 0, position 0), then section 1 by position.
    assert bodies.index("s0p0") < bodies.index("s1p1") < bodies.index("s1p2")
    assert bodies.index("What is a closure?") < bodies.index("s1p1")


def test_delete_questions_by_section_and_source_only_removes_ai(world) -> None:  # type: ignore[no-untyped-def]
    r, t, a = world.repos, world.tenant, world.assessment
    r.questions.create_many(t.id, [
        {"assessment_id": a.id, "type": "mcq", "body": "ai1", "section_index": 0, "source": "ai"},
        {"assessment_id": a.id, "type": "mcq", "body": "ai2", "section_index": 0, "source": "ai"},
        {"assessment_id": a.id, "type": "mcq", "body": "ai-other-section", "section_index": 1, "source": "ai"},
    ])  # fmt: skip
    assert r.questions.delete_by_assessment_and_source(t.id, a.id, 0, "ai") == 2
    remaining = {q.body for q in r.questions.list_by_assessment(t.id, a.id)}
    assert remaining == {"What is a closure?", "ai-other-section"}  # custom + other section untouched


def test_deleting_an_assessment_cascades_to_questions_and_participants(world) -> None:  # type: ignore[no-untyped-def]
    r, t, a = world.repos, world.tenant, world.assessment
    assert r.assessments.delete(t.id, a.id) is True
    assert r.questions.list_by_assessment(t.id, a.id) == []
    assert r.participants.list_by_assessment(t.id, a.id) == []


# ── Participants & filtered unique index ───────────────────────────────────────────────────
def test_participants_bulk_create_reports_duplicates_and_invalid(world) -> None:  # type: ignore[no-untyped-def]
    r, t, a = world.repos, world.tenant, world.assessment
    added, dupes, invalid = r.participants.create_many(t.id, a.id, [
        {"name": "John", "email": "John@Example.com"},
        {"name": "Jane", "email": "jane@example.com"},
        {"name": "Dup John", "email": "john@example.com"},
        {"name": "Existing", "email": "cand1@example.com"},
        {"name": "Bad", "email": "not-an-email"},
        {"name": "", "email": "noname@example.com"},
    ])  # fmt: skip
    assert [p.email for p in added] == ["john@example.com", "jane@example.com"]
    assert sorted(dupes) == ["cand1@example.com", "john@example.com"]
    assert len(invalid) == 2
    assert all(p.token_hash is None and p.invite_status == "none" for p in added)


def test_participants_for_unknown_or_foreign_assessment_fail_fk(world) -> None:  # type: ignore[no-untyped-def]
    r = world.repos
    other = r.tenants.create(name="Other")
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        r.participants.create_many(other.id, world.assessment.id, [{"name": "X", "email": "x@x.com"}])


def test_same_email_allowed_in_different_assessments(world) -> None:  # type: ignore[no-untyped-def]
    r, t = world.repos, world.tenant
    a2 = r.assessments.create(t.id, title="Second", sections=[], created_by=world.user.id)
    added, dupes, _ = r.participants.create_many(t.id, a2.id, [{"name": "Cand One", "email": "cand1@example.com"}])
    assert len(added) == 1 and dupes == []


def test_filtered_unique_token_index_allows_many_nulls_but_no_duplicate_tokens(world) -> None:  # type: ignore[no-untyped-def]
    r, t, a = world.repos, world.tenant, world.assessment
    added, _, _ = r.participants.create_many(
        t.id, a.id, [{"name": "P2", "email": "p2@example.com"}, {"name": "P3", "email": "p3@example.com"}]
    )
    p1, p2 = world.participant, added[0]
    r.participants.update_token(t.id, p1.id, "hash-unique-1", datetime(2026, 12, 1, tzinfo=UTC))
    with pytest.raises(RepositoryError, match="Duplicate tokenHash"):
        r.participants.update_token(t.id, p2.id, "hash-unique-1", datetime(2026, 12, 1, tzinfo=UTC))
    r.participants.update_token(t.id, p1.id, None, None)
    assert r.participants.find_by_id(t.id, p1.id).token_hash is None  # type: ignore[union-attr]
    r.participants.update_token(t.id, p2.id, "hash-unique-1", None)  # free again after clearing
    got = r.system.find_participant_by_token_hash("hash-unique-1")
    assert got["participant"].id == p2.id and got["assessment"].id == a.id and got["tenant"].id == t.id  # type: ignore[index]
    assert r.system.find_participant_by_token_hash("missing") is None


def test_participant_invite_status_flow_and_isolation(world) -> None:  # type: ignore[no-untyped-def]
    r, t, p = world.repos, world.tenant, world.participant
    when = datetime(2026, 11, 2, tzinfo=UTC)
    r.participants.update_invite_status(t.id, p.id, "sent", when)
    got = r.participants.find_by_id(t.id, p.id)
    assert got.invite_status == "sent" and got.invited_at == when
    other = r.tenants.create(name="Other")
    r.participants.update_invite_status(other.id, p.id, "failed")
    assert r.participants.find_by_id(t.id, p.id).invite_status == "sent"
    assert r.participants.find_by_id(other.id, p.id) is None
    assert r.participants.delete(other.id, p.id) is False
    with pytest.raises(RepositoryError):
        r.participants.update_invite_status(t.id, p.id, "bogus")


# ── Attempts, responses and the deadline rule ──────────────────────────────────────────────
def make_attempt(world, clock, minutes: int = 30, token: str = "aid-token-hash-xyz"):  # type: ignore[no-untyped-def]
    deadline = clock.now() + timedelta(minutes=minutes)
    att = world.repos.attempts.create(
        world.tenant.id, participant_id=world.participant.id, assessment_id=world.assessment.id,
        attempt_token_hash=token, deadline_at=deadline,
    )  # fmt: skip
    return att, deadline


def test_response_upsert_respects_15s_grace_with_fake_clock(world, clock) -> None:  # type: ignore[no-untyped-def]
    r, t = world.repos, world.tenant
    att, deadline = make_attempt(world, clock)
    clock.set_time(deadline + timedelta(seconds=14))
    saved = r.responses.upsert(t.id, attempt_id=att.id, question_id=world.question.id, answer_text="Draft 1")
    assert saved == clock.now()
    clock.set_time(deadline + timedelta(seconds=16))
    with pytest.raises(RepositoryError, match="ATTEMPT_CLOSED"):
        r.responses.upsert(t.id, attempt_id=att.id, question_id=world.question.id, answer_text="Too late")
    assert r.responses.list_by_attempt(t.id, att.id)[0].answer_text == "Draft 1"


def test_response_upsert_is_idempotent_last_write_wins(world, clock) -> None:  # type: ignore[no-untyped-def]
    r, t = world.repos, world.tenant
    att, _ = make_attempt(world, clock)
    for text in ("one", "two", "three"):
        clock.advance_seconds(1)
        r.responses.upsert(t.id, attempt_id=att.id, question_id=world.question.id, answer_text=text)
    rows = r.responses.list_by_attempt(t.id, att.id)
    assert len(rows) == 1 and rows[0].answer_text == "three"


def test_response_for_unknown_attempt_or_question_violates_fk(world, clock) -> None:  # type: ignore[no-untyped-def]
    r, t = world.repos, world.tenant
    att, _ = make_attempt(world, clock)
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        r.responses.upsert(t.id, attempt_id=new_id(), question_id=world.question.id, answer_text="x")
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        r.responses.upsert(t.id, attempt_id=att.id, question_id=new_id(), answer_text="x")


def test_responses_are_tenant_isolated(world, clock) -> None:  # type: ignore[no-untyped-def]
    r, t = world.repos, world.tenant
    att, _ = make_attempt(world, clock)
    r.responses.upsert(t.id, attempt_id=att.id, question_id=world.question.id, answer_text="mine")
    other = r.tenants.create(name="Other")
    assert r.responses.list_by_attempt(other.id, att.id) == []
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        r.responses.upsert(other.id, attempt_id=att.id, question_id=world.question.id, answer_text="steal")


def test_only_one_attempt_per_participant(world, clock) -> None:  # type: ignore[no-untyped-def]
    r, t = world.repos, world.tenant
    make_attempt(world, clock)
    with pytest.raises(RepositoryError, match="attempt already exists for participant"):
        r.attempts.create(t.id, participant_id=world.participant.id, assessment_id=world.assessment.id,
                          attempt_token_hash="aid-hash-2", deadline_at=clock.now() + timedelta(hours=1))  # fmt: skip


def test_attempt_token_hash_is_unique_across_participants(world, clock) -> None:  # type: ignore[no-untyped-def]
    r, t = world.repos, world.tenant
    make_attempt(world, clock, token="same-hash")
    added, _, _ = r.participants.create_many(t.id, world.assessment.id, [{"name": "P2", "email": "p2@example.com"}])
    with pytest.raises(RepositoryError, match="Duplicate tokenHash"):
        r.attempts.create(t.id, participant_id=added[0].id, assessment_id=world.assessment.id,
                          attempt_token_hash="same-hash", deadline_at=clock.now() + timedelta(hours=1))  # fmt: skip


def test_attempt_cannot_reference_foreign_participant(world, clock) -> None:  # type: ignore[no-untyped-def]
    r = world.repos
    other = r.tenants.create(name="Other")
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        r.attempts.create(other.id, participant_id=world.participant.id, assessment_id=world.assessment.id,
                          attempt_token_hash="x", deadline_at=clock.now() + timedelta(hours=1))  # fmt: skip


def test_attempt_status_scores_and_lookups(world, clock) -> None:  # type: ignore[no-untyped-def]
    r, t = world.repos, world.tenant
    att, deadline = make_attempt(world, clock)
    assert (att.status, att.score, att.passed) == ("in_progress", None, None)
    assert r.attempts.find_by_participant_id(t.id, world.participant.id).id == att.id  # type: ignore[union-attr]
    submitted_at = clock.now() + timedelta(minutes=10)
    sub = r.attempts.update_status(t.id, att.id, "submitted", submitted_at)
    assert sub.status == "submitted" and sub.submitted_at == submitted_at
    scored = r.attempts.update_scores(t.id, att.id, score=7.5, max_score=10, percent=75, passed=True, status="scored")
    assert (scored.score, scored.max_score, scored.percent, scored.passed, scored.status) == (
        7.5,
        10.0,
        75.0,
        True,
        "scored",
    )
    other = r.tenants.create(name="Other")
    assert r.attempts.update_status(other.id, att.id, "submitted") is None
    assert r.attempts.find_by_id(other.id, att.id) is None
    got = r.system.find_attempt_by_token_hash("aid-token-hash-xyz")
    assert got["attempt"].id == att.id and got["participant"].id == world.participant.id  # type: ignore[index]
    assert got["tenant"].id == t.id and got["assessment"].id == world.assessment.id  # type: ignore[index]
    assert r.system.find_attempt_by_token_hash("nope") is None


def test_attempt_listing_sorts_by_score_then_name_and_reports_time_taken(world, clock) -> None:  # type: ignore[no-untyped-def]
    r, t, a = world.repos, world.tenant, world.assessment
    added, _, _ = r.participants.create_many(
        t.id, a.id, [{"name": "Zed", "email": "zed@x.com"}, {"name": "Amy", "email": "amy@x.com"}]
    )
    plan = [(world.participant, 50.0), (added[0], 90.0), (added[1], None)]
    for i, (p, pct) in enumerate(plan):
        att = r.attempts.create(
            t.id,
            participant_id=p.id,
            assessment_id=a.id,
            attempt_token_hash=f"h{i}",
            deadline_at=clock.now() + timedelta(hours=1),
        )
        if pct is not None:
            r.attempts.update_status(t.id, att.id, "submitted", clock.now() + timedelta(seconds=120))
            r.attempts.update_scores(
                t.id, att.id, score=pct, max_score=100, percent=pct, passed=pct >= 60, status="scored"
            )
    by_score = r.attempts.list_by_assessment(t.id, a.id, sort="score")
    assert [x.name for x in by_score] == ["Zed", "Cand One", "Amy"]  # 90, 50, then unscored last
    assert by_score[0].time_taken_sec == 120 and by_score[2].time_taken_sec is None and by_score[2].percent is None
    assert [x.name for x in r.attempts.list_by_assessment(t.id, a.id, sort="name")] == ["Amy", "Cand One", "Zed"]
    assert r.attempts.list_by_assessment(r.tenants.create(name="O").id, a.id) == []
    listing = {p.email: p for p in r.participants.list_by_assessment(t.id, a.id)}
    assert listing["amy@x.com"].attempt_status == "in_progress" and listing["zed@x.com"].percent == 90.0
    assert r.assessments.list(t.id)[0].submitted_count == 2


def test_find_expired_attempts_uses_deadline_plus_15s_across_tenants(world, clock) -> None:  # type: ignore[no-untyped-def]
    r = world.repos
    att, deadline = make_attempt(world, clock)
    assert r.system.find_expired_attempts(deadline + timedelta(seconds=14)) == []
    expired = r.system.find_expired_attempts(deadline + timedelta(seconds=16))
    assert [e.id for e in expired] == [att.id] and expired[0].tenant_id == world.tenant.id
    r.attempts.update_status(world.tenant.id, att.id, "submitted", deadline)
    assert r.system.find_expired_attempts(deadline + timedelta(hours=1)) == []  # only in_progress counts


# ── Scores ─────────────────────────────────────────────────────────────────────────────────
def test_scores_upsert_is_idempotent_and_validated(world, clock) -> None:  # type: ignore[no-untyped-def]
    r, t = world.repos, world.tenant
    att, _ = make_attempt(world, clock)
    s1 = r.scores.upsert(
        t.id, attempt_id=att.id, question_id=world.question.id, score=2, max_score=5, source="ai", justification="ok"
    )
    s2 = r.scores.upsert(
        t.id, attempt_id=att.id, question_id=world.question.id, score=4.5, max_score=5, source="manual"
    )
    assert s1.id == s2.id and (s2.score, s2.source, s2.justification) == (4.5, "manual", None)
    assert len(r.scores.list_by_attempt(t.id, att.id)) == 1
    with pytest.raises(RepositoryError):
        r.scores.upsert(t.id, attempt_id=att.id, question_id=world.question.id, score=1, max_score=5, source="robot")
    other = r.tenants.create(name="O")
    assert r.scores.list_by_attempt(other.id, att.id) == []


# ── Jobs ───────────────────────────────────────────────────────────────────────────────────
def test_jobs_claim_oldest_first_complete_and_daily_count(repos: Repositories, clock) -> None:  # type: ignore[no-untyped-def]
    t = repos.tenants.create(name="Jobs Corp")
    j1 = repos.jobs.enqueue(t.id, type="generate", ref_id=new_id(), payload={"sectionIndexes": [0]})
    clock.advance_seconds(1)
    j2 = repos.jobs.enqueue(t.id, type="email", ref_id=new_id(), payload={"participantId": "p1"})
    assert j1.status == "queued" and j1.payload == {"sectionIndexes": [0]} and j1.max_attempts == 3
    claimed = repos.jobs.claim_next("worker-1")
    assert claimed.id == j1.id and claimed.status == "running" and claimed.attempts == 1  # type: ignore[union-attr]
    assert claimed.locked_by == "worker-1" and claimed.locked_at == clock.now()  # type: ignore[union-attr]
    second = repos.system.claim_next_job("worker-2")
    assert second.id == j2.id  # type: ignore[union-attr]
    assert repos.jobs.claim_next("worker-3") is None
    repos.jobs.complete(j1.id, {"questionsGenerated": 5})
    done = repos.jobs.find_by_id(t.id, j1.id)
    assert done.status == "done" and done.result == {"questionsGenerated": 5} and done.locked_by is None  # type: ignore[union-attr]
    assert repos.jobs.count_daily_generations(t.id, clock.now()) == 1
    assert repos.jobs.count_daily_generations(t.id, clock.now() + timedelta(days=1)) == 0


def test_job_failure_requeues_until_max_attempts_then_fails(repos: Repositories) -> None:
    t = repos.tenants.create(name="Retry Corp")
    job = repos.jobs.enqueue(t.id, type="mark", ref_id=new_id(), payload={}, max_attempts=2)
    for expected in ("queued", "failed"):
        claimed = repos.jobs.claim_next("w")
        assert claimed.id == job.id  # type: ignore[union-attr]
        repos.jobs.fail(job.id, "AI timeout")
        got = repos.jobs.find_by_id(t.id, job.id)
        assert got.status == expected and got.error == "AI timeout"  # type: ignore[union-attr]
    assert repos.jobs.claim_next("w") is None


def test_jobs_are_tenant_isolated_but_claimable_globally(repos: Repositories) -> None:
    a, b = repos.tenants.create(name="A"), repos.tenants.create(name="B")
    ja = repos.jobs.enqueue(a.id, type="generate", ref_id=new_id(), payload={})
    assert repos.jobs.find_by_id(b.id, ja.id) is None
    assert repos.system.claim_next_job("w").tenant_id == a.id  # type: ignore[union-attr]


def test_job_checks_and_fk(repos: Repositories) -> None:
    t = repos.tenants.create(name="A")
    with pytest.raises(RepositoryError):
        repos.jobs.enqueue(t.id, type="bogus", ref_id=new_id(), payload={})
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        repos.jobs.enqueue(new_id(), type="generate", ref_id=new_id(), payload={})


# ── Audit ──────────────────────────────────────────────────────────────────────────────────
def test_audit_log_is_append_only_and_scoped(world, clock) -> None:  # type: ignore[no-untyped-def]
    r, t, a = world.repos, world.tenant, world.assessment
    r.audit.log(
        t.id,
        action="assessment.approved",
        entity_type="assessment",
        entity_id=a.id,
        actor_id=world.user.id,
        details={"why": "ok"},
    )
    clock.advance_seconds(1)  # ordering is by created_at (ms precision in the DB)
    r.audit.log(t.id, action="assessment.opened", entity_type="assessment", entity_id=a.id)
    entries = r.audit.list_by_entity(t.id, "assessment", a.id)
    assert [e.action for e in entries] == ["assessment.approved", "assessment.opened"]
    assert entries[0].details == {"why": "ok"} and entries[1].actor_id is None
    other = r.tenants.create(name="O")
    assert r.audit.list_by_entity(other.id, "assessment", a.id) == []
    with pytest.raises(RepositoryError, match="Foreign key constraint failed"):
        r.audit.log(new_id(), action="x", entity_type="e", entity_id=a.id)


# ── Transactions ───────────────────────────────────────────────────────────────────────────
def test_transaction_commits_on_success(repos: Repositories) -> None:
    t = repos.tenants.create(name="Tx")

    def work(tx: Repositories) -> str:
        return tx.users.create(t.id, name="U", email="u@tx.com", password_hash="h", role="admin").id

    uid = repos.with_transaction(work)
    assert repos.users.find_by_id(t.id, uid) is not None


def test_transaction_rolls_back_everything_on_error(repos: Repositories) -> None:
    t = repos.tenants.create(name="Tx Corp")

    def work(tx: Repositories) -> None:
        tx.users.create(t.id, name="Temp", email="temp@tx.com", password_hash="h", role="recruiter")
        tx.audit.log(t.id, action="x", entity_type="user", entity_id=new_id())
        raise RuntimeError("Simulated Transaction Failure")

    with pytest.raises(RuntimeError, match="Simulated"):
        repos.with_transaction(work)
    assert repos.users.list(t.id) == []


def test_transaction_rolls_back_when_a_constraint_fails_midway(repos: Repositories) -> None:
    t = repos.tenants.create(name="Tx2")
    repos.users.create(t.id, name="Existing", email="dup@tx.com", password_hash="h", role="admin")

    def work(tx: Repositories) -> None:
        tx.users.create(t.id, name="New", email="new@tx.com", password_hash="h", role="admin")
        tx.users.create(t.id, name="Dup", email="dup@tx.com", password_hash="h", role="admin")  # raises EMAIL_EXISTS

    with pytest.raises(RepositoryError, match="EMAIL_EXISTS"):
        repos.with_transaction(work)
    assert [u.email for u in repos.users.list(t.id)] == ["dup@tx.com"]


def test_timestamps_are_timezone_aware_utc(world) -> None:  # type: ignore[no-untyped-def]
    a = world.repos.assessments.find_by_id(world.tenant.id, world.assessment.id)
    assert a.created_at.tzinfo is not None and a.created_at.utcoffset() == timedelta(0)
    assert a.created_at == datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

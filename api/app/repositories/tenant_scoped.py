"""Tenant-scoped repositories.

Rules (Prompt A 2.4):
* ``assert_tenant`` is the first line of every function that touches a tenant-owned table.
* Every statement filters on ``tenant_id`` (or inserts it). SQLAlchemy Core binds every
  parameter; SQL text is never built from strings.
* Functions return dataclasses, never raw rows.
Cross-tenant lookups live in ``system.py`` and nowhere else.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, case, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from ..core.ids import new_id
from . import mappers as m
from .base import Ctx, constraint_kind, err_text, fk_error
from .models import (
    GRACE_SECONDS,
    Assessment,
    AssessmentListItem,
    Attempt,
    AttemptListItem,
    AuditLogEntry,
    Job,
    Participant,
    ParticipantListItem,
    Question,
    RepositoryError,
    Response,
    Score,
    Session,
    Tenant,
    User,
    assert_tenant,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def norm_email(email: str) -> str:
    return email.strip().lower()


# ── Tenants (the tenant table itself is not tenant-scoped) ──────────────────────────────────
class TenantsRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def create(self, *, name: str, id: str | None = None) -> Tenant:
        now = self.c.clock.now()
        tid = (id or new_id()).lower()
        t = self.c.t["tenants"]
        self.c.x.run(
            lambda cn: cn.execute(insert(t).values(id=tid, name=name, status="active", created_at=now, updated_at=now))
        )
        return Tenant(tid, name, "active", now, now)

    def find_by_id(self, id: str) -> Tenant | None:
        t = self.c.t["tenants"]
        row = self.c.x.run(lambda cn: cn.execute(select(t).where(t.c.id == id.lower())).first())
        return m.tenant(row) if row else None

    def list(self) -> list[Tenant]:
        t = self.c.t["tenants"]
        rows = self.c.x.run(lambda cn: cn.execute(select(t).order_by(t.c.created_at, t.c.id)).all())
        return [m.tenant(r) for r in rows]


# ── Users ───────────────────────────────────────────────────────────────────────────────────
class UsersRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def create(
        self,
        tenant_id: str,
        *,
        name: str,
        email: str,
        password_hash: str,
        role: str,
        status: str = "active",
        id: str | None = None,
    ) -> User:
        tenant_id = assert_tenant(tenant_id)
        now = self.c.clock.now()
        uid = (id or new_id()).lower()
        email = norm_email(email)
        t = self.c.t["users"]
        try:
            self.c.x.run(
                lambda cn: cn.execute(
                    insert(t).values(
                        id=uid, tenant_id=tenant_id, name=name, email=email, password_hash=password_hash,
                        role=role, status=status, created_at=now, updated_at=now,
                    )
                )
            )  # fmt: skip
        except IntegrityError as exc:
            kind = constraint_kind(exc)
            if kind == "unique" and "email" in err_text(exc):
                raise RepositoryError("EMAIL_EXISTS", "email already registered") from None
            if kind == "fk":
                raise fk_error() from None
            raise RepositoryError("CONSTRAINT_VIOLATION", "invalid user data") from None
        return User(uid, tenant_id, name, email, password_hash, role, status, now, now)

    def find_by_id(self, tenant_id: str, id: str) -> User | None:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["users"]
        row = self.c.x.run(
            lambda cn: cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()
        )
        return m.user(row) if row else None

    def find_by_email(self, email: str) -> User | None:
        """Login lookup. Emails are globally unique (R1), so this is intentionally cross-tenant;
        it is listed in the system-queries registry."""
        t = self.c.t["users"]
        row = self.c.x.run(lambda cn: cn.execute(select(t).where(t.c.email == norm_email(email))).first())
        return m.user(row) if row else None

    def count_active_admins(self, tenant_id: str) -> int:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["users"]
        return int(
            self.c.x.run(
                lambda cn: cn.execute(
                    select(func.count())
                    .select_from(t)
                    .where(t.c.tenant_id == tenant_id, t.c.role == "admin", t.c.status == "active")
                ).scalar_one()
            )
        )

    def list(self, tenant_id: str) -> list[User]:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["users"]
        rows = self.c.x.run(
            lambda cn: cn.execute(select(t).where(t.c.tenant_id == tenant_id).order_by(t.c.created_at, t.c.id)).all()
        )
        return [m.user(r) for r in rows]

    def update(self, tenant_id: str, id: str, **fields: Any) -> User | None:
        tenant_id = assert_tenant(tenant_id)
        allowed = {k: v for k, v in fields.items() if k in ("name", "role", "status") and v is not None}
        t = self.c.t["users"]

        def go(cn: Connection) -> Any:
            if allowed:
                cn.execute(
                    update(t)
                    .where(t.c.tenant_id == tenant_id, t.c.id == id.lower())
                    .values(**allowed, updated_at=self.c.clock.now())
                )
            return cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()

        row = self.c.x.run(go)
        return m.user(row) if row else None


# ── Sessions ────────────────────────────────────────────────────────────────────────────────
class SessionsRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def create(
        self, tenant_id: str, *, user_id: str, token_hash: str, expires_at: datetime, id: str | None = None
    ) -> Session:
        tenant_id = assert_tenant(tenant_id)
        now = self.c.clock.now()
        sid = (id or new_id()).lower()
        t = self.c.t["sessions"]
        try:
            self.c.x.run(
                lambda cn: cn.execute(
                    insert(t).values(
                        id=sid, tenant_id=tenant_id, user_id=user_id.lower(), token_hash=token_hash,
                        expires_at=expires_at, created_at=now, last_seen_at=now,
                    )
                )
            )  # fmt: skip
        except IntegrityError as exc:
            if constraint_kind(exc) == "fk":
                raise fk_error() from None
            raise RepositoryError("DUPLICATE_TOKEN", "Duplicate tokenHash constraint violation") from None
        return Session(sid, tenant_id, user_id.lower(), token_hash, expires_at, now, now)

    def delete_by_token_hash(self, token_hash: str) -> bool:
        """Logout: the caller already proved possession of the token (hash), so no tenant is needed."""
        t = self.c.t["sessions"]
        res = self.c.x.run(lambda cn: cn.execute(delete(t).where(t.c.token_hash == token_hash)))
        return res.rowcount > 0

    def touch(self, token_hash: str, now: datetime) -> None:
        """Bump ``last_seen_at``; the caller already proved possession of the token (hash)."""
        t = self.c.t["sessions"]
        self.c.x.run(lambda cn: cn.execute(update(t).where(t.c.token_hash == token_hash).values(last_seen_at=now)))

    def delete_by_user_id(self, tenant_id: str, user_id: str) -> int:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["sessions"]
        res = self.c.x.run(
            lambda cn: cn.execute(delete(t).where(t.c.tenant_id == tenant_id, t.c.user_id == user_id.lower()))
        )
        return int(res.rowcount)


# ── Login attempts (rate limiting; keyed by email, not tenant-owned) ───────────────────────
class LoginAttemptsRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def record(self, *, email: str, ip_address: str, success: bool, id: str | None = None) -> None:
        t = self.c.t["login_attempts"]
        self.c.x.run(
            lambda cn: cn.execute(
                insert(t).values(
                    id=(id or new_id()).lower(), email=norm_email(email), ip_address=ip_address,
                    attempted_at=self.c.clock.now(), success=success,
                )
            )
        )  # fmt: skip

    def count_recent_failures(self, email: str, since: datetime) -> int:
        t = self.c.t["login_attempts"]
        return int(
            self.c.x.run(
                lambda cn: cn.execute(
                    select(func.count())
                    .select_from(t)
                    .where(t.c.email == norm_email(email), t.c.success.is_(False), t.c.attempted_at >= since)
                ).scalar_one()
            )
        )

    def failure_state(self, email: str, since: datetime) -> tuple[int, datetime | None]:
        """Failed attempts for ``email`` strictly after ``since`` and the time of the latest one."""
        t = self.c.t["login_attempts"]
        e = norm_email(email)

        def go(cn: Connection) -> tuple[int, datetime | None]:
            n, last = cn.execute(
                select(func.count(), func.max(t.c.attempted_at)).where(
                    t.c.email == e, t.c.success.is_(False), t.c.attempted_at > since
                )
            ).one()
            return int(n), last

        return self.c.x.run(go)

    def clear_failures(self, email: str) -> None:
        """A successful login clears that email's failure window (Prompt A 4.3)."""
        t = self.c.t["login_attempts"]
        self.c.x.run(lambda cn: cn.execute(delete(t).where(t.c.email == norm_email(email), t.c.success.is_(False))))


# ── Assessments ─────────────────────────────────────────────────────────────────────────────
class AssessmentsRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def create(
        self,
        tenant_id: str,
        *,
        title: str,
        sections: list[dict[str, Any]],
        created_by: str,
        job_description: str | None = None,
        duration_minutes: int = 60,
        passing_score: int = 60,
        id: str | None = None,
    ) -> Assessment:
        tenant_id = assert_tenant(tenant_id)
        now = self.c.clock.now()
        aid = (id or new_id()).lower()
        t = self.c.t["assessments"]
        try:
            self.c.x.run(
                lambda cn: cn.execute(
                    insert(t).values(
                        id=aid, tenant_id=tenant_id, title=title, job_description=job_description,
                        jd_file_name=None, duration_minutes=duration_minutes, passing_score=passing_score,
                        status="draft", sections_json=sections, created_by=created_by.lower(),
                        created_at=now, updated_at=now,
                    )
                )
            )  # fmt: skip
        except IntegrityError as exc:
            if constraint_kind(exc) == "fk":
                raise fk_error() from None
            raise RepositoryError("CONSTRAINT_VIOLATION", "invalid assessment data") from None
        return Assessment(
            aid, tenant_id, title, job_description, None, duration_minutes, passing_score, "draft",
            sections, created_by.lower(), now, now,
        )  # fmt: skip

    def find_by_id(self, tenant_id: str, id: str) -> Assessment | None:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["assessments"]
        row = self.c.x.run(
            lambda cn: cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()
        )
        return m.assessment(row) if row else None

    def list(self, tenant_id: str, status: str | None = None) -> list[AssessmentListItem]:
        tenant_id = assert_tenant(tenant_id)
        a, p, at = self.c.t["assessments"], self.c.t["participants"], self.c.t["attempts"]
        pc = (
            select(p.c.assessment_id, func.count().label("n"))
            .where(p.c.tenant_id == tenant_id)
            .group_by(p.c.assessment_id)
            .subquery()
        )
        sc = (
            select(at.c.assessment_id, func.count().label("n"))
            .where(at.c.tenant_id == tenant_id, at.c.status != "in_progress")
            .group_by(at.c.assessment_id)
            .subquery()
        )
        q = (
            select(a.c.id, a.c.title, a.c.status, a.c.created_at, func.coalesce(pc.c.n, 0).label("pn"),
                   func.coalesce(sc.c.n, 0).label("sn"))
            .select_from(a.outerjoin(pc, pc.c.assessment_id == a.c.id).outerjoin(sc, sc.c.assessment_id == a.c.id))
            .where(a.c.tenant_id == tenant_id)
            .order_by(a.c.created_at.desc(), a.c.id)
        )  # fmt: skip
        if status:
            q = q.where(a.c.status == status)
        rows = self.c.x.run(lambda cn: cn.execute(q).all())
        return [AssessmentListItem(r.id, r.title, r.status, int(r.pn), int(r.sn), r.created_at) for r in rows]

    def update(self, tenant_id: str, id: str, **fields: Any) -> Assessment | None:
        tenant_id = assert_tenant(tenant_id)
        mapping = {
            "title": "title", "job_description": "job_description", "jd_file_name": "jd_file_name",
            "duration_minutes": "duration_minutes", "passing_score": "passing_score", "status": "status",
            "sections": "sections_json",
        }  # fmt: skip
        values = {mapping[k]: v for k, v in fields.items() if k in mapping}
        t = self.c.t["assessments"]

        def go(cn: Connection) -> Any:
            if values:
                try:
                    cn.execute(
                        update(t)
                        .where(t.c.tenant_id == tenant_id, t.c.id == id.lower())
                        .values(**values, updated_at=self.c.clock.now())
                    )
                except IntegrityError:
                    raise RepositoryError("CONSTRAINT_VIOLATION", "invalid assessment data") from None
            return cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()

        row = self.c.x.run(go)
        return m.assessment(row) if row else None

    def delete(self, tenant_id: str, id: str) -> bool:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["assessments"]
        try:
            res = self.c.x.run(lambda cn: cn.execute(delete(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())))
        except IntegrityError:
            raise RepositoryError("IN_USE", "assessment has dependent records") from None
        return res.rowcount > 0


# ── Questions ───────────────────────────────────────────────────────────────────────────────
class QuestionsRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def _values(self, tenant_id: str, now: datetime, d: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": (d.get("id") or new_id()).lower(), "tenant_id": tenant_id,
            "assessment_id": d["assessment_id"].lower(), "section_index": d.get("section_index", 0),
            "type": d["type"], "body": d["body"], "options_json": d.get("options"),
            "correct_answer": d.get("correct_answer"), "rubric": d.get("rubric"),
            "max_score": d.get("max_score", 10), "source": d.get("source", "ai"),
            "position": d.get("position", 0), "status": d.get("status", "draft"),
            "explanation": d.get("explanation"), "word_limit": d.get("word_limit"),
            "created_at": now, "updated_at": now,
        }  # fmt: skip

    def create_many(self, tenant_id: str, items: list[dict[str, Any]]) -> list[Question]:
        tenant_id = assert_tenant(tenant_id)
        now = self.c.clock.now()
        rows = [self._values(tenant_id, now, d) for d in items]
        t = self.c.t["questions"]
        if not rows:
            return []

        def go(cn: Connection) -> None:
            for r in rows:
                cn.execute(insert(t).values(**r))

        try:
            self.c.x.run(go)
        except IntegrityError as exc:
            if constraint_kind(exc) == "fk":
                raise fk_error() from None
            raise RepositoryError("CONSTRAINT_VIOLATION", "invalid question data") from None
        return [self._from_values(r) for r in rows]

    def create(self, tenant_id: str, **data: Any) -> Question:
        tenant_id = assert_tenant(tenant_id)
        return self.create_many(tenant_id, [data])[0]

    @staticmethod
    def _from_values(r: dict[str, Any]) -> Question:
        return Question(
            r["id"], r["tenant_id"], r["assessment_id"], r["section_index"], r["type"], r["body"],
            r["options_json"], r["correct_answer"], r["rubric"], r["max_score"], r["source"],
            r["position"], r["status"], r["explanation"], r["word_limit"], r["created_at"], r["updated_at"],
        )  # fmt: skip

    def find_by_id(self, tenant_id: str, id: str) -> Question | None:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["questions"]
        row = self.c.x.run(
            lambda cn: cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()
        )
        return m.question(row) if row else None

    def list_by_assessment(self, tenant_id: str, assessment_id: str) -> list[Question]:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["questions"]
        rows = self.c.x.run(
            lambda cn: cn.execute(
                select(t)
                .where(t.c.tenant_id == tenant_id, t.c.assessment_id == assessment_id.lower())
                .order_by(t.c.section_index, t.c.position, t.c.created_at, t.c.id)
            ).all()
        )
        return [m.question(r) for r in rows]

    def update(self, tenant_id: str, id: str, **fields: Any) -> Question | None:
        tenant_id = assert_tenant(tenant_id)
        mapping = {
            "body": "body", "options": "options_json", "correct_answer": "correct_answer",
            "rubric": "rubric", "max_score": "max_score", "position": "position",
            "explanation": "explanation", "word_limit": "word_limit", "status": "status",
        }  # fmt: skip
        values = {mapping[k]: v for k, v in fields.items() if k in mapping}
        t = self.c.t["questions"]

        def go(cn: Connection) -> Any:
            if values:
                cn.execute(
                    update(t)
                    .where(t.c.tenant_id == tenant_id, t.c.id == id.lower())
                    .values(**values, updated_at=self.c.clock.now())
                )
            return cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()

        row = self.c.x.run(go)
        return m.question(row) if row else None

    def delete(self, tenant_id: str, id: str) -> bool:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["questions"]
        try:
            res = self.c.x.run(lambda cn: cn.execute(delete(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())))
        except IntegrityError:
            raise RepositoryError("IN_USE", "question has responses or scores") from None
        return res.rowcount > 0

    def delete_by_assessment_and_source(
        self, tenant_id: str, assessment_id: str, section_index: int, source: str
    ) -> int:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["questions"]
        res = self.c.x.run(
            lambda cn: cn.execute(
                delete(t).where(
                    t.c.tenant_id == tenant_id,
                    t.c.assessment_id == assessment_id.lower(),
                    t.c.section_index == section_index,
                    t.c.source == source,
                )
            )
        )
        return int(res.rowcount)

    def replace_ai_in_sections(
        self, tenant_id: str, assessment_id: str, per_section: dict[int, list[dict[str, Any]]]
    ) -> list[Question]:
        """Atomically swap the AI draft questions of the given sections for ``per_section`` (custom ones stay).

        One transaction: either every section is replaced or nothing changes (no partial questions on a
        failed job). Refuses when the assessment is no longer a draft (approval raced the job).
        """
        tenant_id = assert_tenant(tenant_id)
        aid = assessment_id.lower()
        now = self.c.clock.now()
        q, a = self.c.t["questions"], self.c.t["assessments"]
        created: list[dict[str, Any]] = []

        def go(cn: Connection) -> None:
            status = cn.execute(select(a.c.status).where(a.c.tenant_id == tenant_id, a.c.id == aid)).scalar()
            if status is None:
                raise RepositoryError("NOT_FOUND", "assessment not found")
            if status != "draft":
                raise RepositoryError("NOT_DRAFT", "assessment is no longer a draft")
            for idx, items in per_section.items():
                cn.execute(
                    delete(q).where(
                        q.c.tenant_id == tenant_id, q.c.assessment_id == aid,
                        q.c.section_index == idx, q.c.source == "ai", q.c.status == "draft",
                    )
                )  # fmt: skip
                top = cn.execute(
                    select(func.max(q.c.position)).where(
                        q.c.tenant_id == tenant_id, q.c.assessment_id == aid, q.c.section_index == idx
                    )
                ).scalar()
                nxt = 0 if top is None else int(top) + 1
                for item in items:
                    row = self._values(
                        tenant_id, now,
                        {**item, "assessment_id": aid, "section_index": idx, "source": "ai", "position": nxt},
                    )  # fmt: skip
                    nxt += 1
                    cn.execute(insert(q).values(**row))
                    created.append(row)

        try:
            self.c.x.run(go)
        except IntegrityError:
            raise RepositoryError("CONSTRAINT_VIOLATION", "invalid question data") from None
        return [self._from_values(r) for r in created]

    def approve_all(self, tenant_id: str, assessment_id: str) -> int:
        """Approve: questions -> ``approved`` with positions renumbered 1..n, assessment -> ``approved`` (one tx)."""
        tenant_id = assert_tenant(tenant_id)
        aid = assessment_id.lower()
        now = self.c.clock.now()
        q, a = self.c.t["questions"], self.c.t["assessments"]

        def go(cn: Connection) -> int:
            res = cn.execute(
                update(a).where(a.c.tenant_id == tenant_id, a.c.id == aid, a.c.status == "draft")
                .values(status="approved", updated_at=now)
            )  # fmt: skip
            if res.rowcount == 0:
                raise RepositoryError("NOT_DRAFT", "assessment is not a draft")
            rows = cn.execute(
                select(q.c.id).where(q.c.tenant_id == tenant_id, q.c.assessment_id == aid)
                .order_by(q.c.section_index, q.c.position, q.c.created_at, q.c.id)
            ).all()  # fmt: skip
            for n, r in enumerate(rows, start=1):
                cn.execute(
                    update(q).where(q.c.tenant_id == tenant_id, q.c.id == r.id)
                    .values(status="approved", position=n, updated_at=now)
                )  # fmt: skip
            return len(rows)

        return self.c.x.run(go)


# ── Participants ────────────────────────────────────────────────────────────────────────────
class ParticipantsRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def create_many(
        self, tenant_id: str, assessment_id: str, items: list[dict[str, str]]
    ) -> tuple[list[Participant], list[str], list[str]]:
        """Returns ``(added, duplicates, invalid)``; duplicates/invalid are lowercase emails as given."""
        tenant_id = assert_tenant(tenant_id)
        now = self.c.clock.now()
        aid = assessment_id.lower()
        a, p = self.c.t["assessments"], self.c.t["participants"]

        def go(cn: Connection) -> tuple[list[Participant], list[str], list[str]]:
            if cn.execute(select(a.c.id).where(a.c.tenant_id == tenant_id, a.c.id == aid)).first() is None:
                raise fk_error()
            existing = {
                r.email
                for r in cn.execute(select(p.c.email).where(p.c.tenant_id == tenant_id, p.c.assessment_id == aid))
            }
            added: list[Participant] = []
            dupes: list[str] = []
            invalid: list[str] = []
            for item in items:
                email = norm_email(item.get("email", ""))
                name = (item.get("name") or "").strip()
                if not _EMAIL_RE.match(email) or not name or len(email) > 320:
                    invalid.append(email)
                    continue
                if email in existing:
                    dupes.append(email)
                    continue
                existing.add(email)
                pid = new_id()
                cn.execute(
                    insert(p).values(
                        id=pid, tenant_id=tenant_id, assessment_id=aid, name=name, email=email,
                        invite_status="none", token_hash=None, token_expires_at=None, invited_at=None,
                        created_at=now, updated_at=now,
                    )
                )  # fmt: skip
                added.append(Participant(pid, tenant_id, aid, name, email, "none", None, None, None, now, now))
            return added, dupes, invalid

        return self.c.x.run(go)

    def list_by_assessment(self, tenant_id: str, assessment_id: str) -> list[ParticipantListItem]:
        tenant_id = assert_tenant(tenant_id)
        p, at = self.c.t["participants"], self.c.t["attempts"]
        q = (
            select(p.c.id, p.c.name, p.c.email, p.c.invite_status, at.c.status.label("astatus"), at.c.percent)
            .select_from(p.outerjoin(at, (at.c.participant_id == p.c.id) & (at.c.tenant_id == p.c.tenant_id)))
            .where(p.c.tenant_id == tenant_id, p.c.assessment_id == assessment_id.lower())
            .order_by(p.c.created_at, p.c.email)
        )  # fmt: skip
        rows = self.c.x.run(lambda cn: cn.execute(q).all())
        return [
            ParticipantListItem(
                r.id, r.name, r.email, r.invite_status, r.astatus or "not_started",
                None if r.percent is None else float(r.percent),
            )
            for r in rows
        ]  # fmt: skip

    def find_by_id(self, tenant_id: str, id: str) -> Participant | None:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["participants"]
        row = self.c.x.run(
            lambda cn: cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()
        )
        return m.participant(row) if row else None

    def update_token(self, tenant_id: str, id: str, token_hash: str | None, expires_at: datetime | None) -> None:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["participants"]
        try:
            self.c.x.run(
                lambda cn: cn.execute(
                    update(t)
                    .where(t.c.tenant_id == tenant_id, t.c.id == id.lower())
                    .values(token_hash=token_hash, token_expires_at=expires_at, updated_at=self.c.clock.now())
                )
            )
        except IntegrityError:
            raise RepositoryError("DUPLICATE_TOKEN", "Duplicate tokenHash constraint violation") from None

    def update_invite_status(self, tenant_id: str, id: str, status: str, invited_at: datetime | None = None) -> None:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["participants"]
        values: dict[str, Any] = {"invite_status": status, "updated_at": self.c.clock.now()}
        if invited_at is not None:
            values["invited_at"] = invited_at
        try:
            self.c.x.run(
                lambda cn: cn.execute(
                    update(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower()).values(**values)
                )
            )
        except IntegrityError:
            raise RepositoryError("CONSTRAINT_VIOLATION", "invalid invite status") from None

    def delete(self, tenant_id: str, id: str) -> bool:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["participants"]
        try:
            res = self.c.x.run(lambda cn: cn.execute(delete(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())))
        except IntegrityError:
            raise RepositoryError("IN_USE", "participant has an attempt") from None
        return res.rowcount > 0


# ── Attempts ────────────────────────────────────────────────────────────────────────────────
class AttemptsRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def create(
        self, tenant_id: str, *, participant_id: str, assessment_id: str, attempt_token_hash: str,
        deadline_at: datetime, id: str | None = None,
    ) -> Attempt:  # fmt: skip
        tenant_id = assert_tenant(tenant_id)
        now = self.c.clock.now()
        aid = (id or new_id()).lower()
        t = self.c.t["attempts"]
        try:
            self.c.x.run(
                lambda cn: cn.execute(
                    insert(t).values(
                        id=aid, tenant_id=tenant_id, participant_id=participant_id.lower(),
                        assessment_id=assessment_id.lower(), attempt_token_hash=attempt_token_hash,
                        started_at=now, deadline_at=deadline_at, submitted_at=None, status="in_progress",
                        score=None, max_score=None, percent=None, passed=None, created_at=now, updated_at=now,
                    )
                )
            )  # fmt: skip
        except IntegrityError as exc:
            kind, text = constraint_kind(exc), err_text(exc)
            if kind == "fk":
                raise fk_error() from None
            if kind == "unique" and ("token_hash" in text or "uq_attempts_token_hash" in text):
                raise RepositoryError("DUPLICATE_TOKEN", "Duplicate tokenHash constraint violation") from None
            if kind == "unique":
                raise RepositoryError("ATTEMPT_EXISTS", "attempt already exists for participant") from None
            raise RepositoryError("CONSTRAINT_VIOLATION", "invalid attempt data") from None
        return Attempt(
            aid, tenant_id, participant_id.lower(), assessment_id.lower(), attempt_token_hash, now,
            deadline_at, None, "in_progress", None, None, None, None, now, now,
        )  # fmt: skip

    def find_by_id(self, tenant_id: str, id: str) -> Attempt | None:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["attempts"]
        row = self.c.x.run(
            lambda cn: cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()
        )
        return m.attempt(row) if row else None

    def find_by_participant_id(self, tenant_id: str, participant_id: str) -> Attempt | None:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["attempts"]
        row = self.c.x.run(
            lambda cn: cn.execute(
                select(t).where(t.c.tenant_id == tenant_id, t.c.participant_id == participant_id.lower())
            ).first()
        )
        return m.attempt(row) if row else None

    def update_status(
        self, tenant_id: str, id: str, status: str, submitted_at: datetime | None = None
    ) -> Attempt | None:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["attempts"]
        values: dict[str, Any] = {"status": status, "updated_at": self.c.clock.now()}
        if submitted_at is not None:
            values["submitted_at"] = submitted_at

        def go(cn: Connection) -> Any:
            cn.execute(update(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower()).values(**values))
            return cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()

        row = self.c.x.run(go)
        return m.attempt(row) if row else None

    def update_scores(
        self, tenant_id: str, id: str, *, score: float, max_score: float, percent: float, passed: bool,
        status: str | None = None,
    ) -> Attempt | None:  # fmt: skip
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["attempts"]
        values: dict[str, Any] = {
            "score": score, "max_score": max_score, "percent": percent, "passed": passed,
            "updated_at": self.c.clock.now(),
        }  # fmt: skip
        if status:
            values["status"] = status

        def go(cn: Connection) -> Any:
            cn.execute(update(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower()).values(**values))
            return cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()

        row = self.c.x.run(go)
        return m.attempt(row) if row else None

    def list_by_assessment(self, tenant_id: str, assessment_id: str, sort: str | None = None) -> list[AttemptListItem]:
        tenant_id = assert_tenant(tenant_id)
        at, p = self.c.t["attempts"], self.c.t["participants"]
        q = (
            select(at, p.c.name.label("pname"), p.c.email.label("pemail"))
            .select_from(at.join(p, (p.c.id == at.c.participant_id) & (p.c.tenant_id == at.c.tenant_id)))
            .where(at.c.tenant_id == tenant_id, at.c.assessment_id == assessment_id.lower())
        )  # fmt: skip
        if sort == "name":
            q = q.order_by(p.c.name, p.c.email)
        else:
            # highest score first, unscored (NULL) last
            q = q.order_by(case((at.c.percent.is_(None), 1), else_=0), at.c.percent.desc(), p.c.name)
        rows = self.c.x.run(lambda cn: cn.execute(q).all())
        out: list[AttemptListItem] = []
        for r in rows:
            mp = r._mapping
            taken = None
            if mp["submitted_at"] is not None:
                taken = int((mp["submitted_at"] - mp["started_at"]).total_seconds())
            out.append(
                AttemptListItem(
                    mp["id"], mp["pname"], mp["pemail"],
                    None if mp["score"] is None else float(mp["score"]),
                    None if mp["max_score"] is None else float(mp["max_score"]),
                    None if mp["percent"] is None else float(mp["percent"]),
                    None if mp["passed"] is None else bool(mp["passed"]),
                    taken, mp["status"],
                )
            )  # fmt: skip
        return out


# ── Responses ───────────────────────────────────────────────────────────────────────────────
class ResponsesRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def upsert(self, tenant_id: str, *, attempt_id: str, question_id: str, answer_text: str) -> datetime:
        """Idempotent; last write wins. Rejected after ``deadline + 15 s`` using the injected clock."""
        tenant_id = assert_tenant(tenant_id)
        now = self.c.clock.now()
        at, r = self.c.t["attempts"], self.c.t["responses"]
        aid, qid = attempt_id.lower(), question_id.lower()

        def go(cn: Connection) -> datetime:
            att = cn.execute(select(at.c.deadline_at).where(at.c.tenant_id == tenant_id, at.c.id == aid)).first()
            if att is None:
                raise fk_error()
            if now > att.deadline_at + timedelta(seconds=GRACE_SECONDS):
                raise RepositoryError("ATTEMPT_CLOSED", "deadline passed")
            upd = cn.execute(
                update(r)
                .where(r.c.attempt_id == aid, r.c.question_id == qid, r.c.tenant_id == tenant_id)
                .values(answer_text=answer_text, saved_at=now)
            )
            if upd.rowcount == 0:
                try:
                    cn.execute(
                        insert(r).values(
                            id=new_id(), tenant_id=tenant_id, attempt_id=aid, question_id=qid,
                            answer_text=answer_text, saved_at=now,
                        )
                    )  # fmt: skip
                except IntegrityError as exc:
                    if constraint_kind(exc) == "fk":
                        raise fk_error() from None
                    raise
            return now

        return self.c.x.run(go)

    def list_by_attempt(self, tenant_id: str, attempt_id: str) -> list[Response]:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["responses"]
        rows = self.c.x.run(
            lambda cn: cn.execute(
                select(t)
                .where(t.c.tenant_id == tenant_id, t.c.attempt_id == attempt_id.lower())
                .order_by(t.c.saved_at, t.c.id)
            ).all()
        )
        return [m.response(r) for r in rows]


# ── Scores ──────────────────────────────────────────────────────────────────────────────────
class ScoresRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def upsert(
        self, tenant_id: str, *, attempt_id: str, question_id: str, score: float, max_score: float,
        source: str, justification: str | None = None,
    ) -> Score:  # fmt: skip
        tenant_id = assert_tenant(tenant_id)
        now = self.c.clock.now()
        t = self.c.t["scores"]
        aid, qid = attempt_id.lower(), question_id.lower()

        def go(cn: Connection) -> Any:
            upd = cn.execute(
                update(t)
                .where(t.c.tenant_id == tenant_id, t.c.attempt_id == aid, t.c.question_id == qid)
                .values(score=score, max_score=max_score, source=source, justification=justification, updated_at=now)
            )
            if upd.rowcount == 0:
                cn.execute(
                    insert(t).values(
                        id=new_id(), tenant_id=tenant_id, attempt_id=aid, question_id=qid, score=score,
                        max_score=max_score, source=source, justification=justification,
                        created_at=now, updated_at=now,
                    )
                )  # fmt: skip
            return cn.execute(
                select(t).where(t.c.tenant_id == tenant_id, t.c.attempt_id == aid, t.c.question_id == qid)
            ).first()

        try:
            row = self.c.x.run(go)
        except IntegrityError as exc:
            if constraint_kind(exc) == "fk":
                raise fk_error() from None
            raise RepositoryError("CONSTRAINT_VIOLATION", "invalid score data") from None
        return m.score(row)

    def list_by_attempt(self, tenant_id: str, attempt_id: str) -> list[Score]:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["scores"]
        rows = self.c.x.run(
            lambda cn: cn.execute(
                select(t)
                .where(t.c.tenant_id == tenant_id, t.c.attempt_id == attempt_id.lower())
                .order_by(t.c.created_at, t.c.id)
            ).all()
        )
        return [m.score(r) for r in rows]


# ── Jobs (tenant-scoped parts; claim/complete/fail are in system.py) ───────────────────────
class JobsRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def enqueue(self, tenant_id: str, *, type: str, ref_id: str, payload: Any, max_attempts: int = 3) -> Job:
        tenant_id = assert_tenant(tenant_id)
        now = self.c.clock.now()
        jid = new_id()
        t = self.c.t["jobs"]
        try:
            self.c.x.run(
                lambda cn: cn.execute(
                    insert(t).values(
                        id=jid, tenant_id=tenant_id, type=type, status="queued", ref_id=ref_id.lower(),
                        payload_json=payload, result_json=None, error=None, attempts=0,
                        max_attempts=max_attempts, locked_at=None, locked_by=None, run_after=None,
                        started_at=None, tokens_used=0, created_at=now, updated_at=now,
                    )
                )
            )  # fmt: skip
        except IntegrityError as exc:
            if constraint_kind(exc) == "fk":
                raise fk_error() from None
            raise RepositoryError("CONSTRAINT_VIOLATION", "invalid job data") from None
        return Job(
            jid, tenant_id, type, "queued", ref_id.lower(), payload, None, None, 0, max_attempts, None, None,
            None, None, 0, now, now,
        )  # fmt: skip

    def find_by_id(self, tenant_id: str, id: str) -> Job | None:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["jobs"]
        row = self.c.x.run(
            lambda cn: cn.execute(select(t).where(t.c.tenant_id == tenant_id, t.c.id == id.lower())).first()
        )
        return m.job(row) if row else None

    def claim_next(self, worker_id: str) -> Job | None:
        """Convenience alias for ``system.claim_next_job`` (same implementation)."""
        from .system import claim_next_job

        return claim_next_job(self.c, worker_id)

    def complete(self, id: str, result: Any = None, tokens_used: int = 0) -> None:
        """Mark a claimed job done. Takes only the job id: the worker got it from ``claim_next``."""
        t = self.c.t["jobs"]
        self.c.x.run(
            lambda cn: cn.execute(
                update(t)
                .where(t.c.id == id.lower())
                .values(status="done", result_json=result, error=None, locked_at=None, locked_by=None,
                        run_after=None, tokens_used=tokens_used, updated_at=self.c.clock.now())
            )
        )  # fmt: skip

    def fail(
        self, id: str, error: str, *, retryable: bool = True, delay_seconds: float | None = None,
        code: str | None = None, tokens_used: int = 0,
    ) -> str:  # fmt: skip
        """Record a failure and return the new status.

        Re-queues (optionally not before ``now + delay_seconds``) while attempts remain and ``retryable``;
        otherwise the job is ``failed`` for good, with ``code`` kept in ``result_json``.
        """
        t = self.c.t["jobs"]
        now = self.c.clock.now()

        def go(cn: Connection) -> str:
            row = cn.execute(
                select(t.c.attempts, t.c.max_attempts, t.c.tokens_used).where(t.c.id == id.lower())
            ).first()
            if row is None:
                return "failed"
            again = retryable and row.attempts < row.max_attempts
            values: dict[str, Any] = {
                "status": "queued" if again else "failed", "error": error[:4000], "locked_at": None,
                "locked_by": None, "updated_at": now, "tokens_used": int(row.tokens_used) + tokens_used,
                "run_after": now + timedelta(seconds=delay_seconds) if again and delay_seconds else None,
            }  # fmt: skip
            if not again and code:
                values["result_json"] = {"code": code}
            cn.execute(update(t).where(t.c.id == id.lower()).values(**values))
            return str(values["status"])

        return self.c.x.run(go)

    def requeue_stuck(self, older_than: datetime) -> list[tuple[str, str]]:
        """Job-loop maintenance (any tenant, like ``claim_next``): jobs ``running`` since before ``older_than``
        belong to a dead worker. Re-queue them, or fail them when no attempts remain. Returns (id, status)."""
        t = self.c.t["jobs"]
        now = self.c.clock.now()

        def go(cn: Connection) -> list[tuple[str, str]]:
            rows = cn.execute(
                select(t.c.id, t.c.attempts, t.c.max_attempts).where(
                    t.c.status == "running", t.c.locked_at < older_than
                )
            ).all()
            out = []
            for r in rows:
                again = r.attempts < r.max_attempts
                status = "queued" if again else "failed"
                msg = "The job stopped before finishing (worker restarted); " + ("retrying." if again else "giving up.")
                res = cn.execute(
                    update(t).where(t.c.id == r.id, t.c.status == "running")
                    .values(status=status, error=msg, locked_at=None, locked_by=None, run_after=None, updated_at=now)
                )  # fmt: skip
                if res.rowcount:
                    out.append((str(r.id), status))
            return out

        return self.c.x.run(go)

    def sum_tokens(self, tenant_id: str, date_utc: datetime) -> int:
        """Tokens spent by the tenant's jobs created on the UTC day of ``date_utc``."""
        tenant_id = assert_tenant(tenant_id)
        start = date_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        t = self.c.t["jobs"]
        return int(
            self.c.x.run(
                lambda cn: cn.execute(
                    select(func.coalesce(func.sum(t.c.tokens_used), 0)).where(
                        t.c.tenant_id == tenant_id, t.c.created_at >= start, t.c.created_at < start + timedelta(days=1)
                    )
                ).scalar_one()
            )
        )

    def count_daily_generations(self, tenant_id: str, date_utc: datetime) -> int:
        tenant_id = assert_tenant(tenant_id)
        start = date_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        t = self.c.t["jobs"]
        return int(
            self.c.x.run(
                lambda cn: cn.execute(
                    select(func.count())
                    .select_from(t)
                    .where(
                        t.c.tenant_id == tenant_id,
                        t.c.type == "generate",
                        t.c.created_at >= start,
                        t.c.created_at < end,
                    )
                ).scalar_one()
            )
        )


# ── Audit ───────────────────────────────────────────────────────────────────────────────────
class AuditRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def log(
        self, tenant_id: str, *, action: str, entity_type: str, entity_id: str,
        actor_id: str | None = None, details: Any = None,
    ) -> None:  # fmt: skip
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["audit_log"]
        try:
            self.c.x.run(
                lambda cn: cn.execute(
                    insert(t).values(
                        id=new_id(), tenant_id=tenant_id, actor_id=actor_id.lower() if actor_id else None,
                        action=action, entity_type=entity_type, entity_id=entity_id.lower(),
                        details_json=details, created_at=self.c.clock.now(),
                    )
                )
            )  # fmt: skip
        except IntegrityError:
            raise fk_error() from None

    def list_by_entity(self, tenant_id: str, entity_type: str, entity_id: str) -> list[AuditLogEntry]:
        tenant_id = assert_tenant(tenant_id)
        t = self.c.t["audit_log"]
        rows = self.c.x.run(
            lambda cn: cn.execute(
                select(t)
                .where(t.c.tenant_id == tenant_id, t.c.entity_type == entity_type, t.c.entity_id == entity_id.lower())
                .order_by(t.c.created_at, t.c.id)
            ).all()
        )
        return [m.audit(r) for r in rows]

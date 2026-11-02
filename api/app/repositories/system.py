"""Cross-tenant "system" queries.

These are the ONLY repository functions allowed to read tenant-owned tables without a
tenant argument (Prompt A 2.4). Each carries the reason. A unit test pins this list so a
new one cannot appear unnoticed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, or_, select, text, update

from . import mappers as m
from .base import Ctx
from .models import GRACE_SECONDS, Attempt, Job

ALLOWED_CROSS_TENANT_SYSTEM_FUNCTIONS = (
    "claim_next_job",
    "find_expired_attempts",
    "find_session_by_token_hash",
    "find_participant_by_token_hash",
    "find_attempt_by_token_hash",
)

# Functions that take no tenant id BY DESIGN because they are keyed by a unique id/hash the
# caller already holds, or touch only non-tenant-owned data. Pinned by tests as well.
TENANTLESS_BY_DESIGN = {
    "TenantsRepo": {"create", "find_by_id", "list"},
    "UsersRepo": {"find_by_email"},  # login: emails are globally unique (R1)
    "SessionsRepo": {"delete_by_token_hash", "touch"},  # caller holds the token
    "LoginAttemptsRepo": {
        "record",
        "count_recent_failures",
        "failure_state",
        "clear_failures",
    },  # keyed by email, not tenant-owned
    "JobsRepo": {"claim_next", "complete", "fail", "requeue_stuck"},  # worker owns a claimed job id
}


def claim_next_job(c: Ctx, worker_id: str) -> Job | None:
    """Job loop: claim the oldest queued job across all tenants (workers serve every tenant)."""
    t = c.t["jobs"]
    now = c.clock.now()

    def go(cn: Connection) -> Any:
        if cn.dialect.name == "mssql":
            schema = t.schema or "dbo"
            row = cn.execute(
                text(
                    f"""
                    WITH next_job AS (
                        SELECT TOP (1) * FROM [{schema}].[jobs] WITH (UPDLOCK, READPAST, ROWLOCK)
                        WHERE status = 'queued' AND (run_after IS NULL OR run_after <= :now)
                        ORDER BY created_at, id
                    )
                    UPDATE next_job
                    SET status = 'running', attempts = attempts + 1, started_at = :now, run_after = NULL,
                        locked_at = :now, locked_by = :worker, updated_at = :now
                    OUTPUT inserted.id
                    """  # noqa: S608 - schema is validated as an identifier by Settings
                ),
                {"now": now.replace(tzinfo=None), "worker": worker_id},
            ).first()
            if row is None:
                return None
            return cn.execute(select(t).where(t.c.id == str(row[0]).lower())).first()
        # SQLite (memory backend): single writer, so select-then-update inside one transaction is atomic.
        row = cn.execute(
            select(t)
            .where(t.c.status == "queued", or_(t.c.run_after.is_(None), t.c.run_after <= now))
            .order_by(t.c.created_at, t.c.id)
            .limit(1)
        ).first()
        if row is None:
            return None
        cn.execute(
            update(t)
            .where(t.c.id == row.id, t.c.status == "queued")
            .values(
                status="running",
                attempts=t.c.attempts + 1,
                started_at=now,
                run_after=None,
                locked_at=now,
                locked_by=worker_id,
                updated_at=now,
            )
        )
        return cn.execute(select(t).where(t.c.id == row.id)).first()

    row = c.x.run(go)
    return m.job(row) if row else None


class SystemRepo:
    def __init__(self, c: Ctx) -> None:
        self.c = c

    def claim_next_job(self, worker_id: str) -> Job | None:
        """Job loop: workers serve every tenant, so claiming has no tenant argument."""
        return claim_next_job(self.c, worker_id)

    def find_expired_attempts(self, now: datetime) -> list[Attempt]:
        """Deadline timer: in-progress attempts past ``deadline + 15 s`` in any tenant (global sweep)."""
        t = self.c.t["attempts"]
        cutoff = now - timedelta(seconds=GRACE_SECONDS)
        rows = self.c.x.run(
            lambda cn: cn.execute(
                select(t).where(t.c.status == "in_progress", t.c.deadline_at < cutoff).order_by(t.c.deadline_at, t.c.id)
            ).all()
        )
        return [m.attempt(r) for r in rows]

    def find_session_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        """Auth resolver: the sid cookie arrives before the tenant is known."""
        s, u, tn = self.c.t["sessions"], self.c.t["users"], self.c.t["tenants"]

        def go(cn: Connection) -> Any:
            sess = cn.execute(select(s).where(s.c.token_hash == token_hash)).first()
            if sess is None:
                return None
            usr = cn.execute(select(u).where(u.c.tenant_id == sess.tenant_id, u.c.id == sess.user_id)).first()
            ten = cn.execute(select(tn).where(tn.c.id == sess.tenant_id)).first()
            if usr is None or ten is None:
                return None
            return sess, usr, ten

        res = self.c.x.run(go)
        if res is None:
            return None
        return {"session": m.session(res[0]), "user": m.user(res[1]), "tenant": m.tenant(res[2])}

    def find_participant_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        """Public invite landing: candidates present a link before the tenant is known."""
        p, a, tn = self.c.t["participants"], self.c.t["assessments"], self.c.t["tenants"]

        def go(cn: Connection) -> Any:
            par = cn.execute(select(p).where(p.c.token_hash == token_hash)).first()
            if par is None:
                return None
            ass = cn.execute(select(a).where(a.c.tenant_id == par.tenant_id, a.c.id == par.assessment_id)).first()
            ten = cn.execute(select(tn).where(tn.c.id == par.tenant_id)).first()
            if ass is None or ten is None:
                return None
            return par, ass, ten

        res = self.c.x.run(go)
        if res is None:
            return None
        return {"participant": m.participant(res[0]), "assessment": m.assessment(res[1]), "tenant": m.tenant(res[2])}

    def find_attempt_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        """Exam resume: the aid cookie is presented by anonymous candidates."""
        at, p, a, tn = (self.c.t[n] for n in ("attempts", "participants", "assessments", "tenants"))

        def go(cn: Connection) -> Any:
            att = cn.execute(select(at).where(at.c.attempt_token_hash == token_hash)).first()
            if att is None:
                return None
            par = cn.execute(select(p).where(p.c.tenant_id == att.tenant_id, p.c.id == att.participant_id)).first()
            ass = cn.execute(select(a).where(a.c.tenant_id == att.tenant_id, a.c.id == att.assessment_id)).first()
            ten = cn.execute(select(tn).where(tn.c.id == att.tenant_id)).first()
            if par is None or ass is None or ten is None:
                return None
            return att, par, ass, ten

        res = self.c.x.run(go)
        if res is None:
            return None
        return {
            "attempt": m.attempt(res[0]),
            "participant": m.participant(res[1]),
            "assessment": m.assessment(res[2]),
            "tenant": m.tenant(res[3]),
        }

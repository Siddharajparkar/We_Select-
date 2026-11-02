"""SQLAlchemy Core table definitions mirroring ``migrations/sql/0001_init.sql``.

On SQL Server the tables are created by the T-SQL migration (the source of truth,
including ISJSON checks); this metadata is used for queries and, for the
``memory`` backend (SQLite), to create an equivalent schema with the same
foreign keys, unique constraints, check constraints and filtered unique index.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from .coltypes import GUID, JsonText, UtcDateTime

TABLE_NAMES = (
    "tenants",
    "users",
    "sessions",
    "login_attempts",
    "assessments",
    "questions",
    "participants",
    "attempts",
    "responses",
    "scores",
    "jobs",
    "audit_log",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def build_metadata(schema: str | None) -> MetaData:
    md = MetaData(schema=schema)
    pre = f"{schema}." if schema else ""

    def fk(cols: list[str], target: str, refcols: list[str], **kw: object) -> ForeignKeyConstraint:
        return ForeignKeyConstraint(cols, [f"{pre}{target}.{c}" for c in refcols], **kw)  # type: ignore[arg-type]

    def created_updated() -> list[Column]:  # type: ignore[type-arg]
        return [Column("created_at", UtcDateTime, nullable=False), Column("updated_at", UtcDateTime, nullable=False)]

    Table(
        "tenants",
        md,
        Column("id", GUID, primary_key=True),
        Column("name", String(255), nullable=False),
        Column("status", String(20), nullable=False, server_default="active"),
        *created_updated(),
        CheckConstraint(_in("status", ("active", "suspended")), name="CK_tenants_status"),
    )
    Table(
        "users",
        md,
        Column("id", GUID, primary_key=True),
        Column("tenant_id", GUID, nullable=False),
        Column("name", String(255), nullable=False),
        Column("email", String(320), nullable=False),
        Column("password_hash", String(255), nullable=False),
        Column("role", String(20), nullable=False),
        Column("status", String(20), nullable=False, server_default="active"),
        *created_updated(),
        fk(["tenant_id"], "tenants", ["id"], name="FK_users_tenant"),
        UniqueConstraint("tenant_id", "email", name="UQ_users_tenant_email"),
        UniqueConstraint("email", name="UQ_users_email"),
        UniqueConstraint("tenant_id", "id", name="UQ_users_tenant_id"),
        CheckConstraint(_in("role", ("admin", "recruiter", "reviewer")), name="CK_users_role"),
        CheckConstraint(_in("status", ("active", "disabled")), name="CK_users_status"),
    )
    Table(
        "sessions",
        md,
        Column("id", GUID, primary_key=True),
        Column("tenant_id", GUID, nullable=False),
        Column("user_id", GUID, nullable=False),
        Column("token_hash", String(64), nullable=False),
        Column("expires_at", UtcDateTime, nullable=False),
        Column("created_at", UtcDateTime, nullable=False),
        Column("last_seen_at", UtcDateTime, nullable=False),
        fk(["tenant_id", "user_id"], "users", ["tenant_id", "id"], name="FK_sessions_user", ondelete="CASCADE"),
        UniqueConstraint("token_hash", name="UQ_sessions_token_hash"),
        Index("IX_sessions_user_id", "user_id"),
    )
    Table(
        "login_attempts",
        md,
        Column("id", GUID, primary_key=True),
        Column("email", String(320), nullable=False),
        Column("ip_address", String(45), nullable=False),
        Column("attempted_at", UtcDateTime, nullable=False),
        Column("success", Boolean, nullable=False),
        Index("IX_login_attempts_email", "email", "attempted_at"),
    )
    Table(
        "assessments",
        md,
        Column("id", GUID, primary_key=True),
        Column("tenant_id", GUID, nullable=False),
        Column("title", String(255), nullable=False),
        Column("job_description", Text, nullable=True),
        Column("jd_file_name", String(255), nullable=True),
        Column("duration_minutes", Integer, nullable=False, server_default="60"),
        Column("passing_score", Integer, nullable=False, server_default="60"),
        Column("status", String(20), nullable=False, server_default="draft"),
        Column("sections_json", JsonText, nullable=False),
        Column("created_by", GUID, nullable=False),
        *created_updated(),
        fk(["tenant_id"], "tenants", ["id"], name="FK_assessments_tenant"),
        fk(["tenant_id", "created_by"], "users", ["tenant_id", "id"], name="FK_assessments_creator"),
        UniqueConstraint("tenant_id", "id", name="UQ_assessments_tenant_id"),
        CheckConstraint("duration_minutes BETWEEN 5 AND 240", name="CK_assessments_duration"),
        CheckConstraint("passing_score BETWEEN 0 AND 100", name="CK_assessments_passing_score"),
        CheckConstraint(_in("status", ("draft", "approved", "open", "closed")), name="CK_assessments_status"),
        Index("IX_assessments_tenant_status", "tenant_id", "status"),
    )
    Table(
        "questions",
        md,
        Column("id", GUID, primary_key=True),
        Column("tenant_id", GUID, nullable=False),
        Column("assessment_id", GUID, nullable=False),
        Column("section_index", Integer, nullable=False, server_default="0"),
        Column("type", String(20), nullable=False),
        Column("body", Text, nullable=False),
        Column("options_json", JsonText, nullable=True),
        Column("correct_answer", Text, nullable=True),
        Column("rubric", Text, nullable=True),
        Column("max_score", Integer, nullable=False, server_default="10"),
        Column("source", String(20), nullable=False, server_default="ai"),
        Column("position", Integer, nullable=False, server_default="0"),
        Column("status", String(20), nullable=False, server_default="draft"),
        Column("explanation", Text, nullable=True),
        Column("word_limit", Integer, nullable=True),
        *created_updated(),
        fk(
            ["tenant_id", "assessment_id"],
            "assessments",
            ["tenant_id", "id"],
            name="FK_questions_assessment",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "id", name="UQ_questions_tenant_id"),
        CheckConstraint(_in("type", ("mcq", "descriptive", "cognitive")), name="CK_questions_type"),
        CheckConstraint("max_score BETWEEN 1 AND 20", name="CK_questions_max_score"),
        CheckConstraint(_in("source", ("ai", "custom")), name="CK_questions_source"),
        CheckConstraint(_in("status", ("draft", "approved")), name="CK_questions_status"),
        Index("IX_questions_assessment", "tenant_id", "assessment_id", "position"),
    )
    Table(
        "participants",
        md,
        Column("id", GUID, primary_key=True),
        Column("tenant_id", GUID, nullable=False),
        Column("assessment_id", GUID, nullable=False),
        Column("name", String(255), nullable=False),
        Column("email", String(320), nullable=False),
        Column("invite_status", String(20), nullable=False, server_default="none"),
        Column("token_hash", String(64), nullable=True),
        Column("token_expires_at", UtcDateTime, nullable=True),
        Column("invited_at", UtcDateTime, nullable=True),
        *created_updated(),
        fk(
            ["tenant_id", "assessment_id"],
            "assessments",
            ["tenant_id", "id"],
            name="FK_participants_assessment",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "id", name="UQ_participants_tenant_id"),
        UniqueConstraint("tenant_id", "assessment_id", "email", name="UQ_participants_assessment_email"),
        CheckConstraint(
            _in("invite_status", ("none", "queued", "sent", "failed")), name="CK_participants_invite_status"
        ),
        Index(
            "UQ_participants_token_hash",
            "token_hash",
            unique=True,
            mssql_where=Column("token_hash").isnot(None),
            sqlite_where=Column("token_hash").isnot(None),
        ),
    )
    Table(
        "attempts",
        md,
        Column("id", GUID, primary_key=True),
        Column("tenant_id", GUID, nullable=False),
        Column("participant_id", GUID, nullable=False),
        Column("assessment_id", GUID, nullable=False),
        Column("attempt_token_hash", String(64), nullable=False),
        Column("started_at", UtcDateTime, nullable=False),
        Column("deadline_at", UtcDateTime, nullable=False),
        Column("submitted_at", UtcDateTime, nullable=True),
        Column("status", String(20), nullable=False, server_default="in_progress"),
        Column("score", Numeric(5, 2), nullable=True),
        Column("max_score", Numeric(5, 2), nullable=True),
        Column("percent", Numeric(5, 2), nullable=True),
        Column("passed", Boolean, nullable=True),
        *created_updated(),
        fk(["tenant_id", "participant_id"], "participants", ["tenant_id", "id"], name="FK_attempts_participant"),
        fk(["tenant_id", "assessment_id"], "assessments", ["tenant_id", "id"], name="FK_attempts_assessment"),
        UniqueConstraint("participant_id", name="UQ_attempts_participant"),
        UniqueConstraint("attempt_token_hash", name="UQ_attempts_token_hash"),
        UniqueConstraint("tenant_id", "id", name="UQ_attempts_tenant_id"),
        CheckConstraint(
            _in("status", ("in_progress", "submitted", "scored", "needs_review")), name="CK_attempts_status"
        ),
        Index("IX_attempts_assessment_status", "tenant_id", "assessment_id", "status"),
    )
    Table(
        "responses",
        md,
        Column("id", GUID, primary_key=True),
        Column("tenant_id", GUID, nullable=False),
        Column("attempt_id", GUID, nullable=False),
        Column("question_id", GUID, nullable=False),
        Column("answer_text", Text, nullable=True),
        Column("saved_at", UtcDateTime, nullable=False),
        fk(
            ["tenant_id", "attempt_id"],
            "attempts",
            ["tenant_id", "id"],
            name="FK_responses_attempt",
            ondelete="CASCADE",
        ),
        fk(["tenant_id", "question_id"], "questions", ["tenant_id", "id"], name="FK_responses_question"),
        UniqueConstraint("tenant_id", "id", name="UQ_responses_tenant_id"),
        UniqueConstraint("attempt_id", "question_id", name="UQ_responses_attempt_question"),
    )
    Table(
        "scores",
        md,
        Column("id", GUID, primary_key=True),
        Column("tenant_id", GUID, nullable=False),
        Column("attempt_id", GUID, nullable=False),
        Column("question_id", GUID, nullable=False),
        Column("score", Numeric(5, 2), nullable=False),
        Column("max_score", Numeric(5, 2), nullable=False),
        Column("source", String(20), nullable=False),
        Column("justification", Text, nullable=True),
        *created_updated(),
        fk(["tenant_id", "attempt_id"], "attempts", ["tenant_id", "id"], name="FK_scores_attempt", ondelete="CASCADE"),
        fk(["tenant_id", "question_id"], "questions", ["tenant_id", "id"], name="FK_scores_question"),
        UniqueConstraint("tenant_id", "id", name="UQ_scores_tenant_id"),
        UniqueConstraint("attempt_id", "question_id", name="UQ_scores_attempt_question"),
        CheckConstraint(_in("source", ("auto", "ai", "manual")), name="CK_scores_source"),
    )
    Table(
        "jobs",
        md,
        Column("id", GUID, primary_key=True),
        Column("tenant_id", GUID, nullable=False),
        Column("type", String(20), nullable=False),
        Column("status", String(20), nullable=False, server_default="queued"),
        Column("ref_id", GUID, nullable=False),
        Column("payload_json", JsonText, nullable=False),
        Column("result_json", JsonText, nullable=True),
        Column("error", Text, nullable=True),
        Column("attempts", Integer, nullable=False, server_default="0"),
        Column("max_attempts", Integer, nullable=False, server_default="3"),
        Column("locked_at", UtcDateTime, nullable=True),
        Column("locked_by", String(100), nullable=True),
        Column("run_after", UtcDateTime, nullable=True),
        Column("started_at", UtcDateTime, nullable=True),
        Column("tokens_used", Integer, nullable=False, server_default="0"),
        *created_updated(),
        fk(["tenant_id"], "tenants", ["id"], name="FK_jobs_tenant"),
        CheckConstraint(_in("type", ("generate", "mark", "email")), name="CK_jobs_type"),
        CheckConstraint(_in("status", ("queued", "running", "done", "failed")), name="CK_jobs_status"),
        Index("IX_jobs_claim", "status", "created_at"),
    )
    Table(
        "audit_log",
        md,
        Column("id", GUID, primary_key=True),
        Column("tenant_id", GUID, nullable=False),
        Column("actor_id", GUID, nullable=True),
        Column("action", String(50), nullable=False),
        Column("entity_type", String(50), nullable=False),
        Column("entity_id", GUID, nullable=False),
        Column("details_json", JsonText, nullable=True),
        Column("created_at", UtcDateTime, nullable=False),
        fk(["tenant_id"], "tenants", ["id"], name="FK_audit_log_tenant"),
        Index("IX_audit_log_tenant_entity", "tenant_id", "entity_type", "entity_id"),
    )
    return md

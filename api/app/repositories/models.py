"""Domain models (plain dataclasses), repository errors and shared guards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE)

GRACE_SECONDS = 15  # responses are accepted until deadline + 15 s


class RepositoryError(Exception):
    """Domain-level persistence error. ``code`` is stable; ``str(exc)`` carries it for matching."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def assert_tenant(tenant_id: object) -> str:
    """First line of every tenant-scoped repository function."""
    if not isinstance(tenant_id, str) or not _UUID_RE.match(tenant_id):
        raise ValueError("tenantId required: must be a valid UUID")
    return tenant_id.lower()


UserRole = Literal["admin", "recruiter", "reviewer"]
UserStatus = Literal["active", "disabled"]
AssessmentStatus = Literal["draft", "approved", "open", "closed"]
QuestionType = Literal["mcq", "descriptive", "cognitive"]
QuestionSource = Literal["ai", "custom"]
InviteStatus = Literal["none", "queued", "sent", "failed"]
AttemptStatus = Literal["in_progress", "submitted", "scored", "needs_review"]
ScoreSource = Literal["auto", "ai", "manual"]
JobType = Literal["generate", "mark", "email"]
JobStatus = Literal["queued", "running", "done", "failed"]


@dataclass
class Tenant:
    id: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass
class User:
    id: str
    tenant_id: str
    name: str
    email: str
    password_hash: str
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass
class Session:
    id: str
    tenant_id: str
    user_id: str
    token_hash: str
    expires_at: datetime
    created_at: datetime
    last_seen_at: datetime


@dataclass
class Assessment:
    id: str
    tenant_id: str
    title: str
    job_description: str | None
    jd_file_name: str | None
    duration_minutes: int
    passing_score: int
    status: str
    sections: list[dict[str, Any]]
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass
class AssessmentListItem:
    id: str
    title: str
    status: str
    participant_count: int
    submitted_count: int
    created_at: datetime


@dataclass
class Question:
    id: str
    tenant_id: str
    assessment_id: str
    section_index: int
    type: str
    body: str
    options: list[str] | None
    correct_answer: str | None
    rubric: str | None
    max_score: int
    source: str
    position: int
    status: str
    explanation: str | None
    word_limit: int | None
    created_at: datetime
    updated_at: datetime


@dataclass
class Participant:
    id: str
    tenant_id: str
    assessment_id: str
    name: str
    email: str
    invite_status: str
    token_hash: str | None
    token_expires_at: datetime | None
    invited_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class ParticipantListItem:
    id: str
    name: str
    email: str
    invite_status: str
    attempt_status: str
    percent: float | None


@dataclass
class Attempt:
    id: str
    tenant_id: str
    participant_id: str
    assessment_id: str
    attempt_token_hash: str
    started_at: datetime
    deadline_at: datetime
    submitted_at: datetime | None
    status: str
    score: float | None
    max_score: float | None
    percent: float | None
    passed: bool | None
    created_at: datetime
    updated_at: datetime


@dataclass
class AttemptListItem:
    attempt_id: str
    name: str
    email: str
    score: float | None
    max_score: float | None
    percent: float | None
    passed: bool | None
    time_taken_sec: int | None
    status: str


@dataclass
class Response:
    id: str
    tenant_id: str
    attempt_id: str
    question_id: str
    answer_text: str | None
    saved_at: datetime


@dataclass
class Score:
    id: str
    tenant_id: str
    attempt_id: str
    question_id: str
    score: float
    max_score: float
    source: str
    justification: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class Job:
    id: str
    tenant_id: str
    type: str
    status: str
    ref_id: str
    payload: Any
    result: Any
    error: str | None
    attempts: int
    max_attempts: int
    locked_at: datetime | None
    locked_by: str | None
    run_after: datetime | None
    started_at: datetime | None
    tokens_used: int
    created_at: datetime
    updated_at: datetime


@dataclass
class AuditLogEntry:
    id: str
    tenant_id: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str
    details: Any
    created_at: datetime

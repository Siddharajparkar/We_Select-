"""Row -> dataclass mapping."""

from __future__ import annotations

from typing import Any

from .base import num
from .models import (
    Assessment,
    Attempt,
    AuditLogEntry,
    Job,
    Participant,
    Question,
    Response,
    Score,
    Session,
    Tenant,
    User,
)


def tenant(r: Any) -> Tenant:
    m = r._mapping
    return Tenant(m["id"], m["name"], m["status"], m["created_at"], m["updated_at"])


def user(r: Any) -> User:
    m = r._mapping
    return User(
        m["id"], m["tenant_id"], m["name"], m["email"], m["password_hash"], m["role"], m["status"],
        m["created_at"], m["updated_at"],
    )  # fmt: skip


def session(r: Any) -> Session:
    m = r._mapping
    return Session(
        m["id"], m["tenant_id"], m["user_id"], m["token_hash"], m["expires_at"], m["created_at"], m["last_seen_at"]
    )


def assessment(r: Any) -> Assessment:
    m = r._mapping
    return Assessment(
        m["id"], m["tenant_id"], m["title"], m["job_description"], m["jd_file_name"],
        int(m["duration_minutes"]), int(m["passing_score"]), m["status"], m["sections_json"] or [],
        m["created_by"], m["created_at"], m["updated_at"],
    )  # fmt: skip


def question(r: Any) -> Question:
    m = r._mapping
    return Question(
        m["id"], m["tenant_id"], m["assessment_id"], int(m["section_index"]), m["type"], m["body"],
        m["options_json"], m["correct_answer"], m["rubric"], int(m["max_score"]), m["source"],
        int(m["position"]), m["status"], m["explanation"],
        None if m["word_limit"] is None else int(m["word_limit"]), m["created_at"], m["updated_at"],
    )  # fmt: skip


def participant(r: Any) -> Participant:
    m = r._mapping
    return Participant(
        m["id"], m["tenant_id"], m["assessment_id"], m["name"], m["email"], m["invite_status"],
        m["token_hash"], m["token_expires_at"], m["invited_at"], m["created_at"], m["updated_at"],
    )  # fmt: skip


def attempt(r: Any) -> Attempt:
    m = r._mapping
    return Attempt(
        m["id"], m["tenant_id"], m["participant_id"], m["assessment_id"], m["attempt_token_hash"],
        m["started_at"], m["deadline_at"], m["submitted_at"], m["status"], num(m["score"]),
        num(m["max_score"]), num(m["percent"]), None if m["passed"] is None else bool(m["passed"]),
        m["created_at"], m["updated_at"],
    )  # fmt: skip


def response(r: Any) -> Response:
    m = r._mapping
    return Response(m["id"], m["tenant_id"], m["attempt_id"], m["question_id"], m["answer_text"], m["saved_at"])


def score(r: Any) -> Score:
    m = r._mapping
    return Score(
        m["id"], m["tenant_id"], m["attempt_id"], m["question_id"], float(m["score"]), float(m["max_score"]),
        m["source"], m["justification"], m["created_at"], m["updated_at"],
    )  # fmt: skip


def job(r: Any) -> Job:
    m = r._mapping
    return Job(
        m["id"], m["tenant_id"], m["type"], m["status"], m["ref_id"], m["payload_json"], m["result_json"],
        m["error"], int(m["attempts"]), int(m["max_attempts"]), m["locked_at"], m["locked_by"],
        m["run_after"], m["started_at"], int(m["tokens_used"]), m["created_at"], m["updated_at"],
    )  # fmt: skip


def audit(r: Any) -> AuditLogEntry:
    m = r._mapping
    return AuditLogEntry(
        m["id"], m["tenant_id"], m["actor_id"], m["action"], m["entity_type"], m["entity_id"],
        m["details_json"], m["created_at"],
    )  # fmt: skip

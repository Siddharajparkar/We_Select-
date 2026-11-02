"""Starting AI jobs: checks that run *before* anything is queued (Prompt A 6.2)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ..config import Settings
from ..core.clock import Clock
from ..core.errors import AppError
from ..repositories import Repositories
from ..repositories.models import Assessment, Job
from . import assessments as assessments_svc
from . import questions as questions_svc
from .auth import AuthContext
from .text import count_words

MIN_JD_WORDS = 100


def _guard(repos: Repositories, settings: Settings, clock: Clock, auth: AuthContext, a: Assessment) -> None:
    assessments_svc.require_draft(a, "changed")
    if count_words(a.job_description) < MIN_JD_WORDS:
        raise AppError.unprocessable(
            "JD_TOO_SHORT", f"The job description needs at least {MIN_JD_WORDS} words to generate questions"
        )


def _check_daily_cap(repos: Repositories, settings: Settings, clock: Clock, auth: AuthContext) -> None:
    now = clock.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    wait = max(1, int((midnight - now).total_seconds()))
    if repos.jobs.count_daily_generations(auth.tenant_id, now) >= settings.DAILY_GENERATION_LIMIT:
        raise AppError.too_many_requests(
            "DAILY_AI_LIMIT", f"The daily limit of {settings.DAILY_GENERATION_LIMIT} generations was reached", wait
        )
    if repos.jobs.sum_tokens(auth.tenant_id, now) >= settings.AI_DAILY_TOKEN_CAP:
        raise AppError.too_many_requests("DAILY_AI_LIMIT", "The daily AI usage allowance was reached", wait)


def start_generate(
    repos: Repositories, settings: Settings, clock: Clock, auth: AuthContext, assessment_id: str,
    section_indexes: list[int] | None,
) -> Job:  # fmt: skip
    a = assessments_svc.get_or_404(repos, auth, assessment_id)
    _guard(repos, settings, clock, auth, a)
    if section_indexes is None:
        chosen = list(range(len(a.sections)))
    else:
        bad = [i for i in section_indexes if not 0 <= i < len(a.sections)]
        if not section_indexes or bad or len(set(section_indexes)) != len(section_indexes):
            raise AppError.bad_request(
                "sectionIndexes must list distinct, existing section numbers",
                [{"path": "sectionIndexes", "message": f"valid values are 0..{len(a.sections) - 1}"}],
            )
        chosen = sorted(section_indexes)
    _check_daily_cap(repos, settings, clock, auth)
    job = repos.jobs.enqueue(
        auth.tenant_id, type="generate", ref_id=a.id,
        payload={"mode": "sections", "assessmentId": a.id, "sectionIndexes": chosen, "requestedBy": auth.user_id},
    )  # fmt: skip
    repos.audit.log(auth.tenant_id, action="assessment.generate", entity_type="assessment", entity_id=a.id,
                    actor_id=auth.user_id, details={"jobId": job.id, "sections": chosen})  # fmt: skip
    return job


def start_regenerate(repos: Repositories, settings: Settings, clock: Clock, auth: AuthContext, question_id: str) -> Job:
    q = questions_svc.get_or_404(repos, auth, question_id)
    a = questions_svc.require_draft_question(repos, auth, q, "regenerated")
    if q.source != "ai":
        raise AppError.conflict("CONFLICT", "Only AI-generated questions can be regenerated")
    _guard(repos, settings, clock, auth, a)
    _check_daily_cap(repos, settings, clock, auth)
    job = repos.jobs.enqueue(
        auth.tenant_id, type="generate", ref_id=a.id,
        payload={"mode": "question", "assessmentId": a.id, "questionId": q.id, "requestedBy": auth.user_id},
    )  # fmt: skip
    repos.audit.log(auth.tenant_id, action="question.regenerate", entity_type="question", entity_id=q.id,
                    actor_id=auth.user_id, details={"jobId": job.id})  # fmt: skip
    return job


def job_view(j: Job) -> dict[str, Any]:
    code = j.result.get("code") if j.status == "failed" and isinstance(j.result, dict) else None
    return {
        "id": j.id,
        "type": j.type,
        "status": j.status,
        "attempts": j.attempts,
        "maxAttempts": j.max_attempts,
        "result": j.result if j.status == "done" else None,
        "error": j.error,
        "errorCode": code,
        "tokensUsed": j.tokens_used,
        "createdAt": j.created_at.isoformat().replace("+00:00", "Z"),
        "updatedAt": j.updated_at.isoformat().replace("+00:00", "Z"),
    }


def get_job(repos: Repositories, auth: AuthContext, job_id: str) -> Job:
    j = repos.jobs.find_by_id(auth.tenant_id, job_id)
    if j is None:
        raise AppError.not_found("Job not found")
    return j

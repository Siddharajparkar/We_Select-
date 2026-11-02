"""Assessment use-cases (Prompt A 5.2 - 5.5). Routes stay thin; rules live here."""

from __future__ import annotations

from typing import Any

from ..core.errors import AppError
from ..providers.files_memory import sanitize_file_name
from ..providers.ports import FilesProvider, SaveJdInput
from ..repositories import Repositories
from ..repositories.models import Assessment, RepositoryError
from ..schemas.assessments import AssessmentCreateIn, AssessmentPatchIn
from . import jd_files
from .auth import AuthContext
from .text import count_words


def view(a: Assessment) -> dict[str, Any]:
    return {
        "id": a.id,
        "title": a.title,
        "status": a.status,
        "jobDescription": a.job_description,
        "jdFileName": a.jd_file_name,
        "durationMinutes": a.duration_minutes,
        "passingScore": a.passing_score,
        "sections": a.sections,
        "createdBy": a.created_by,
        "createdAt": a.created_at.isoformat().replace("+00:00", "Z"),
        "updatedAt": a.updated_at.isoformat().replace("+00:00", "Z"),
    }


def get_or_404(repos: Repositories, auth: AuthContext, assessment_id: str) -> Assessment:
    """Another tenant's id is indistinguishable from an unknown one (404)."""
    a = repos.assessments.find_by_id(auth.tenant_id, assessment_id)
    if a is None:
        raise AppError.not_found("Assessment not found")
    return a


def require_draft(a: Assessment, action: str = "edited") -> None:
    if a.status != "draft":
        raise AppError.conflict("CONFLICT", f"Only a draft assessment can be {action}")


def blob_path_for(tenant_id: str, assessment_id: str, file_name: str) -> str:
    return f"{tenant_id}/{assessment_id}/{file_name}"


def create(repos: Repositories, auth: AuthContext, body: AssessmentCreateIn) -> Assessment:
    a = repos.assessments.create(
        auth.tenant_id,
        title=body.title,
        sections=[s.model_dump() for s in body.sections],
        created_by=auth.user_id,
        job_description=body.jobDescription,
        duration_minutes=body.durationMinutes,
        passing_score=body.passingScore,
    )
    repos.audit.log(
        auth.tenant_id, action="assessment.create", entity_type="assessment", entity_id=a.id, actor_id=auth.user_id
    )
    return a


def _section_warnings(repos: Repositories, auth: AuthContext, a: Assessment, new: list[dict[str, Any]]) -> list[str]:
    """Existing AI questions of changed/removed sections are kept; tell the caller (Phase 6 regenerates)."""
    changed = {i for i in range(max(len(a.sections), len(new))) if a.sections[i : i + 1] != new[i : i + 1]}
    if not changed:
        return []
    per_section: dict[int, int] = {}
    for q in repos.questions.list_by_assessment(auth.tenant_id, a.id):
        if q.source == "ai" and q.section_index in changed:
            per_section[q.section_index] = per_section.get(q.section_index, 0) + 1
    return [
        f"Section {i + 1} was changed or removed but {n} existing AI question(s) were kept; regenerate to match."
        for i, n in sorted(per_section.items())
    ]


def patch(
    repos: Repositories, auth: AuthContext, assessment_id: str, body: AssessmentPatchIn
) -> tuple[Assessment, list[str]]:
    a = get_or_404(repos, auth, assessment_id)
    require_draft(a)
    fields: dict[str, Any] = {}
    sent = body.model_fields_set
    if "title" in sent:
        fields["title"] = body.title
    if "jobDescription" in sent:
        fields["job_description"] = body.jobDescription
    if "durationMinutes" in sent:
        fields["duration_minutes"] = body.durationMinutes
    if "passingScore" in sent:
        fields["passing_score"] = body.passingScore
    warnings: list[str] = []
    if "sections" in sent and body.sections is not None:
        new_sections = [s.model_dump() for s in body.sections]
        fields["sections"] = new_sections
        warnings = _section_warnings(repos, auth, a, new_sections)
    updated = repos.assessments.update(auth.tenant_id, a.id, **fields)
    if updated is None:  # deleted concurrently
        raise AppError.not_found("Assessment not found")
    repos.audit.log(auth.tenant_id, action="assessment.update", entity_type="assessment", entity_id=a.id,
                    actor_id=auth.user_id, details={"fields": sorted(sent)})  # fmt: skip
    return updated, warnings


def delete(repos: Repositories, files: FilesProvider, auth: AuthContext, assessment_id: str) -> None:
    from ..core.logging import logger

    a = get_or_404(repos, auth, assessment_id)
    require_draft(a, "deleted")
    try:
        repos.assessments.delete(auth.tenant_id, a.id)
    except RepositoryError as exc:
        if exc.code == "IN_USE":
            raise AppError.conflict("CONFLICT", "Assessment has dependent records and cannot be deleted") from None
        raise
    if a.jd_file_name:  # best effort: the row is already gone
        try:
            files.delete_jd(blob_path_for(auth.tenant_id, a.id, a.jd_file_name))
        except Exception:
            logger.warn("could not delete job description blob", assessment_id=a.id)
    repos.audit.log(
        auth.tenant_id, action="assessment.delete", entity_type="assessment", entity_id=a.id, actor_id=auth.user_id
    )


def upload_jd(
    repos: Repositories, files: FilesProvider, auth: AuthContext, assessment_id: str, file_name: str, content: bytes
) -> dict[str, Any]:
    from ..core.logging import logger

    a = get_or_404(repos, auth, assessment_id)
    require_draft(a, "changed")
    kind = jd_files.detect_kind(file_name, content)
    text = jd_files.extract_text(kind, content)
    safe_name = sanitize_file_name(file_name)
    new_path = blob_path_for(auth.tenant_id, a.id, safe_name)
    old_path = blob_path_for(auth.tenant_id, a.id, a.jd_file_name) if a.jd_file_name else None

    saved = files.save_jd(SaveJdInput(auth.tenant_id, a.id, safe_name, content))
    if saved != new_path:  # the provider owns the layout; fail loudly if it ever diverges
        files.delete_jd(saved)
        raise AppError.internal()
    try:
        repos.assessments.update(auth.tenant_id, a.id, job_description=text, jd_file_name=safe_name)
    except Exception:
        try:
            if new_path != old_path:
                files.delete_jd(new_path)  # do not leave an orphan blob behind
        except Exception:
            logger.warn("could not remove orphan blob after failed update", assessment_id=a.id)
        raise
    if old_path and old_path != new_path:
        try:
            files.delete_jd(old_path)
        except Exception:
            logger.warn("could not delete replaced blob", assessment_id=a.id)
    repos.audit.log(auth.tenant_id, action="assessment.jd_upload", entity_type="assessment", entity_id=a.id,
                    actor_id=auth.user_id, details={"bytes": len(content), "kind": kind})  # fmt: skip
    return {"fileName": safe_name, "wordCount": count_words(text), "jobDescription": text}


def close(repos: Repositories, auth: AuthContext, assessment_id: str) -> Assessment:
    a = get_or_404(repos, auth, assessment_id)
    if a.status not in ("approved", "open"):
        raise AppError.conflict("CONFLICT", "Only an approved or open assessment can be closed")
    updated = repos.assessments.update(auth.tenant_id, a.id, status="closed")
    assert updated is not None
    repos.audit.log(
        auth.tenant_id, action="assessment.close", entity_type="assessment", entity_id=a.id, actor_id=auth.user_id
    )
    return updated

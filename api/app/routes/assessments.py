from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Query, Response, UploadFile

from ..core.errors import AppError
from ..deps import Prov, Repos, Staff
from ..schemas.assessments import AssessmentCreateIn, AssessmentPatchIn, Status
from ..schemas.common import UuidPath
from ..services import assessments as svc
from ..services.jd_files import MAX_FILE_BYTES

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("", status_code=201)
def create_assessment(body: AssessmentCreateIn, auth: Staff, repos: Repos) -> dict[str, str]:
    a = svc.create(repos, auth, body)
    return {"id": a.id, "status": a.status}


@router.get("")
def list_assessments(
    auth: Staff, repos: Repos, status: Annotated[Status | None, Query()] = None
) -> list[dict[str, Any]]:
    return [
        {
            "id": i.id,
            "title": i.title,
            "status": i.status,
            "participantCount": i.participant_count,
            "submittedCount": i.submitted_count,
            "createdAt": i.created_at.isoformat().replace("+00:00", "Z"),
        }
        for i in repos.assessments.list(auth.tenant_id, status)
    ]


@router.get("/{assessment_id}")
def get_assessment(assessment_id: UuidPath, auth: Staff, repos: Repos) -> dict[str, Any]:
    return svc.view(svc.get_or_404(repos, auth, assessment_id))


@router.patch("/{assessment_id}")
def patch_assessment(assessment_id: UuidPath, body: AssessmentPatchIn, auth: Staff, repos: Repos) -> dict[str, Any]:
    updated, warnings = svc.patch(repos, auth, assessment_id, body)
    return {**svc.view(updated), "warnings": warnings}


@router.delete("/{assessment_id}", status_code=204)
def delete_assessment(assessment_id: UuidPath, auth: Staff, repos: Repos, providers: Prov) -> Response:
    svc.delete(repos, providers.files, auth, assessment_id)
    return Response(status_code=204)


@router.post("/{assessment_id}/jd-file")
def upload_jd_file(
    assessment_id: UuidPath, auth: Staff, repos: Repos, providers: Prov, file: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    svc.get_or_404(repos, auth, assessment_id)  # 404 before reading the body into memory
    content = file.file.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise AppError.bad_request("The file is larger than the 2 MB limit")
    return svc.upload_jd(repos, providers.files, auth, assessment_id, file.filename or "file", content)


@router.post("/{assessment_id}/close")
def close_assessment(assessment_id: UuidPath, auth: Staff, repos: Repos) -> dict[str, str]:
    a = svc.close(repos, auth, assessment_id)
    return {"id": a.id, "status": a.status}

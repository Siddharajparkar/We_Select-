"""Endpoints 15-22: AI generation, jobs, questions and approval (Prompt B)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from ..deps import Cfg, Clk, Repos, Staff
from ..schemas.common import UuidPath
from ..schemas.questions import GenerateIn, QuestionCreateIn, QuestionPatchIn
from ..services import generation as gen
from ..services import questions as svc

router = APIRouter(tags=["generation"])


@router.post("/assessments/{assessment_id}/generate", status_code=202)
def generate(
    assessment_id: UuidPath, body: GenerateIn, auth: Staff, repos: Repos, cfg: Cfg, clock: Clk
) -> dict[str, str]:
    job = gen.start_generate(repos, cfg, clock, auth, assessment_id, body.sectionIndexes)
    return {"jobId": job.id, "status": job.status}


@router.get("/jobs/{job_id}")
def get_job(job_id: UuidPath, auth: Staff, repos: Repos) -> dict[str, Any]:
    return gen.job_view(gen.get_job(repos, auth, job_id))


@router.get("/assessments/{assessment_id}/questions")
def list_questions(assessment_id: UuidPath, auth: Staff, repos: Repos) -> list[dict[str, Any]]:
    return svc.list_for(repos, auth, assessment_id)


@router.post("/assessments/{assessment_id}/questions", status_code=201)
def add_question(assessment_id: UuidPath, body: QuestionCreateIn, auth: Staff, repos: Repos) -> dict[str, Any]:
    return svc.view(svc.add(repos, auth, assessment_id, body))


@router.patch("/questions/{question_id}")
def patch_question(question_id: UuidPath, body: QuestionPatchIn, auth: Staff, repos: Repos) -> dict[str, Any]:
    return svc.view(svc.patch(repos, auth, question_id, body))


@router.delete("/questions/{question_id}", status_code=204)
def delete_question(question_id: UuidPath, auth: Staff, repos: Repos) -> Response:
    svc.delete(repos, auth, question_id)
    return Response(status_code=204)


@router.post("/questions/{question_id}/regenerate", status_code=202)
def regenerate_question(question_id: UuidPath, auth: Staff, repos: Repos, cfg: Cfg, clock: Clk) -> dict[str, str]:
    job = gen.start_regenerate(repos, cfg, clock, auth, question_id)
    return {"jobId": job.id, "status": job.status}


@router.post("/assessments/{assessment_id}/approve")
def approve(assessment_id: UuidPath, auth: Staff, repos: Repos) -> dict[str, Any]:
    return svc.approve(repos, auth, assessment_id)

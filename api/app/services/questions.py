"""Question use-cases: list, add, edit, delete and approve (Prompt A 6.x)."""

from __future__ import annotations

from typing import Any

from ..core.errors import AppError
from ..repositories import Repositories
from ..repositories.models import Assessment, Question, RepositoryError
from ..schemas.questions import MAX_PER_SECTION, MAX_TOTAL, OBJECTIVE, QuestionCreateIn, QuestionPatchIn, check_fields
from . import assessments as assessments_svc
from .auth import AuthContext


def view(q: Question) -> dict[str, Any]:
    return {
        "id": q.id,
        "assessmentId": q.assessment_id,
        "sectionIndex": q.section_index,
        "type": q.type,
        "body": q.body,
        "options": q.options,
        "correctAnswer": q.correct_answer,
        "explanation": q.explanation,
        "rubric": q.rubric,
        "maxScore": q.max_score,
        "wordLimit": q.word_limit,
        "source": q.source,
        "status": q.status,
        "position": q.position,
    }


def get_or_404(repos: Repositories, auth: AuthContext, question_id: str) -> Question:
    q = repos.questions.find_by_id(auth.tenant_id, question_id)
    if q is None:
        raise AppError.not_found("Question not found")
    return q


def require_draft_question(repos: Repositories, auth: AuthContext, q: Question, action: str) -> Assessment:
    a = repos.assessments.find_by_id(auth.tenant_id, q.assessment_id)
    if a is None:
        raise AppError.not_found("Question not found")
    if a.status != "draft" or q.status != "draft":
        raise AppError.conflict("CONFLICT", f"Questions of an approved assessment cannot be {action}")
    return a


def list_for(repos: Repositories, auth: AuthContext, assessment_id: str) -> list[dict[str, Any]]:
    a = assessments_svc.get_or_404(repos, auth, assessment_id)
    return [view(q) for q in repos.questions.list_by_assessment(auth.tenant_id, a.id)]


def add(repos: Repositories, auth: AuthContext, assessment_id: str, body: QuestionCreateIn) -> Question:
    a = assessments_svc.get_or_404(repos, auth, assessment_id)
    assessments_svc.require_draft(a, "changed")
    if body.sectionIndex >= len(a.sections):
        raise AppError.bad_request(
            "sectionIndex does not exist in this assessment", [{"path": "sectionIndex", "message": "out of range"}]
        )
    if a.sections[body.sectionIndex]["type"] != body.type:
        raise AppError.bad_request(
            f"Section {body.sectionIndex + 1} holds {a.sections[body.sectionIndex]['type']} questions",
            [{"path": "type", "message": "does not match the section type"}],
        )
    existing = repos.questions.list_by_assessment(auth.tenant_id, a.id)
    if sum(1 for q in existing if q.section_index == body.sectionIndex) >= MAX_PER_SECTION:
        raise AppError.conflict("CONFLICT", f"A section can hold at most {MAX_PER_SECTION} questions")
    if len(existing) >= MAX_TOTAL:
        raise AppError.conflict("CONFLICT", f"An assessment can hold at most {MAX_TOTAL} questions")
    in_section = [q.position for q in existing if q.section_index == body.sectionIndex]
    objective = body.type in OBJECTIVE
    q = repos.questions.create(
        auth.tenant_id,
        assessment_id=a.id,
        section_index=body.sectionIndex,
        type=body.type,
        body=body.body,
        options=body.options if objective else None,
        correct_answer=body.correctAnswer if objective else None,
        explanation=body.explanation if objective else None,
        rubric=None if objective else body.rubric,
        max_score=body.maxScore or (1 if objective else 10),
        word_limit=None if objective else (body.wordLimit or 250),
        source="custom",
        position=(max(in_section) + 1) if in_section else 0,
    )
    repos.audit.log(auth.tenant_id, action="question.create", entity_type="question", entity_id=q.id,
                    actor_id=auth.user_id, details={"assessmentId": a.id})  # fmt: skip
    return q


def patch(repos: Repositories, auth: AuthContext, question_id: str, body: QuestionPatchIn) -> Question:
    q = get_or_404(repos, auth, question_id)
    require_draft_question(repos, auth, q, "edited")
    sent = body.model_fields_set
    merged = {
        "options": q.options, "correctAnswer": q.correct_answer, "rubric": q.rubric, "wordLimit": q.word_limit,
        **{k: getattr(body, k) for k in sent},
    }  # fmt: skip
    problem = check_fields(q.type, merged)
    if problem:
        raise AppError.bad_request(problem, [{"path": sorted(sent)[0], "message": problem}])
    fields: dict[str, Any] = {}
    for api_name, repo_name in (
        ("body", "body"), ("options", "options"), ("correctAnswer", "correct_answer"),
        ("explanation", "explanation"), ("rubric", "rubric"), ("maxScore", "max_score"), ("wordLimit", "word_limit"),
    ):  # fmt: skip
        if api_name in sent:
            fields[repo_name] = getattr(body, api_name)
    updated = repos.questions.update(auth.tenant_id, q.id, **fields)
    if updated is None:
        raise AppError.not_found("Question not found")
    repos.audit.log(auth.tenant_id, action="question.update", entity_type="question", entity_id=q.id,
                    actor_id=auth.user_id, details={"fields": sorted(sent)})  # fmt: skip
    return updated


def delete(repos: Repositories, auth: AuthContext, question_id: str) -> None:
    q = get_or_404(repos, auth, question_id)
    require_draft_question(repos, auth, q, "deleted")
    repos.questions.delete(auth.tenant_id, q.id)
    repos.audit.log(auth.tenant_id, action="question.delete", entity_type="question", entity_id=q.id,
                    actor_id=auth.user_id, details={"assessmentId": q.assessment_id})  # fmt: skip


def approve(repos: Repositories, auth: AuthContext, assessment_id: str) -> dict[str, Any]:
    """Draft -> approved. Every section must hold exactly its configured number of questions (R5)."""
    a = assessments_svc.get_or_404(repos, auth, assessment_id)
    assessments_svc.require_draft(a, "approved")
    questions = repos.questions.list_by_assessment(auth.tenant_id, a.id)
    if not questions:
        raise AppError.conflict("NO_QUESTIONS", "Add or generate questions before approving")
    have: dict[int, int] = {}
    for q in questions:
        have[q.section_index] = have.get(q.section_index, 0) + 1
    problems = []
    for i, section in enumerate(a.sections):
        if have.get(i, 0) != section["count"]:
            problems.append(
                {"path": f"sections[{i}]", "message": f"has {have.get(i, 0)} of {section['count']} questions"}
            )
    for i in sorted(set(have) - set(range(len(a.sections)))):
        problems.append({"path": f"sections[{i}]", "message": "has questions but no longer exists in the assessment"})
    if problems:
        raise AppError.conflict(
            "SECTION_INCOMPLETE", "Every section must have exactly its configured number of questions", problems
        )
    try:
        count = repos.questions.approve_all(auth.tenant_id, a.id)
    except RepositoryError as exc:
        if exc.code == "NOT_DRAFT":
            raise AppError.conflict("CONFLICT", "Only a draft assessment can be approved") from None
        raise
    repos.audit.log(auth.tenant_id, action="assessment.approve", entity_type="assessment", entity_id=a.id,
                    actor_id=auth.user_id, details={"questions": count})  # fmt: skip
    return {"id": a.id, "status": "approved", "questionCount": count}

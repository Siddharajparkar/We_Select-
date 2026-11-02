"""Job handlers. Phase 6 registers ``generate``; ``mark`` (Phase 9) and ``email`` (Phase 7) come later."""

from __future__ import annotations

from typing import Any

from ..ai.validator import drop_duplicates
from ..providers.ports import GeneratedQuestion, GenerateQuestionsInput, ProviderError
from ..repositories.models import Question, RepositoryError
from ..services.text import count_words
from .engine import Handler, JobContext, JobError, JobOutcome, NonRetryableJobError

BATCH_SIZE = 5  # questions requested per model call keeps the answer well inside the output-token limit
MIN_JD_WORDS = 100
MAX_DUPLICATE_RETRIES = 3


def _provider_error(exc: ProviderError, tokens: int) -> JobError:
    if exc.code == "TIMEOUT":
        return JobError("The AI service took too long to answer.", code="AI_TIMEOUT", tokens_used=tokens)
    if exc.code == "RATE_LIMITED":
        return JobError(
            "The AI service is busy right now.", code="AI_RATE_LIMITED", retry_after=exc.retry_after, tokens_used=tokens
        )
    if exc.code == "INVALID_RESPONSE":
        return NonRetryableJobError(
            "The AI could not produce usable questions after 3 attempts. Try again or refine the job description.",
            code="AI_OUTPUT_INVALID",
            tokens_used=tokens,
        )
    return JobError("The AI service is temporarily unavailable.", code="AI_UNAVAILABLE", tokens_used=tokens)


class _Ai:
    """Calls the provider, accumulating tokens and translating failures into job errors."""

    def __init__(self, ctx: JobContext, jd: str) -> None:
        self.ctx, self.jd, self.tokens = ctx, jd, 0

    def questions(
        self, section: dict[str, Any], count: int, existing: list[str]
    ) -> tuple[list[GeneratedQuestion], int]:
        """Up to ``count`` new, non-duplicate questions for ``section``. Returns (questions, duplicates dropped)."""
        collected: list[GeneratedQuestion] = []
        dropped_total = 0
        remaining = count
        empty_rounds = 0
        while remaining > 0 and empty_rounds < MAX_DUPLICATE_RETRIES:
            want = min(BATCH_SIZE, remaining)
            try:
                got, tokens = self.ctx.providers.ai.generate_questions_with_usage(
                    GenerateQuestionsInput(self.jd, section["type"], section["domain"], section["difficulty"], want)
                )
            except ProviderError as exc:
                raise _provider_error(exc, self.tokens) from None
            self.tokens += tokens
            got = got[:want]  # never accept more than was asked for
            kept, dropped = drop_duplicates(got, existing + [c.question for c in collected])
            dropped_total += dropped
            collected += kept
            remaining -= len(kept)
            empty_rounds = 0 if kept else empty_rounds + 1
            if len(got) < want and not kept:
                break
        return collected, dropped_total


def _row(q: GeneratedQuestion) -> dict[str, Any]:
    objective = q.type in ("mcq", "cognitive")
    return {
        "type": q.type,
        "body": q.question,
        "options": q.options if objective else None,
        "correct_answer": q.correct if objective else None,
        "explanation": q.explanation if objective else None,
        "rubric": None if objective else q.rubric,
        "max_score": 1 if objective else (q.max_score or 10),
        "word_limit": None if objective else (q.word_limit or 250),
    }


def _load(ctx: JobContext) -> tuple[dict[str, Any], Any, list[Question]]:
    payload = ctx.job.payload or {}
    a = ctx.repos.assessments.find_by_id(ctx.job.tenant_id, str(payload.get("assessmentId", "")))
    if a is None:
        raise NonRetryableJobError("The assessment no longer exists.", code="NOT_FOUND")
    if a.status != "draft":
        raise NonRetryableJobError("The assessment was approved before generation finished.", code="CONFLICT")
    if count_words(a.job_description) < MIN_JD_WORDS:
        raise NonRetryableJobError("The job description is too short to generate questions.", code="JD_TOO_SHORT")
    return payload, a, ctx.repos.questions.list_by_assessment(ctx.job.tenant_id, a.id)


def _generate_sections(ctx: JobContext) -> JobOutcome:
    payload, a, existing = _load(ctx)
    ai = _Ai(ctx, a.job_description)
    chosen: list[int] = [i for i in payload.get("sectionIndexes", []) if 0 <= i < len(a.sections)]
    replaced = set(chosen)
    # What stays (custom questions, AI questions of untouched sections) must not be duplicated.
    keep_bodies = [q.body for q in existing if not (q.section_index in replaced and q.source == "ai")]
    per_section: dict[int, list[dict[str, Any]]] = {}
    report: list[dict[str, Any]] = []
    warnings: list[str] = []
    for idx in chosen:
        section = a.sections[idx]
        kept_here = sum(1 for q in existing if q.section_index == idx and q.source != "ai")
        need = max(0, section["count"] - kept_here)
        new: list[GeneratedQuestion] = []
        dropped = 0
        if need:
            new, dropped = ai.questions(section, need, keep_bodies)
            if not new:
                raise NonRetryableJobError(
                    f"The AI returned nothing usable for section {idx + 1}. Try again or refine the job description.",
                    code="AI_OUTPUT_INVALID",
                    tokens_used=ai.tokens,
                )
            keep_bodies += [q.question for q in new]
        per_section[idx] = [_row(q) for q in new]
        note = {"sectionIndex": idx, "requested": need, "created": len(new), "duplicatesDropped": dropped}
        report.append(note)
        if len(new) < need:
            warnings.append(f"Section {idx + 1}: only {len(new)} of {need} questions could be generated.")
    try:
        created = ctx.repos.questions.replace_ai_in_sections(ctx.job.tenant_id, a.id, per_section)
    except RepositoryError as exc:
        raise NonRetryableJobError(
            "The assessment changed while questions were being generated.", code="CONFLICT", tokens_used=ai.tokens
        ) from exc
    return JobOutcome(
        {"questionsCreated": len(created), "sections": report, "warnings": warnings}, tokens_used=ai.tokens
    )


def _regenerate_question(ctx: JobContext) -> JobOutcome:
    payload, a, existing = _load(ctx)
    old = next((q for q in existing if q.id == str(payload.get("questionId", "")).lower()), None)
    if old is None:
        raise NonRetryableJobError("The question no longer exists.", code="NOT_FOUND")
    if old.source != "ai" or old.status != "draft":
        raise NonRetryableJobError("Only AI-generated draft questions can be regenerated.", code="CONFLICT")
    section = a.sections[old.section_index]
    ai = _Ai(ctx, a.job_description)
    new, _ = ai.questions(section, 1, [q.body for q in existing])  # includes the old text: the result must differ
    if not new:
        raise NonRetryableJobError(
            "The AI kept producing the same question. Try again.", code="AI_OUTPUT_INVALID", tokens_used=ai.tokens
        )
    row = _row(new[0])
    updated = ctx.repos.questions.update(ctx.job.tenant_id, old.id, **{k: v for k, v in row.items() if k != "type"})
    if updated is None:
        raise NonRetryableJobError("The question no longer exists.", code="NOT_FOUND", tokens_used=ai.tokens)
    return JobOutcome({"questionId": old.id, "questionsCreated": 1, "warnings": []}, tokens_used=ai.tokens)


def generate_handler(ctx: JobContext) -> JobOutcome:
    mode = (ctx.job.payload or {}).get("mode")
    if mode == "question":
        return _regenerate_question(ctx)
    return _generate_sections(ctx)


def default_handlers() -> dict[str, Handler]:
    return {"generate": generate_handler}

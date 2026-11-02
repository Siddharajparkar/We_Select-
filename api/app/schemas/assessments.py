"""Request schemas for assessments (Prompt A 5.1)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

MAX_JD_CHARS = 20_000
MAX_TOTAL_QUESTIONS = 40
MAX_PER_SECTION = 20
MAX_SECTIONS = 10

QuestionType = Literal["mcq", "descriptive", "cognitive"]
Difficulty = Literal["easy", "medium", "hard"]
Status = Literal["draft", "approved", "open", "closed"]


class SectionIn(BaseModel):
    type: QuestionType
    domain: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    difficulty: Difficulty
    count: Annotated[int, Field(ge=1, le=MAX_PER_SECTION)]


def _check_total(sections: list[SectionIn]) -> list[SectionIn]:
    total = sum(s.count for s in sections)
    if total > MAX_TOTAL_QUESTIONS:
        raise ValueError(f"sections.count must add up to at most {MAX_TOTAL_QUESTIONS} (got {total})")
    return sections


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Sections = Annotated[list[SectionIn], Field(min_length=1, max_length=MAX_SECTIONS)]


class AssessmentCreateIn(BaseModel):
    title: Title
    jobDescription: Annotated[str, StringConstraints(max_length=MAX_JD_CHARS)] | None = None
    durationMinutes: Annotated[int, Field(ge=5, le=240)]
    passingScore: Annotated[int, Field(ge=0, le=100)]
    sections: Sections

    @model_validator(mode="after")
    def _total(self) -> AssessmentCreateIn:
        _check_total(self.sections)
        return self


class AssessmentPatchIn(BaseModel):
    title: Title | None = None
    jobDescription: Annotated[str, StringConstraints(max_length=MAX_JD_CHARS)] | None = None
    durationMinutes: Annotated[int, Field(ge=5, le=240)] | None = None
    passingScore: Annotated[int, Field(ge=0, le=100)] | None = None
    sections: Sections | None = None

    @model_validator(mode="after")
    def _rules(self) -> AssessmentPatchIn:
        if not self.model_fields_set:
            raise ValueError("provide at least one field to change")
        for name in ("title", "durationMinutes", "passingScore", "sections"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        if self.sections is not None:
            _check_total(self.sections)
        return self

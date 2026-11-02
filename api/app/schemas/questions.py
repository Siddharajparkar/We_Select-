"""Request schemas and field rules for questions (Prompt A 6.x)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from .assessments import QuestionType

BodyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
OptionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
MAX_PER_SECTION = 20
MAX_TOTAL = 40
OBJECTIVE = ("mcq", "cognitive")


class GenerateIn(BaseModel):
    sectionIndexes: list[int] | None = None


class QuestionFields(BaseModel):
    body: BodyText | None = None
    options: list[OptionText] | None = None
    correctAnswer: Literal["A", "B", "C", "D"] | None = None
    explanation: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    rubric: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)] | None = None
    maxScore: Annotated[int, Field(ge=1, le=20)] | None = None
    wordLimit: Annotated[int, Field(ge=10, le=2000)] | None = None


class QuestionCreateIn(QuestionFields):
    sectionIndex: Annotated[int, Field(ge=0, le=9)]
    type: QuestionType
    body: BodyText  # type: ignore[assignment]

    @model_validator(mode="after")
    def _rules(self) -> QuestionCreateIn:
        problem = check_fields(self.type, self.model_dump(exclude_none=True))
        if problem:
            raise ValueError(problem)
        return self


class QuestionPatchIn(QuestionFields):
    @model_validator(mode="after")
    def _some(self) -> QuestionPatchIn:
        if not self.model_fields_set:
            raise ValueError("provide at least one field to change")
        for name in self.model_fields_set:
            if name != "explanation" and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


def check_fields(kind: str, v: dict[str, Any]) -> str | None:
    """Cross-field rules for one question of ``kind``. Returns a message or None when fine."""
    if kind in OBJECTIVE:
        opts = v.get("options")
        if not isinstance(opts, list) or len(opts) != 4:
            return "options must contain exactly 4 choices"
        if len({o.lower() for o in opts}) != 4:
            return "options must be different from each other"
        if v.get("correctAnswer") not in ("A", "B", "C", "D"):
            return "correctAnswer must be one of A, B, C, D"
        if v.get("rubric") is not None or v.get("wordLimit") is not None:
            return "rubric and wordLimit apply to descriptive questions only"
        return None
    if v.get("options") is not None or v.get("correctAnswer") is not None:
        return "options and correctAnswer apply to multiple-choice questions only"
    if not v.get("rubric"):
        return "a descriptive question needs a rubric (at least 10 characters)"
    return None

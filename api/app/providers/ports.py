"""Provider ports (interfaces) for AI, email and file storage.

Real Azure implementations: ``ai_azure.py``, ``email_azure.py``, ``files_azure.py``.
Fakes for dev/test: ``ai_fake.py``, ``email_fake.py``, ``files_memory.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

QuestionKind = Literal["mcq", "cognitive", "descriptive"]


@dataclass
class GeneratedQuestion:
    type: QuestionKind
    question: str
    options: list[str] | None = None
    correct: str | None = None  # A|B|C|D for mcq / cognitive
    explanation: str | None = None
    rubric: str | None = None  # descriptive
    max_score: int | None = None  # descriptive
    word_limit: int | None = None  # descriptive


@dataclass
class GenerateQuestionsInput:
    job_description: str
    type: QuestionKind
    domain: str
    difficulty: Literal["easy", "medium", "hard"]
    count: int


@dataclass
class MarkAnswerInput:
    question: str
    rubric: str
    max_score: int
    answer: str


@dataclass
class MarkAnswerResult:
    score: float
    justification: str


@dataclass
class SendInviteInput:
    to: str
    name: str
    title: str
    duration_minutes: int
    link: str
    expires_at: datetime


@dataclass
class SendInviteResult:
    message_id: str


@dataclass
class SaveJdInput:
    tenant_id: str
    assessment_id: str
    file_name: str
    content: bytes
    content_type: str = "application/octet-stream"


class ProviderError(Exception):
    """Raised by providers; ``code`` is one of TIMEOUT, RATE_LIMITED, INVALID_RESPONSE, UPSTREAM."""

    def __init__(self, message: str, code: str = "UPSTREAM", retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class AiProvider(Protocol):
    def generate_questions(self, data: GenerateQuestionsInput) -> list[GeneratedQuestion]: ...
    def generate_questions_with_usage(self, data: GenerateQuestionsInput) -> tuple[list[GeneratedQuestion], int]:
        """Same as ``generate_questions`` plus the total tokens spent (all attempts)."""
        ...

    def mark_answer(self, data: MarkAnswerInput) -> MarkAnswerResult: ...


class EmailProvider(Protocol):
    def send_invite(self, data: SendInviteInput) -> SendInviteResult: ...


class FilesProvider(Protocol):
    def save_jd(self, data: SaveJdInput) -> str: ...
    def get_jd(self, path: str) -> bytes: ...
    def delete_jd(self, path: str) -> None: ...


@dataclass
class Providers:
    ai: AiProvider
    email: EmailProvider
    files: FilesProvider
    extras: dict[str, object] = field(default_factory=dict)

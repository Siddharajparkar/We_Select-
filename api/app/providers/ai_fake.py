"""Scriptable fake AI provider (deterministic)."""

from __future__ import annotations

from .ports import (
    GeneratedQuestion,
    GenerateQuestionsInput,
    MarkAnswerInput,
    MarkAnswerResult,
    ProviderError,
)


class FakeAiProvider:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.fail_count = 0  # fail N times, then succeed
        self.return_invalid_json = False
        self.simulate_timeout = False
        self.simulate_429 = False
        self.partial_count: int | None = None
        self.call_count = 0
        self._serial = 0  # distinct topic words per question, so de-duplication never drops fake output
        self.calls: list[GenerateQuestionsInput] = []
        self.tokens_per_question = 50
        self.script: list[list[GeneratedQuestion]] = []  # optional canned answers, consumed in order

    def _topic(self) -> str:
        self._serial += 1
        return " ".join(f"topic{self._serial}x{k}" for k in range(5))

    def _maybe_fail(self, what: str) -> None:
        if self.simulate_timeout:
            raise ProviderError(f"{what} timed out", "TIMEOUT")
        if self.simulate_429:
            raise ProviderError("AI rate limited", "RATE_LIMITED", retry_after=2)
        if self.return_invalid_json:
            raise ProviderError("Invalid JSON returned from AI", "INVALID_RESPONSE")
        if self.fail_count > 0:
            self.fail_count -= 1
            raise ProviderError("Fake AI transient failure", "UPSTREAM")

    def generate_questions(self, data: GenerateQuestionsInput) -> list[GeneratedQuestion]:
        return self.generate_questions_with_usage(data)[0]

    def generate_questions_with_usage(self, data: GenerateQuestionsInput) -> tuple[list[GeneratedQuestion], int]:
        out = self._generate(data)
        return out, self.tokens_per_question * len(out)

    def _generate(self, data: GenerateQuestionsInput) -> list[GeneratedQuestion]:
        self.call_count += 1
        self.calls.append(data)
        self._maybe_fail("AI call")
        if self.script:
            return self.script.pop(0)
        count = data.count if self.partial_count is None else self.partial_count
        out: list[GeneratedQuestion] = []
        for i in range(count):
            if data.type in ("mcq", "cognitive"):
                out.append(
                    GeneratedQuestion(
                        type=data.type,
                        question=f"Sample {data.type} question about {data.domain} covering {self._topic()}",
                        options=["Option A", "Option B", "Option C", "Option D"],
                        correct="A",
                        explanation=f"Explanation for question {i + 1}",
                    )
                )
            else:
                out.append(
                    GeneratedQuestion(
                        type="descriptive",
                        question=f"Describe {data.domain} in detail covering {self._topic()}",
                        rubric="Award marks based on accuracy, depth and clarity.",
                        max_score=10,
                        word_limit=250,
                    )
                )
        return out

    def mark_answer(self, data: MarkAnswerInput) -> MarkAnswerResult:
        self.call_count += 1
        self._maybe_fail("AI marking")
        score = data.max_score // 2 if data.answer.strip() else 0
        return MarkAnswerResult(
            score=score, justification=f"Fake AI assessment: awarded {score} of {data.max_score} marks."
        )

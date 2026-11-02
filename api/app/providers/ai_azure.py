"""Azure AI Foundry / Azure OpenAI provider (GPT-4o) over the v1 chat-completions route.

UNVERIFIED against the real service (ledger AZ-027): unit tests drive it through ``httpx.MockTransport``.
Secrets: the key is sent only in the ``api-key`` header and never logged; neither are prompts or JD text.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from ..ai.prompts import build_generate_messages, temperature_for
from ..ai.validator import AiOutputInvalid, parse_questions
from ..config import Settings
from ..core.logging import logger
from ..tools.probe import foundry_url
from .ports import (
    GeneratedQuestion,
    GenerateQuestionsInput,
    MarkAnswerInput,
    MarkAnswerResult,
    ProviderError,
)

MAX_VALIDATION_ATTEMPTS = 3
RATE_LIMIT_WAIT_SECONDS = 2.0


class AzureAiProvider:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._sleep = sleep

    # ── transport ───────────────────────────────────────────────────────────────────────
    def _chat(self, messages: list[dict[str, Any]], *, temperature: float) -> tuple[str, int]:
        s = self.settings
        url = foundry_url(s.FOUNDRY_ENDPOINT, s.FOUNDRY_DEPLOYMENT, s.FOUNDRY_API_STYLE, s.FOUNDRY_API_VERSION)
        body = {
            "model": s.FOUNDRY_DEPLOYMENT,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": s.AI_MAX_OUTPUT_TOKENS,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json", "api-key": s.FOUNDRY_KEY}
        for attempt in (1, 2):
            try:
                with httpx.Client(timeout=s.AI_TIMEOUT_SECONDS, transport=self._transport) as client:
                    res = client.post(url, headers=headers, json=body)
            except httpx.TimeoutException:
                raise ProviderError("The AI service did not answer in time", "TIMEOUT") from None
            except httpx.HTTPError:
                raise ProviderError("The AI service could not be reached", "UPSTREAM") from None
            if res.status_code == 429:
                retry_after = _retry_after(res)
                if attempt == 1:
                    logger.warn("ai_rate_limited", wait_seconds=RATE_LIMIT_WAIT_SECONDS)
                    self._sleep(RATE_LIMIT_WAIT_SECONDS)
                    continue
                raise ProviderError("The AI service is rate limited", "RATE_LIMITED", retry_after=retry_after)
            break
        if res.status_code >= 400:
            # Status only: the response body may echo prompt text, so it is deliberately not included.
            raise ProviderError(f"The AI service returned HTTP {res.status_code}", "UPSTREAM")
        try:
            payload = res.json()
            content = payload["choices"][0]["message"]["content"]
            tokens = int((payload.get("usage") or {}).get("total_tokens") or 0)
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("The AI service returned an unexpected response", "INVALID_RESPONSE") from None
        if not isinstance(content, str):
            raise ProviderError("The AI service returned an empty answer", "INVALID_RESPONSE")
        return content, tokens

    # ── port ────────────────────────────────────────────────────────────────────────────
    def generate_questions(self, data: GenerateQuestionsInput) -> list[GeneratedQuestion]:
        return self.generate_questions_with_usage(data)[0]

    def generate_questions_with_usage(self, data: GenerateQuestionsInput) -> tuple[list[GeneratedQuestion], int]:
        total = 0
        last = "unknown"
        for attempt in range(1, MAX_VALIDATION_ATTEMPTS + 1):
            content, tokens = self._chat(
                build_generate_messages(data, retry=attempt > 1), temperature=temperature_for("generate")
            )
            total += tokens
            try:
                return parse_questions(content, data.type)[: data.count], total
            except AiOutputInvalid as exc:
                last = str(exc)
                logger.warn("ai_output_invalid", attempt=attempt, reason=last)
        raise ProviderError(
            f"The AI answer was unusable after {MAX_VALIDATION_ATTEMPTS} attempts ({last})", "INVALID_RESPONSE"
        )

    def mark_answer(self, data: MarkAnswerInput) -> MarkAnswerResult:
        raise ProviderError("AzureAiProvider.mark_answer is implemented in Phase 9", "UPSTREAM")


def _retry_after(res: httpx.Response) -> int | None:
    raw = res.headers.get("retry-after")
    return int(raw) if raw and raw.isdigit() else None

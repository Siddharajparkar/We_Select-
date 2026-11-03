"""Validation and de-duplication of model output. Nothing the model returns is trusted."""

from __future__ import annotations

import json
import re
from typing import Any

from ..providers.ports import GeneratedQuestion, QuestionKind

MAX_QUESTION_CHARS = 2000
MAX_OPTION_CHARS = 500
MAX_TEXT_CHARS = 2000
DEFAULT_WORD_LIMIT = 250
DEFAULT_MAX_SCORE = 10
DUPLICATE_THRESHOLD = 0.8
_FENCE = re.compile(r"^\s*```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$", re.S)
_WORD = re.compile(r"[a-z0-9]+")
_LABEL = re.compile(r"^\(?([A-Da-d])[\).:]\s+")  # "A) text", "B. text", "(C) text", "D: text"
_BARE_LETTER = re.compile(r"^\(?(?:option\s+|answer\s*:?\s*)?([A-Da-d])[\).:]?$", re.I)  # "B", "B)", "Option B"


class AiOutputInvalid(Exception):
    """The model answer cannot be used (not JSON, wrong shape, or no valid question in it)."""


def strip_fences(raw: str) -> str:
    m = _FENCE.match(raw)
    return (m.group(1) if m else raw).strip()


def _text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    v = " ".join(value.split())
    return v if v and len(v) <= limit else None


def _option_text(value: Any) -> str | None:
    """One option as plain text. Small models sometimes send {"A": "text"} instead of "text"."""
    if isinstance(value, dict) and len(value) == 1:
        value = next(iter(value.values()))
    return _text(value, MAX_OPTION_CHARS)


def _strip_labels(options: list[str]) -> list[str]:
    """Drop "A) " style prefixes, but only when all four options carry A, B, C, D in order."""
    letters = [(m.group(1).upper() if (m := _LABEL.match(o)) else None) for o in options]
    if letters == ["A", "B", "C", "D"]:
        return [_LABEL.sub("", o, count=1) for o in options]
    return options


def _norm(text: str) -> str:
    return " ".join(_WORD.findall(text.lower()))


def _correct_letter(correct: Any, options: list[str]) -> str | None:
    """Map the model's `correct` to A-D: a letter ("B", "B)", "Option B"), or the exact text of exactly one option."""
    if not isinstance(correct, str):
        return None
    c = correct.strip()
    m = _BARE_LETTER.match(c)
    if m:
        return m.group(1).upper()
    candidates = [c]
    if (lm := _LABEL.match(c)) is not None:
        candidates.append(c[lm.end() :])
    for cand in candidates:
        hits = [i for i, o in enumerate(options) if _norm(o) == _norm(cand) and _norm(cand)]
        if len(hits) == 1:
            return "ABCD"[hits[0]]
    return None


def _one(item: Any, kind: QuestionKind) -> GeneratedQuestion | None:
    if not isinstance(item, dict):
        return None
    question = _text(item.get("question"), MAX_QUESTION_CHARS)
    if question is None:
        return None
    if kind in ("mcq", "cognitive"):
        opts = item.get("options")
        if not isinstance(opts, list) or len(opts) != 4:
            return None
        raw = [_option_text(o) for o in opts]
        if any(o is None for o in raw):
            return None
        cleaned = _strip_labels([str(o) for o in raw])
        if len({o.lower() for o in cleaned}) != 4:
            return None
        correct = _correct_letter(item.get("correct"), cleaned)
        if correct is None:
            return None
        explanation = _text(item.get("explanation"), MAX_TEXT_CHARS)
        if explanation is None:
            return None
        return GeneratedQuestion(
            type=kind, question=question, options=[str(o) for o in cleaned], correct=correct, explanation=explanation
        )
    rubric = _text(item.get("rubric"), MAX_TEXT_CHARS)
    if rubric is None or len(rubric) < 10:
        return None
    score = item.get("maxScore", DEFAULT_MAX_SCORE)
    if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 20:
        return None
    limit = item.get("wordLimit", DEFAULT_WORD_LIMIT)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 10 <= limit <= 2000:
        return None
    return GeneratedQuestion(type=kind, question=question, rubric=rubric, max_score=score, word_limit=limit)


def parse_questions(raw: str, kind: QuestionKind) -> list[GeneratedQuestion]:
    """Return the valid questions of one model answer; raise ``AiOutputInvalid`` when there are none."""
    try:
        data = json.loads(strip_fences(raw))
    except (ValueError, TypeError):
        raise AiOutputInvalid("the answer is not valid JSON") from None
    items = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise AiOutputInvalid("the answer has no `questions` list")
    good = [q for q in (_one(i, kind) for i in items) if q is not None]
    if not good:
        raise AiOutputInvalid("none of the returned questions had the required fields")
    return good


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def similarity(a: str, b: str) -> float:
    """Jaccard similarity of the word sets of two question texts."""
    wa, wb = _words(a), _words(b)
    if not wa and not wb:
        return 1.0
    return len(wa & wb) / len(wa | wb)


def drop_duplicates(new: list[GeneratedQuestion], existing_bodies: list[str]) -> tuple[list[GeneratedQuestion], int]:
    """Drop questions more than 80 % similar to an existing or earlier-kept one. Returns (kept, dropped)."""
    seen = list(existing_bodies)
    kept: list[GeneratedQuestion] = []
    for q in new:
        if any(similarity(q.question, s) > DUPLICATE_THRESHOLD for s in seen):
            continue
        kept.append(q)
        seen.append(q.question)
    return kept, len(new) - len(kept)

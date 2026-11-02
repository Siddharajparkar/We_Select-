"""Phase 0: provider ports, fakes and factory."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.config import load_settings
from app.providers import create_providers
from app.providers.ai_fake import FakeAiProvider
from app.providers.email_fake import FakeEmailProvider
from app.providers.files_memory import MemoryFilesProvider, sanitize_file_name
from app.providers.ports import (
    GenerateQuestionsInput,
    MarkAnswerInput,
    ProviderError,
    SaveJdInput,
    SendInviteInput,
)

FAKE_BLOB_CS = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=ZmFrZQ==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"


def gen(count: int = 3, type_: str = "mcq") -> GenerateQuestionsInput:
    return GenerateQuestionsInput("JD text", type_, "Python", "easy", count)  # type: ignore[arg-type]


def test_fake_ai_generates_requested_mcq_count() -> None:
    qs = FakeAiProvider().generate_questions(gen(3))
    assert len(qs) == 3
    assert all(q.type == "mcq" and q.options and len(q.options) == 4 and q.correct == "A" for q in qs)


def test_fake_ai_descriptive_has_rubric_and_score() -> None:
    q = FakeAiProvider().generate_questions(gen(1, "descriptive"))[0]
    assert q.rubric and q.max_score == 10 and q.word_limit == 250 and q.options is None


def test_fake_ai_is_deterministic() -> None:
    a = FakeAiProvider().generate_questions(gen(2))
    b = FakeAiProvider().generate_questions(gen(2))
    assert a == b


def test_fake_ai_fail_count_then_succeeds() -> None:
    ai = FakeAiProvider()
    ai.fail_count = 2
    for _ in range(2):
        with pytest.raises(ProviderError) as e:
            ai.generate_questions(gen())
        assert e.value.code == "UPSTREAM"
    assert len(ai.generate_questions(gen())) == 3
    assert ai.call_count == 3 and len(ai.calls) == 3


@pytest.mark.parametrize(
    ("flag", "code"),
    [("simulate_timeout", "TIMEOUT"), ("simulate_429", "RATE_LIMITED"), ("return_invalid_json", "INVALID_RESPONSE")],
)
def test_fake_ai_scripted_failures(flag: str, code: str) -> None:
    ai = FakeAiProvider()
    setattr(ai, flag, True)
    with pytest.raises(ProviderError) as e:
        ai.generate_questions(gen())
    assert e.value.code == code
    with pytest.raises(ProviderError):
        ai.mark_answer(MarkAnswerInput("q", "r", 10, "answer"))


def test_fake_ai_429_has_retry_after_and_partial_count() -> None:
    ai = FakeAiProvider()
    ai.simulate_429 = True
    with pytest.raises(ProviderError) as e:
        ai.generate_questions(gen())
    assert e.value.retry_after == 2
    ai.reset()
    ai.partial_count = 1
    assert len(ai.generate_questions(gen(5))) == 1


def test_fake_ai_marks_half_for_non_empty_answer() -> None:
    ai = FakeAiProvider()
    assert ai.mark_answer(MarkAnswerInput("q", "r", 10, "some answer")).score == 5
    assert ai.mark_answer(MarkAnswerInput("q", "r", 10, "   ")).score == 0


def test_fake_email_outbox_and_scripted_failure() -> None:
    mail = FakeEmailProvider()
    inv = SendInviteInput("c@example.com", "Cand", "Exam", 60, "https://x/t/abc", datetime(2026, 12, 1, tzinfo=UTC))
    mail.fail_count = 1
    with pytest.raises(ProviderError):
        mail.send_invite(inv)
    res = mail.send_invite(inv)
    assert len(mail.outbox) == 1 and mail.outbox[0].message_id == res.message_id
    assert mail.call_count == 2
    assert mail.drain_outbox()[0].data.to == "c@example.com"
    assert mail.outbox == []


def test_memory_files_roundtrip_and_path_layout() -> None:
    f = MemoryFilesProvider()
    t, a = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
    path = f.save_jd(SaveJdInput(t, a, "jd.pdf", b"%PDF"))
    assert path == f"{t}/{a}/jd.pdf"
    assert f.get_jd(path) == b"%PDF"
    f.delete_jd(path)
    f.delete_jd(path)  # idempotent
    with pytest.raises(FileNotFoundError):
        f.get_jd(path)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", ".._.._etc_passwd"),
        ("a\\b/c.txt", "a_b_c.txt"),
        ("na\x00me\x1f.pdf", "name.pdf"),
        ("", "file"),
        ("\x00\x01", "file"),
    ],
)
def test_sanitize_file_name(raw: str, expected: str) -> None:
    assert sanitize_file_name(raw) == expected


def test_sanitize_truncates_to_120_keeping_extension() -> None:
    out = sanitize_file_name("a" * 300 + ".docx")
    assert len(out) == 120 and out.endswith(".docx")
    assert len(sanitize_file_name("b" * 300)) == 120


def test_factory_returns_fakes_by_default() -> None:
    p = create_providers(load_settings())
    assert isinstance(p.ai, FakeAiProvider) and isinstance(p.email, FakeEmailProvider)
    assert isinstance(p.files, MemoryFilesProvider)


def test_factory_returns_azure_implementations_when_configured() -> None:
    from app.providers.ai_azure import AzureAiProvider
    from app.providers.email_azure import AzureEmailProvider

    s = load_settings(
        AI_MODE="azure", FOUNDRY_ENDPOINT="https://x.invalid", FOUNDRY_KEY="k",
        EMAIL_MODE="azure", ACS_CONNECTION_STRING="endpoint=x;accesskey=y", ACS_SENDER="a@b.invalid",
    )  # fmt: skip
    p = create_providers(s)
    assert isinstance(p.ai, AzureAiProvider) and isinstance(p.email, AzureEmailProvider)
    # generate_questions is real since Phase 6 (tested with a mock transport); marking arrives in Phase 9.
    with pytest.raises(ProviderError, match="Phase 9"):
        p.ai.mark_answer(MarkAnswerInput(question="q", rubric="r", max_score=5, answer="a"))


def test_factory_builds_blob_provider_for_azurite_without_network() -> None:
    from app.providers.files_azure import AzureBlobFilesProvider

    s = load_settings(FILES_MODE="azurite", BLOB_CONNECTION_STRING=FAKE_BLOB_CS)
    assert isinstance(create_providers(s).files, AzureBlobFilesProvider)

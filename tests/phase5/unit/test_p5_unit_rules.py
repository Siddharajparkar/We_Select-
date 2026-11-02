"""Phase 5 unit tests: schema limits, filename sanitiser, word count, file detection and extraction."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.middleware import JD_FILE_MAX_BYTES, MAX_BODY_BYTES, RequestContextMiddleware
from app.providers.files_memory import sanitize_file_name
from app.schemas.assessments import AssessmentCreateIn, AssessmentPatchIn
from app.services import jd_files
from app.services.text import count_words
from helpers_pdf import JD_TEXT, make_pdf


def section(count: int = 5, **over: object) -> dict[str, object]:
    return {"type": "mcq", "domain": "Python", "difficulty": "medium", "count": count, **over}


def create(**over: object) -> dict[str, object]:
    return {"title": "Backend", "durationMinutes": 60, "passingScore": 60, "sections": [section()], **over}


# ── schema limits ───────────────────────────────────────────────────────────────────────────
def test_valid_create_body() -> None:
    a = AssessmentCreateIn(**create(jobDescription="x " * 10))  # type: ignore[arg-type]
    assert a.sections[0].count == 5


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_title_bounds(title: str) -> None:
    with pytest.raises(ValidationError):
        AssessmentCreateIn(**create(title=title))  # type: ignore[arg-type]


def test_title_boundaries_ok() -> None:
    AssessmentCreateIn(**create(title="x"))  # type: ignore[arg-type]
    AssessmentCreateIn(**create(title="x" * 200))  # type: ignore[arg-type]


@pytest.mark.parametrize("minutes", [4, 241, 0, -1])
def test_duration_out_of_range(minutes: int) -> None:
    with pytest.raises(ValidationError):
        AssessmentCreateIn(**create(durationMinutes=minutes))  # type: ignore[arg-type]


@pytest.mark.parametrize("minutes", [5, 240])
def test_duration_edges_ok(minutes: int) -> None:
    AssessmentCreateIn(**create(durationMinutes=minutes))  # type: ignore[arg-type]


@pytest.mark.parametrize("score", [-1, 101])
def test_passing_score_out_of_range(score: int) -> None:
    with pytest.raises(ValidationError):
        AssessmentCreateIn(**create(passingScore=score))  # type: ignore[arg-type]


@pytest.mark.parametrize("score", [0, 100])
def test_passing_score_edges_ok(score: int) -> None:
    AssessmentCreateIn(**create(passingScore=score))  # type: ignore[arg-type]


def test_job_description_20000_ok_20001_rejected() -> None:
    AssessmentCreateIn(**create(jobDescription="a" * 20_000))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        AssessmentCreateIn(**create(jobDescription="a" * 20_001))  # type: ignore[arg-type]


def test_sections_count_bounds() -> None:
    with pytest.raises(ValidationError):
        AssessmentCreateIn(**create(sections=[]))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        AssessmentCreateIn(**create(sections=[section(1)] * 11))  # type: ignore[arg-type]
    AssessmentCreateIn(**create(sections=[section(1)] * 10))  # type: ignore[arg-type]


def test_per_section_count_max_20() -> None:
    AssessmentCreateIn(**create(sections=[section(20)]))  # type: ignore[arg-type]
    for bad in (0, 21):
        with pytest.raises(ValidationError):
            AssessmentCreateIn(**create(sections=[section(bad)]))  # type: ignore[arg-type]


def test_total_questions_max_40() -> None:
    AssessmentCreateIn(**create(sections=[section(20), section(20)]))  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="at most 40"):
        AssessmentCreateIn(**create(sections=[section(20), section(20), section(1)]))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad",
    [{"type": "essay"}, {"difficulty": "extreme"}, {"domain": ""}, {"domain": "d" * 101}],
)
def test_section_field_rules(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AssessmentCreateIn(**create(sections=[section(**bad)]))  # type: ignore[arg-type]


def test_patch_needs_a_field_and_rejects_nulls() -> None:
    with pytest.raises(ValidationError):
        AssessmentPatchIn()
    with pytest.raises(ValidationError):
        AssessmentPatchIn(title=None)
    assert AssessmentPatchIn(jobDescription=None).model_fields_set == {"jobDescription"}  # null clears the JD


def test_patch_total_limit_applies() -> None:
    with pytest.raises(ValidationError):
        AssessmentPatchIn(sections=[section(20), section(20), section(5)])  # type: ignore[arg-type]


# ── filename sanitiser ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../x.pdf", ".._.._x.pdf"),
        ("..\\..\\evil.txt", ".._.._evil.txt"),
        ("/etc/passwd", "_etc_passwd"),
        ("report\x00\x1f.pdf", "report.pdf"),
        ("naïve résumé 日本語.pdf", "naïve résumé 日本語.pdf"),
        ("", "file"),
    ],
)
def test_sanitize_file_name(raw: str, expected: str) -> None:
    out = sanitize_file_name(raw)
    assert out == expected
    assert "/" not in out and "\\" not in out


def test_long_names_are_capped_at_120_and_keep_the_extension() -> None:
    out = sanitize_file_name("a" * 300 + ".pdf")
    assert len(out) == 120 and out.endswith(".pdf")
    assert len(sanitize_file_name("b" * 300)) == 120


# ── word count ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("text", "n"),
    [(None, 0), ("", 0), ("   \n\t ", 0), ("one", 1), ("one  two\nthree\tfour", 4), (" lead and trail ", 3)],
)
def test_count_words(text: str | None, n: int) -> None:
    assert count_words(text) == n


# ── file detection ──────────────────────────────────────────────────────────────────────────
def test_detect_pdf_and_txt() -> None:
    assert jd_files.detect_kind("JD.PDF", make_pdf("hi")) == "pdf"
    assert jd_files.detect_kind("jd.txt", "héllo".encode()) == "txt"
    assert jd_files.detect_kind("jd.txt", b"\xef\xbb\xbfBOM text") == "txt"


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("evil.pdf", b"MZ\x90\x00 this is an exe"),  # renamed executable
        ("note.txt", b"abc\x00def"),  # binary
        ("note.txt", "caf\xe9".encode("latin-1")),  # not UTF-8
        ("run.exe", b"%PDF-1.4"),  # PDF bytes, wrong extension
        ("jd", b"hello"),
        ("jd.docx", b"PK\x03\x04"),
    ],
)
def test_detect_rejects_by_bytes_and_extension(name: str, content: bytes) -> None:
    with pytest.raises(AppError) as e:
        jd_files.detect_kind(name, content)
    assert e.value.status == 400 and e.value.code == "VALIDATION_ERROR"


# ── extraction ──────────────────────────────────────────────────────────────────────────────
def test_extract_pdf_text() -> None:
    text = jd_files.extract_text("pdf", make_pdf(JD_TEXT))
    assert "FastAPI" in text and text.startswith("Senior Backend Engineer")


def test_extract_normalises_whitespace() -> None:
    assert jd_files.extract_text("txt", b"  Hello \t  world  \r\n\r\n\r\n\r\n  next   line is long enough ") == (
        "Hello world\n\nnext line is long enough"
    )


def test_text_under_20_chars_is_unreadable() -> None:
    with pytest.raises(AppError) as e:
        jd_files.extract_text("txt", b"too short")
    assert e.value.status == 422 and e.value.code == "FILE_UNREADABLE" and "Paste" in e.value.message


def test_pdf_without_text_is_unreadable() -> None:
    with pytest.raises(AppError) as e:
        jd_files.extract_text("pdf", make_pdf(""))
    assert e.value.code == "FILE_UNREADABLE"


def test_corrupt_pdf_is_unreadable() -> None:
    with pytest.raises(AppError) as e:
        jd_files.extract_text("pdf", b"%PDF-1.4\nthis is not a pdf at all")
    assert e.value.status == 422 and e.value.code == "FILE_UNREADABLE"


def test_text_boundary_20000_ok_20001_rejected_never_truncated() -> None:
    assert len(jd_files.extract_text("txt", b"a" * 20_000)) == 20_000
    with pytest.raises(AppError) as e:
        jd_files.extract_text("txt", b"a" * 20_001)
    assert e.value.code == "FILE_UNREADABLE" and "20,000" in e.value.message


def test_slow_pdf_is_cut_off(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    monkeypatch.setattr(jd_files, "PDF_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(jd_files, "_pdf_text", lambda _c: time.sleep(0.5) or "x" * 50)
    with pytest.raises(AppError) as e:
        jd_files.extract_text("pdf", b"%PDF-")
    assert e.value.code == "FILE_UNREADABLE" and "too long" in e.value.message


# ── body limits ─────────────────────────────────────────────────────────────────────────────
def test_only_the_jd_upload_route_gets_a_bigger_body_limit() -> None:
    mw = RequestContextMiddleware(lambda *a: None)  # type: ignore[arg-type]
    jd = "/api/v1/assessments/11111111-1111-4111-8111-111111111111/jd-file"
    assert mw.limit_for("POST", jd) > JD_FILE_MAX_BYTES
    assert mw.limit_for("GET", jd) == MAX_BODY_BYTES
    assert mw.limit_for("POST", "/api/v1/assessments") == MAX_BODY_BYTES
    assert mw.limit_for("POST", jd + "/x") == MAX_BODY_BYTES

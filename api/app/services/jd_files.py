"""Job-description upload handling (Prompt A 5.4): type detection by magic bytes and text extraction."""

from __future__ import annotations

import io
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from ..core.errors import AppError
from ..schemas.assessments import MAX_JD_CHARS

MAX_FILE_BYTES = 2 * 1024 * 1024
MIN_TEXT_CHARS = 20
PDF_TIMEOUT_SECONDS = 10
MAX_PDF_PAGES = 200

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pdf-extract")


def unreadable(message: str) -> AppError:
    return AppError.unprocessable("FILE_UNREADABLE", message)


def detect_kind(file_name: str, content: bytes) -> str:
    """``pdf`` or ``txt``. The extension must be allowed AND the bytes must agree (client mime is never trusted)."""
    lower = file_name.lower()
    if lower.endswith(".pdf"):
        if not content.startswith(b"%PDF-"):
            raise AppError.bad_request("The file is not a valid PDF (content does not match the .pdf extension)")
        return "pdf"
    if lower.endswith(".txt"):
        if b"\x00" in content:
            raise AppError.bad_request("The file is not a text file (it contains binary data)")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise AppError.bad_request("The text file must be UTF-8 encoded") from None
        return "txt"
    raise AppError.bad_request("Only .pdf and .txt files are accepted")


def normalise_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t\f\v\u00a0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pdf_text(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted:
        raise ValueError("encrypted")
    parts = []
    for page in reader.pages[:MAX_PDF_PAGES]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def extract_text(kind: str, content: bytes) -> str:
    """Return normalised text or raise 422 FILE_UNREADABLE (empty/scanned, corrupt, too long, too slow)."""
    if kind == "txt":
        raw = content.decode("utf-8-sig")
    else:
        future = _executor.submit(_pdf_text, content)
        try:
            raw = future.result(timeout=PDF_TIMEOUT_SECONDS)
        except FutureTimeout:
            future.cancel()
            raise unreadable("Reading the PDF took too long. Paste the job description text instead.") from None
        except Exception:
            raise unreadable("The PDF could not be read. Paste the job description text instead.") from None
    text = normalise_whitespace(raw)
    if len(text) < MIN_TEXT_CHARS:
        raise unreadable(
            "No readable text was found in the file (is it a scanned image?). Paste the job description text instead."
        )
    if len(text) > MAX_JD_CHARS:
        raise unreadable(f"The file text is longer than the {MAX_JD_CHARS:,} character limit. Shorten it and retry.")
    return text

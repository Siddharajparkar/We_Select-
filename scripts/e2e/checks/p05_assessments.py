"""Phase 5 live checks: endpoints 8-14 (run with the tenants created by p04). Blob existence in Azure Storage
is verified by the office guide (OC-5) with `az storage blob list`; this harness checks behaviour over HTTP."""

from __future__ import annotations

BODY = {
    "title": "E2E Assessment",
    "jobDescription": "placeholder",
    "durationMinutes": 60,
    "passingScore": 60,
    "sections": [{"type": "mcq", "domain": "Python", "difficulty": "medium", "count": 3}],
}
JD_LINES = [
    "Senior Backend Engineer",
    "We are hiring a backend engineer to design and build Python services on Azure.",
    "You will own APIs, databases and background jobs, and mentor other engineers on the team.",
    "Requirements include strong SQL skills, FastAPI experience, testing discipline and clear communication.",
]


def make_pdf(lines: list[str]) -> bytes:
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # noqa: E731
    body = "BT /F1 10 Tf 40 760 Td 12 TL " + " ".join(f"({esc(x)}) Tj T*" for x in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(body)} >>\nstream\n{body}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _sid(ctx, tag="A"):  # type: ignore[no-untyped-def]
    return ctx.state[tag]["sid"]


def create_list_get(ctx):  # type: ignore[no-untyped-def]
    r = ctx.request("POST", "/api/v1/assessments", _sid(ctx), json=BODY)
    assert r.status_code == 201 and r.json()["status"] == "draft", f"create: {r.status_code}"
    aid = r.json()["id"]
    ctx.state["assessment_id"] = aid
    rows = ctx.request("GET", "/api/v1/assessments", _sid(ctx)).json()
    assert aid in {x["id"] for x in rows}, "created assessment missing from list"
    g = ctx.request("GET", f"/api/v1/assessments/{aid}", _sid(ctx))
    assert g.status_code == 200 and g.json()["sections"] == BODY["sections"]


def upload_pdf_stores_text(ctx):  # type: ignore[no-untyped-def]
    aid = ctx.state["assessment_id"]
    r = ctx.request(
        "POST",
        f"/api/v1/assessments/{aid}/jd-file",
        _sid(ctx),
        files={"file": ("e2e-jd.pdf", make_pdf(JD_LINES), "application/pdf")},
    )
    assert r.status_code == 200, f"upload: {r.status_code} {r.text[:120]}"
    assert "FastAPI" in r.json()["jobDescription"] and r.json()["wordCount"] > 30
    g = ctx.request("GET", f"/api/v1/assessments/{aid}", _sid(ctx)).json()
    assert g["jdFileName"] == "e2e-jd.pdf"


def bad_files_are_rejected(ctx):  # type: ignore[no-untyped-def]
    aid = ctx.state["assessment_id"]
    r = ctx.request(
        "POST",
        f"/api/v1/assessments/{aid}/jd-file",
        _sid(ctx),
        files={"file": ("evil.pdf", b"MZ not a pdf", "application/pdf")},
    )
    assert r.status_code == 400, f"renamed exe: {r.status_code}"
    r = ctx.request(
        "POST",
        f"/api/v1/assessments/{aid}/jd-file",
        _sid(ctx),
        files={"file": ("big.txt", b"a" * (2 * 1024 * 1024 + 1))},
    )
    assert r.status_code == 400, f"2 MB + 1: {r.status_code}"


def other_tenant_gets_404(ctx):  # type: ignore[no-untyped-def]
    aid = ctx.state["assessment_id"]
    for method, suffix in (("GET", ""), ("DELETE", ""), ("POST", "/close")):
        r = ctx.request(method, f"/api/v1/assessments/{aid}{suffix}", _sid(ctx, "B"))
        assert r.status_code == 404, f"{method}{suffix}: {r.status_code}"
    assert aid not in {x["id"] for x in ctx.request("GET", "/api/v1/assessments", _sid(ctx, "B")).json()}


def delete_draft(ctx):  # type: ignore[no-untyped-def]
    aid = ctx.state["assessment_id"]
    assert ctx.request("DELETE", f"/api/v1/assessments/{aid}", _sid(ctx)).status_code == 204
    assert ctx.request("GET", f"/api/v1/assessments/{aid}", _sid(ctx)).status_code == 404


CHECKS = [create_list_get, upload_pdf_stores_text, bad_files_are_rejected, other_tenant_gets_404, delete_draft]

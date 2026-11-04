#!/usr/bin/env python3
"""Build docs/ARCHITECTURE.pdf (and the diagram PNGs in docs/images/).

    python scripts/docs/build_architecture.py            # diagrams + PDF
    python scripts/docs/build_architecture.py --diagrams # diagrams only

Inputs : docs/architecture/content.html (the text) and docs/architecture/icons/*.png (official Azure icon set).
Outputs: docs/images/architecture.png, docs/images/pipeline.png, docs/images/layers.png and docs/ARCHITECTURE.pdf.
Needs  : Google Chrome or Microsoft Edge (headless, for the PNG and PDF export) and pypdf (already a dependency)
         for the table-of-contents page numbers. No Graphviz, no other tools.
"""

from __future__ import annotations

import argparse
import base64
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "docs" / "architecture"
ICONS = SRC / "icons"
IMAGES = ROOT / "docs" / "images"
PDF = ROOT / "docs" / "ARCHITECTURE.pdf"

K = 1.2  # text scale: keeps diagram text readable when the figure is shrunk to a page
INK, MUTED, LINE, BLUE, GREEN, AMBER = "#1f2937", "#6b7280", "#9ca3af", "#0b6bcb", "#15803d", "#b45309"


# ── drawing helpers ───────────────────────────────────────────────────────────────────────────────
def icon_uri(name: str) -> str:
    return "data:image/png;base64," + base64.b64encode((ICONS / f"{name}.png").read_bytes()).decode()


class Svg:
    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.parts: list[str] = []

    def group(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        title: str,
        *,
        fill: str = "#f8fafc",
        stroke: str = LINE,
        dash: bool = False,
        title_right: bool = False,
    ) -> None:
        d = ' stroke-dasharray="6 4"' if dash else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{d}/>'
        )
        tx, anchor = (x + w - 14, "end") if title_right else (x + 14, "start")
        self.parts.append(
            f'<text x="{tx}" y="{y + 24}" font-size="{round(15 * K)}" font-weight="700" fill="{MUTED}" text-anchor="{anchor}">{html.escape(title)}</text>'
        )

    def node(
        self,
        icon: str,
        cx: int,
        cy: int,
        label: str,
        sub: str = "",
        *,
        size: int = 64,
        dim: bool = False,
        side: bool = False,
    ) -> None:
        op = ' opacity="0.55"' if dim else ""
        self.parts.append(
            f'<image href="{icon_uri(icon)}" x="{cx - size // 2}" y="{cy - size // 2}" width="{size}" height="{size}"{op}/>'
        )
        if side:  # label to the right of the icon
            tx, ty, anchor = cx + size // 2 + 10, cy - 6, "start"
        else:
            tx, ty, anchor = cx, cy + size // 2 + 22, "middle"
        self.parts.append(
            f'<text x="{tx}" y="{ty}" font-size="{round(14 * K)}" font-weight="700" fill="{INK}" text-anchor="{anchor}">{html.escape(label)}</text>'
        )
        for i, line in enumerate(filter(None, sub.split("|"))):
            self.parts.append(
                f'<text x="{tx}" y="{ty + 19 * (i + 1)}" font-size="{round(12 * K)}" fill="{MUTED}" text-anchor="{anchor}">{html.escape(line)}</text>'
            )

    def edge(
        self,
        pts: list[tuple[int, int]],
        label: str = "",
        *,
        color: str = BLUE,
        dash: bool = False,
        at: float = 0.5,
        dx: int = 0,
        dy: int = -8,
    ) -> None:
        d = "M " + " L ".join(f"{x} {y}" for x, y in pts)
        da = ' stroke-dasharray="7 5"' if dash else ""
        self.parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"{da} marker-end="url(#arrow-{color[1:]})"/>'
        )
        if label:
            (x1, y1), (x2, y2) = pts[-2], pts[-1]
            lx, ly = x1 + (x2 - x1) * at + dx, y1 + (y2 - y1) * at + dy
            w = 8.6 * len(label) + 16
            self.parts.append(
                f'<rect x="{lx - w / 2:.0f}" y="{ly - 17:.0f}" width="{w:.0f}" height="24" rx="4" fill="white" fill-opacity="0.92"/>'
            )
            self.parts.append(
                f'<text x="{lx:.0f}" y="{ly:.0f}" font-size="{round(12 * K)}" fill="{color}" text-anchor="middle" font-weight="600">{html.escape(label)}</text>'
            )

    def box(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        title: str,
        lines: list[str] = (),
        *,
        fill: str = "white",
        stroke: str = BLUE,
    ) -> None:  # type: ignore[assignment]
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.8"/>'
        )
        self.parts.append(
            f'<text x="{x + w / 2:.0f}" y="{y + 24}" font-size="{round(14 * K)}" font-weight="700" fill="{INK}" text-anchor="middle">{html.escape(title)}</text>'
        )
        for i, line in enumerate(lines):
            self.parts.append(
                f'<text x="{x + w / 2:.0f}" y="{y + 44 + 19 * i}" font-size="{round(12 * K)}" fill="{MUTED}" text-anchor="middle">{html.escape(line)}</text>'
            )

    def text(
        self, x: int, y: int, s: str, *, size: int = 12, color: str = MUTED, bold: bool = False, anchor: str = "start"
    ) -> None:
        w = "700" if bold else "400"
        self.parts.append(
            f'<text x="{x}" y="{y}" font-size="{round(size * K)}" fill="{color}" font-weight="{w}" text-anchor="{anchor}">{html.escape(s)}</text>'
        )

    def render(self) -> str:
        markers = "".join(
            f'<marker id="arrow-{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{c}"/></marker>'
            for c in (BLUE, GREEN, AMBER, MUTED)
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" font-family="Segoe UI, Helvetica, Arial, sans-serif">'
            f'<defs>{markers}</defs><rect width="100%" height="100%" fill="white"/>' + "".join(self.parts) + "</svg>"
        )


# ── the three diagrams ────────────────────────────────────────────────────────────────────────────
def main_diagram() -> Svg:
    s = Svg(1560, 900)
    s.group(20, 60, 230, 380, "GitHub")
    s.group(430, 40, 1110, 840, "Azure resource group <RG> (East US)", fill="#f4f8fe", stroke="#7aa7e0")
    s.group(640, 330, 300, 330, "Container Apps environment", fill="#eef5ff", stroke="#7aa7e0", title_right=True)
    s.group(1215, 80, 310, 780, "Existing services (own regions)", fill="#fbfbfb", stroke=LINE, dash=True)

    s.node("github", 125, 150, "Repository", "branch main")
    s.node("github-actions", 125, 330, "GitHub Actions", "CI/CD pipeline")
    s.node("entra-id", 290, 112, "Entra ID", "OIDC token|exchange", size=56, side=True)
    s.node("users", 135, 700, "Recruiter / API client", "browser or HTTP client")

    s.node("container-registry", 540, 150, "Container Registry", "Basic|image tag = commit SHA")
    s.node("key-vault", 540, 600, "Key Vault", "9 secrets (RBAC)")
    s.node("container-apps", 790, 450, "assess-api", "FastAPI|0.25 vCPU / 0.5 GiB|1 replica", size=72)
    s.node("managed-identity", 790, 590, "Managed identity", "app runtime identity", size=44)
    s.node("blob-storage", 1070, 730, "Blob Storage", "private container jd-files")

    s.node("application-insights", 1370, 150, "Application Insights", "North Central US")
    s.node("sql-database", 1370, 300, "Azure SQL Database", "West US|schema assess (13 tables)")
    s.node("ai-services", 1370, 470, "Azure AI Foundry", "North Central US|Phi-4-mini-instruct")
    s.node(
        "communication-services",
        1370,
        640,
        "Communication Services",
        "Email, Azure-managed domain|Phase 7: not used yet",
        dim=True,
    )

    # delivery path (green)
    s.edge([(165, 305), (262, 146)], "1  OIDC login", color=GREEN, at=0.78, dx=66, dy=4)
    s.edge([(168, 318), (498, 170)], "2  push image", color=GREEN, at=0.55, dy=-10)
    s.edge([(172, 346), (716, 446)], "3  update revision", color=GREEN, at=0.4, dy=-10)
    s.edge([(572, 256), (748, 424)], "pull image (AcrPull)", color=BLUE, at=0.4, dx=-78, dy=0)
    s.edge([(580, 590), (722, 476)], "secret references", color=BLUE, at=0.5, dx=-6, dy=26)
    # runtime path (blue)
    s.edge([(185, 672), (722, 470)], "HTTPS  /api/v1", color=BLUE, at=0.5, dy=-10)
    s.edge([(830, 430), (1332, 168)], "telemetry", color=BLUE, at=0.72, dy=-10)
    s.edge([(838, 440), (1332, 300)], "SQL over TLS", color=BLUE, at=0.6, dy=-10)
    s.edge([(842, 460), (1332, 470)], "chat completions", color=BLUE, at=0.6, dy=-10)
    s.edge([(838, 478), (1332, 630)], "invitation email", color=MUTED, dash=True, at=0.62, dy=-10)
    s.edge([(820, 488), (1034, 690)], "PDF upload / delete", color=BLUE, at=0.55, dx=40, dy=0)

    s.text(
        450,
        868,
        "Green arrows: delivery path (CI/CD). Blue arrows: request and data flow. Dashed: planned (Phase 7).",
        size=12,
    )
    s.text(20, 868, "Icons: Azure icon set.", size=12)
    return s


def pipeline_diagram() -> Svg:
    s = Svg(1500, 650)
    s.box(
        20,
        165,
        280,
        104,
        "Trigger",
        ["push: main, phase/**, feature/**", "pull request into main", "docs-only pushes skip CI"],
        stroke=MUTED,
    )
    jobs = [
        (
            20,
            125,
            "fast  (CI gate)",
            ["ruff lint + format  ·  mypy", 'pytest -m "not sql" + coverage', "shellcheck  ·  plan dry run"],
        ),
        (
            165,
            150,
            "container  (real SQL + image)",
            [
                "SQL Server 2022 + Azurite on the runner",
                "migrations twice (2nd = no-op)",
                "SQL/Azurite tests · docker build",
                "container end-to-end · Trivy scan",
            ],
        ),
        (330, 95, "security", ["gitleaks secret scan", "pip-audit (advisory)"]),
    ]
    for i, (y, h, title, lines) in enumerate(jobs):
        s.box(360, y, 360, h, title, lines)
        s.edge([(300, 217), (360, y + h // 2)], "", color=MUTED)
        s.edge([(720, y + h // 2), (830, 190 + 20 * i)], "", color=MUTED)
    s.box(
        830,
        150,
        290,
        140,
        "deploy gate",
        [
            "needs fast + container + security",
            "push on main only",
            "AZURE_DEPLOY_ENABLED = true",
            "environment: production",
        ],
        fill="#f0fdf4",
        stroke=GREEN,
    )
    s.text(1150, 190, "Pull requests end at the", size=12)
    s.text(1150, 210, "three checks: merge only", size=12)
    s.text(1150, 230, "when all are green.", size=12)

    steps = [
        ("1 Azure login", ["OIDC, no stored", "password"]),
        ("2 Record image", ["current image kept", "for rollback"]),
        ("3 Ingress port", ["set to 8080"]),
        ("4 Build + push", ["docker build on runner", "tag = commit SHA"]),
        ("5 Update app", ["new image +", "GIT_SHA setting"]),
        ("6 Smoke test", ["/api/v1/health = ok", "x-app-version = SHA"]),
    ]
    s.text(150, 472, "Deploy job, in order", size=14, color=INK, bold=True)
    x = 20
    for i, (t, ls) in enumerate(steps):
        s.box(x, 480, 215, 80, t, ls, stroke=GREEN)
        if i:
            s.edge([(x - 25, 520), (x, 520)], "", color=GREEN)
        x += 240
    s.edge([(975, 290), (975, 448), (127, 448), (127, 480)], "", color=GREEN)
    s.box(
        1180, 330, 300, 74, "If the smoke test fails", ["roll back to the recorded image"], fill="#fff7ed", stroke=AMBER
    )
    s.edge([(1327, 480), (1327, 404)], "failure", color=AMBER, at=0.5, dx=34, dy=4)
    s.text(
        20,
        610,
        "Separate, manual workflows:  rollback.yml (image tag)  ·  live-e2e.yml  ·  load-test.yml  |  nightly.yml runs daily at 02:00 UTC.",
        size=12,
    )
    return s


def layers_diagram() -> Svg:
    s = Svg(1300, 840)
    s.text(
        30,
        36,
        "A request travels down the left column. Routes use services for business rules and read repositories directly for simple lookups.",
        size=13,
        color=INK,
        bold=True,
    )
    rows = [
        ("Client", "HTTPS request to /api/v1/...", MUTED),
        (
            "Middleware  (middleware.py)",
            "request id · security headers · body-size limit · access log · last-resort 500 handler",
            BLUE,
        ),
        (
            "Routes  (routes/)",
            "URL, method, status code; validates input (schemas/); calls services, or repositories for simple reads",
            BLUE,
        ),
        (
            "Dependencies  (deps.py, security/)",
            "session cookie -> caller (tenant, role); role checks; platform key",
            BLUE,
        ),
        ("Services  (services/)", "business rules: login, assessments, JD files, generation, questions", BLUE),
        (
            "Repositories  (repositories/)",
            "tenant-scoped data access; one code path for SQL Server and in-memory",
            BLUE,
        ),
        ("Database layer  (db/, migrations/)", "SQLAlchemy engine, pyodbc, schema definition, migration runner", BLUE),
        ("Azure SQL  (schema assess)", "13 tables; user assess_app owns only this schema", GREEN),
    ]
    y = 60
    for i, (title, desc, color) in enumerate(rows):
        s.box(30, y, 700, 72, title, [desc], stroke=color)
        if i:
            s.edge([(380, y - 18), (380, y)], "", color=MUTED)
        y += 90
    s.group(900, 235, 380, 300, "Beside the main path")
    s.box(
        920, 275, 340, 66, "Providers  (providers/)", ["AI · email · file storage: Azure + fake versions"], stroke=GREEN
    )
    s.box(920, 355, 340, 66, "AI helpers  (ai/)", ["prompt templates · strict validation of answers"], stroke=GREEN)
    s.box(920, 435, 340, 66, "Job engine  (jobs/)", ["DB-backed queue · retries · runs generation"], stroke=GREEN)
    s.box(920, 580, 340, 66, "Cross-cutting", ["config.py · core/ (clock, ids, logging, errors)"], stroke=MUTED)
    s.box(920, 660, 340, 66, "telemetry.py", ["Application Insights (OpenTelemetry)"], stroke=MUTED)
    s.edge([(730, 440), (920, 308)], "uses providers", color=GREEN, at=0.62, dx=-4, dy=-10)
    s.edge([(1090, 435), (1090, 421)], "", color=GREEN)
    s.edge([(920, 468), (730, 548)], "uses repositories", color=GREEN, at=0.5, dx=0, dy=24)
    return s


DIAGRAMS = {"architecture": main_diagram, "pipeline": pipeline_diagram, "layers": layers_diagram}


# ── Chrome export ─────────────────────────────────────────────────────────────────────────────────
def find_browser() -> str:
    for env in ("CHROME_PATH",):
        if os.environ.get(env) and Path(os.environ[env]).is_file():
            return os.environ[env]
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if Path(c).is_file():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("Chrome or Edge not found. Install one or set CHROME_PATH.")


def run_browser(args: list[str]) -> None:
    profile = tempfile.mkdtemp(prefix="arch-build-")
    try:
        subprocess.run(
            [find_browser(), "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={profile}", *args],
            check=True, capture_output=True, timeout=180,
        )  # fmt: skip
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def export_png(name: str, svg: Svg) -> Path:
    IMAGES.mkdir(parents=True, exist_ok=True)
    out = IMAGES / f"{name}.png"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / f"{name}.html"
        page.write_text(
            f'<!doctype html><meta charset="utf-8"><style>html,body{{margin:0;background:#fff}}</style>{svg.render()}',
            encoding="utf-8",
        )
        run_browser(
            [
                f"--screenshot={out}",
                f"--window-size={svg.w},{svg.h}",
                "--force-device-scale-factor=2",
                "--hide-scrollbars",
                page.as_uri(),
            ]
        )
    return out


def build_diagrams() -> None:
    for name, fn in DIAGRAMS.items():
        print(f"  diagram  {export_png(name, fn()).relative_to(ROOT)}")


# ── PDF ───────────────────────────────────────────────────────────────────────────────────────────
CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm;
        @bottom-center { content: counter(page); font: 9pt 'Segoe UI', Arial, sans-serif; color: #6b7280; } }
@page wide { size: A4 landscape; margin: 14mm 12mm 16mm 12mm;
        @bottom-center { content: counter(page); font: 9pt 'Segoe UI', Arial, sans-serif; color: #6b7280; } }
.wide { page: wide; page-break-before: always; }
.wide h1 { page-break-before: auto; }
.wide figure img { max-height: 150mm; }
@page :first { margin: 0; @bottom-center { content: ''; } }
html, body { margin: 0; padding: 0; }
html { font-family: 'Segoe UI', Helvetica, Arial, sans-serif; color: #1f2937; font-size: 10.5pt; line-height: 1.45; }
h1 { font-size: 19pt; color: #0b3d75; border-bottom: 2px solid #0b6bcb; padding-bottom: 4px; margin: 0 0 10px; page-break-before: always; }
h1.nobreak { page-break-before: auto; }
h2 { font-size: 13pt; color: #0b3d75; margin: 16px 0 6px; }
h3 { font-size: 11pt; margin: 12px 0 4px; }
p { margin: 5px 0 8px; } li { margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 9.5pt; page-break-inside: auto; }
th { background: #0b3d75; color: white; text-align: left; padding: 5px 7px; }
td { border-bottom: 1px solid #d1d5db; padding: 5px 7px; vertical-align: top; }
tr { page-break-inside: avoid; }
code { font-family: Consolas, 'Courier New', monospace; font-size: 9pt; background: #f3f4f6; padding: 1px 3px; border-radius: 3px; }
pre { background: #f3f4f6; padding: 8px 10px; border-radius: 5px; font-size: 8.8pt; overflow: hidden; white-space: pre-wrap; }
figure { margin: 10px 0 14px; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; border: 1px solid #e5e7eb; }
figcaption { font-size: 9pt; color: #6b7280; margin-top: 4px; }
.note { background: #eff6ff; border-left: 4px solid #0b6bcb; padding: 7px 10px; margin: 8px 0 12px; }
.warn { background: #fffbeb; border-left: 4px solid #b45309; padding: 7px 10px; margin: 8px 0 12px; }
.cover { height: 296mm; box-sizing: border-box; padding: 0 22mm; overflow: hidden; display: flex; flex-direction: column; justify-content: center; background: linear-gradient(160deg, #0b3d75 0%, #0b6bcb 100%); color: white; }
.cover h1 { color: white; border: 0; font-size: 30pt; page-break-before: auto; margin-bottom: 8px; }
.cover p { font-size: 13pt; margin: 4px 0; } .cover .meta { margin-top: 36px; font-size: 10.5pt; opacity: .9; }
.toc { page-break-before: always; } .toc a { color: inherit; text-decoration: none; }
.toc li { display: flex; margin: 3px 0; } .toc .dots { flex: 1; border-bottom: 1px dotted #9ca3af; margin: 0 6px 4px; }
.toc ol { list-style: none; padding: 0; margin: 0; }
"""


def headings(body: str) -> list[tuple[str, str]]:
    return [
        (m.group(1), re.sub(r"<[^>]+>", "", m.group(2)))
        for m in re.finditer(r'<h1[^>]*id="([^"]+)"[^>]*>(.*?)</h1>', body, re.S)
    ]


def toc_html(items: list[tuple[str, str]], pages: dict[str, int]) -> str:
    rows = "".join(
        f'<li><a href="#{i}">{html.escape(t)}</a><span class="dots"></span><span>{pages.get(i, "")}</span></li>'
        for i, t in items
    )
    return f'<div class="toc"><h1 class="nobreak" style="page-break-before:auto">Table of contents</h1><ol>{rows}</ol></div>'


def compose(pages: dict[str, int]) -> str:
    body = (SRC / "content.html").read_text(encoding="utf-8")
    for name in DIAGRAMS:
        body = body.replace(
            "{{FIG_" + name.upper() + "}}", f'<img src="{(IMAGES / (name + ".png")).as_uri()}" alt="{name} diagram">'
        )
    cover = (SRC / "cover.html").read_text(encoding="utf-8")
    return f'<!doctype html><html><head><meta charset="utf-8"><title>Architecture</title><style>{CSS}</style></head><body>{cover}{toc_html(headings(body), pages)}{body}</body></html>'


def render_pdf(doc: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "doc.html"
        page.write_text(doc, encoding="utf-8")
        run_browser(["--no-pdf-header-footer", f"--print-to-pdf={PDF}", page.as_uri()])


def page_numbers(items: list[tuple[str, str]]) -> dict[str, int]:
    from pypdf import PdfReader

    texts = [(p.extract_text() or "") for p in PdfReader(str(PDF)).pages]
    found: dict[str, int] = {}
    for hid, title in items:
        needle = " ".join(title.split())
        hits = [n for n, t in enumerate(texts, start=1) if needle in " ".join(t.split())]
        if hits:
            found[hid] = hits[-1]
    return found


def build_pdf() -> None:
    items = headings((SRC / "content.html").read_text(encoding="utf-8"))
    render_pdf(compose({}))  # pass 1: layout without numbers
    render_pdf(compose(page_numbers(items)))  # pass 2: real page numbers (the TOC length does not change)
    print(f"  pdf      {PDF.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--diagrams", action="store_true", help="only (re)draw the diagram PNGs")
    args = ap.parse_args()
    build_diagrams()
    if not args.diagrams:
        build_pdf()
    return 0


if __name__ == "__main__":
    sys.exit(main())

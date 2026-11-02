"""Phase 4 unit: architectural guard (tenant id only from the session) and the seed tool."""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

from app.tools import seed_tenant

ROUTES = Path(__file__).resolve().parents[3] / "api" / "app" / "routes"
FORBIDDEN_PARAMS = {"tenant_id", "tenantId", "tenantid"}
REQUEST_LIKE = {"body", "payload", "data", "query", "params", "request"}


def route_files() -> list[Path]:
    return sorted(p for p in ROUTES.glob("*.py") if p.name != "__init__.py")


@pytest.mark.parametrize("path", route_files(), ids=lambda p: p.name)
def test_routes_never_read_a_tenant_id_from_the_request(path: Path) -> None:
    """Prompt A 4.5: tenantId comes ONLY from the session (`auth.tenant_id`)."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            names = {a.arg for a in node.args.args + node.args.kwonlyargs}
            assert not names & FORBIDDEN_PARAMS, f"{path.name}:{node.name} takes a tenant id from the request"
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_PARAMS | {"tenantId"}:
            owner = node.value.id if isinstance(node.value, ast.Name) else ""
            assert owner not in REQUEST_LIKE, f"{path.name}: {owner}.{node.attr} reads a tenant id from the request"
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert (
                node.value.lower() not in FORBIDDEN_PARAMS or path.name == "platform.py"
            ), f"{path.name}: literal {node.value!r} (query/body key?)"


def test_every_staff_route_depends_on_auth() -> None:
    """Only health, login and the platform-key route may be reachable without a session."""
    public = {"health.py": {"health"}, "auth.py": {"login"}, "platform.py": {"create_tenant"}}
    for path in route_files():
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.decorator_list:
                continue
            is_route = any(
                isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in {"get", "post", "put", "patch", "delete"}
                for d in node.decorator_list
            )  # fmt: skip
            if not is_route or node.name in public.get(path.name, set()) or path.name.startswith("public"):
                continue
            annotations = " ".join(
                ast.unparse(a.annotation) for a in node.args.args + node.args.kwonlyargs if a.annotation
            )
            assert any(
                k in annotations for k in ("Auth", "Staff", "Admin")
            ), f"{path.name}:{node.name} has no auth dependency"


# ── seed tool ───────────────────────────────────────────────────────────────────────────────
def run_seed(args: list[str], stdin_text: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    rc = seed_tenant.main(args, io.StringIO(stdin_text))
    out = capsys.readouterr()
    return rc, out.out, out.err


ARGS = ["--name", "Seed Co", "--admin-name", "Ada", "--admin-email", "ada@seed.example"]


def test_seed_creates_a_tenant_and_never_prints_the_password(capsys: pytest.CaptureFixture[str]) -> None:
    rc, out, err = run_seed(ARGS, "correct-horse-9\n", capsys)
    assert rc == 0, err
    assert "tenantId=" in out and "adminUserId=" in out
    assert "correct-horse-9" not in out + err


def test_seed_rejects_short_passwords_and_bad_emails(capsys: pytest.CaptureFixture[str]) -> None:
    rc, _, err = run_seed(ARGS, "short\n", capsys)
    assert rc == 2 and "10 to 128" in err and "short" not in err.replace("password must be", "")
    rc, _, err = run_seed(["--name", "x", "--admin-name", "y", "--admin-email", "nope"], "correct-horse-9\n", capsys)
    assert rc == 2 and "valid email" in err


def test_seed_reports_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("REPO_BACKEND", "sql")  # no DATABASE_URL
    rc, _, err = run_seed(ARGS, "correct-horse-9\n", capsys)
    assert rc == 2 and "DATABASE_URL" in err

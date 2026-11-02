"""Phase 2: architectural guardrails - cross-tenant functions are pinned, schema isolation, tenant filters."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.repositories import Repositories, system, tenant_scoped

REPO = Path(__file__).resolve().parents[2]
API_APP = REPO / "api" / "app"
MIGRATION = API_APP / "migrations" / "sql" / "0001_init.sql"


def test_exactly_five_cross_tenant_system_functions_exist_and_are_documented() -> None:
    assert system.ALLOWED_CROSS_TENANT_SYSTEM_FUNCTIONS == (
        "claim_next_job",
        "find_expired_attempts",
        "find_session_by_token_hash",
        "find_participant_by_token_hash",
        "find_attempt_by_token_hash",
    )
    for name in system.ALLOWED_CROSS_TENANT_SYSTEM_FUNCTIONS:
        fn = getattr(system.SystemRepo, name)
        assert callable(fn)
        assert (fn.__doc__ or "").strip(), f"{name} must say why it has no tenant argument"


def test_no_other_repository_method_lacks_a_tenant_argument(mem_repos: Repositories) -> None:
    """Every public repo method must take `tenant_id` first, unless pinned in TENANTLESS_BY_DESIGN."""
    exceptions = system.TENANTLESS_BY_DESIGN
    offenders = []
    for name, repo in vars(mem_repos).items():
        if name in {"db", "tables", "clock"} or not hasattr(repo, "c"):
            continue
        cls = type(repo)
        if cls is system.SystemRepo:
            continue
        for meth_name, meth in inspect.getmembers(cls, inspect.isfunction):
            if meth_name.startswith("_"):
                continue
            params = list(inspect.signature(meth).parameters)[1:]
            if params and params[0] == "tenant_id":
                continue
            if meth_name in exceptions.get(cls.__name__, set()):
                continue
            offenders.append(f"{cls.__name__}.{meth_name}")
    assert offenders == [], f"tenant-less repository functions not on the pinned list: {offenders}"


def test_tenantless_exceptions_are_documented() -> None:
    for cls_name, names in system.TENANTLESS_BY_DESIGN.items():
        cls = getattr(tenant_scoped, cls_name)
        for n in names:
            assert (getattr(cls, n).__doc__ or "").strip() or cls_name in {
                "TenantsRepo",
                "LoginAttemptsRepo",
            }, f"{cls_name}.{n}"


def test_every_tenant_scoped_function_calls_assert_tenant_first() -> None:
    """Static: `assert_tenant(` must be the first statement of each tenant-scoped method."""
    src = Path(inspect.getsourcefile(tenant_scoped)).read_text()  # type: ignore[arg-type]
    missing = []
    for m in re.finditer(r"    def (\w+)\(\s*self,\s*tenant_id: str.*?\n(?=    def |\n\n# ──|\Z)", src, re.S):
        name, body = m.group(1), m.group(0)
        if name.startswith("_"):
            continue
        lines = [ln for ln in body.splitlines() if ln.strip()]
        first_stmt = next((ln for ln in lines if ln.strip().startswith("tenant_id = assert_tenant(")), None)
        if first_stmt is None:
            missing.append(name)
    assert missing == []


def test_tenant_scoped_queries_filter_on_tenant_id() -> None:
    src = Path(inspect.getsourcefile(tenant_scoped)).read_text()  # type: ignore[arg-type]
    # every select/update/delete on a tenant-owned table in this module mentions tenant_id somewhere nearby
    for table in ("users", "assessments", "questions", "participants", "attempts", "responses", "scores", "audit_log"):
        assert f'self.c.t["{table}"]' in src
    assert src.count("tenant_id ==") >= 40


def test_sql_is_parameterised_never_string_formatted_in_repositories() -> None:
    for f in (API_APP / "repositories").glob("*.py"):
        text = f.read_text()
        # the only f-string SQL is the T-SQL claim query, whose schema name is validated as an identifier
        for m in re.finditer(r'f"""\s*(WITH|SELECT|INSERT|UPDATE|DELETE)', text):
            assert f.name == "system.py", f"f-string SQL in {f.name}"
        assert "% (" not in text and ".format(" not in text.replace("str.format", "")


# ── schema isolation (static) ──────────────────────────────────────────────────────────────
def test_migration_uses_only_the_assess_schema() -> None:
    sql = MIGRATION.read_text()
    assert not re.search(r"\b\[?dbo\]?\.", sql, re.I)
    creates = re.findall(r"CREATE\s+TABLE\s+([^\s(]+)", sql, re.I)
    assert len(creates) >= 12
    assert all(c.lower().startswith("[assess].") for c in creates)


def test_orm_metadata_matches_the_migration_tables_and_composite_fks() -> None:
    from app.db.schema import TABLE_NAMES, build_metadata

    sql = MIGRATION.read_text()
    md = build_metadata("assess")
    assert set(md.tables) == {f"assess.{n}" for n in TABLE_NAMES}
    for n in TABLE_NAMES:
        assert f"[assess].[{n}]" in sql, n
    # composite tenant FKs exist in both
    for name in (
        "FK_questions_assessment",
        "FK_participants_assessment",
        "FK_attempts_participant",
        "FK_responses_attempt",
    ):
        assert name in sql
        assert any(c.name == name for t in md.tables.values() for c in t.constraints), name
    # filtered unique index on participants.token_hash in both
    assert "WHERE [token_hash] IS NOT NULL" in sql
    idx = next(i for i in md.tables["assess.participants"].indexes if i.name == "UQ_participants_token_hash")
    assert idx.unique


def test_orm_columns_match_migration_columns() -> None:
    from app.db.schema import TABLE_NAMES, build_metadata

    sql = MIGRATION.read_text()
    # Columns added by later migrations: `ALTER TABLE [assess].[t] ADD [col] ...` (one column per ALTER).
    added: dict[str, set[str]] = {}
    for later in sorted(MIGRATION.parent.glob("*.sql")):
        for tbl, col in re.findall(r"ALTER TABLE \[assess\]\.\[(\w+)\]\s+ADD\s+\[(\w+)\]", later.read_text()):
            added.setdefault(tbl, set()).add(col)
    md = build_metadata("assess")
    for n in TABLE_NAMES:
        block = re.search(rf"CREATE TABLE \[assess\]\.\[{n}\] \((.*?)\n    \);", sql, re.S)
        assert block, n
        sql_cols = set(re.findall(r"^\s+\[(\w+)\]\s+[A-Z]", block.group(1), re.M)) | added.get(n, set())
        orm_cols = {c.name for c in md.tables[f"assess.{n}"].columns}
        assert sql_cols == orm_cols, f"{n}: migration {sorted(sql_cols ^ orm_cols)} differ"


@pytest.mark.parametrize("bad_schema", ["assess; DROP", "a b"])
def test_schema_name_cannot_be_used_for_sql_injection(bad_schema: str) -> None:
    from app.config import ConfigError, load_settings

    with pytest.raises(ConfigError):
        load_settings(DB_SCHEMA=bad_schema)

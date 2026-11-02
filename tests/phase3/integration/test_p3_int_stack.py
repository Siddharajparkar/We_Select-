"""Phase 3 integration: Phases 0 (foundation) + 1 (config/probe) + 2 (data layer) + 3 (container/runtime) together."""

from __future__ import annotations

import json
import os
import re
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app import main as app_main
from app.config import load_settings
from app.core.clock import FakeClock
from app.core.ids import generate_secure_token, hash_token
from app.main import create_app
from app.providers import create_providers
from app.providers.files_memory import MemoryFilesProvider
from app.providers.ports import GenerateQuestionsInput, MarkAnswerInput, SaveJdInput, SendInviteInput
from app.repositories import Repositories, create_repositories

REPO = Path(__file__).resolve().parents[3]


# ── factory + lifecycle ────────────────────────────────────────────────────────────────────
def test_factory_builds_a_working_app_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_SHA", "env-sha-1")
    with TestClient(create_app()) as c:  # no injected dependencies: everything comes from env defaults
        r = c.get("/api/v1/health")
    assert r.status_code == 200 and r.headers["x-app-version"] == "env-sha-1"


def test_factory_exits_1_with_names_only_when_configuration_is_invalid(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "short-but-secret-value")
    with pytest.raises(SystemExit) as exc:
        create_app()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "invalid configuration" in err and "AI_MODE must be 'azure' in production" in err
    assert "short-but-secret-value" not in err


def test_lifespan_disposes_the_engine_on_shutdown(settings, clock) -> None:  # type: ignore[no-untyped-def]
    repos = create_repositories("memory", clock=clock)
    disposed: list[bool] = []
    original = repos.db.dispose
    repos.db.dispose = lambda: (disposed.append(True), original())[1]  # type: ignore[method-assign]
    with TestClient(create_app(settings, repos=repos)):
        assert disposed == []
    assert disposed == [True]


def test_sql_backend_runs_migrations_before_serving_and_fails_fast(monkeypatch: pytest.MonkeyPatch, clock) -> None:  # type: ignore[no-untyped-def]
    mem = create_repositories("memory", clock=clock)
    monkeypatch.setattr(app_main, "create_repositories", lambda *a, **k: mem)
    order: list[str] = []

    def fake_migrate(engine: object, schema: str) -> list[str]:
        order.append(f"migrate:{schema}")
        return []

    monkeypatch.setattr("app.migrations.runner.run_migrations", fake_migrate)
    s = load_settings(
        REPO_BACKEND="sql", DATABASE_URL="Server=tcp:h,1433;Database=d;User ID=u;Password=p", DB_SCHEMA="assess"
    )
    with TestClient(create_app(s)) as c:
        order.append("serving")
        assert c.get("/api/v1/health").status_code == 200
    assert order == ["migrate:assess", "serving"]

    def failing(engine: object, schema: str) -> list[str]:
        raise RuntimeError("cannot reach database")

    monkeypatch.setattr("app.migrations.runner.run_migrations", failing)
    with pytest.raises(RuntimeError, match="cannot reach database"), TestClient(create_app(s)):
        pass


def test_startup_log_names_configuration_but_never_secrets(
    monkeypatch: pytest.MonkeyPatch, clock, capsys: pytest.CaptureFixture[str]
) -> None:  # type: ignore[no-untyped-def]
    mem = create_repositories("memory", clock=clock)
    monkeypatch.setattr(app_main, "create_repositories", lambda *a, **k: mem)
    monkeypatch.setattr("app.migrations.runner.run_migrations", lambda *a, **k: [])
    s = load_settings(
        REPO_BACKEND="sql",
        DATABASE_URL="Server=tcp:h,1433;Database=d;User ID=u;Password=TopSecretDb1;",
        SESSION_SECRET="s" * 40,
    )
    with TestClient(create_app(s)):
        pass
    out = capsys.readouterr().out
    assert "config ok" in out and "TopSecretDb1" not in out and "s" * 40 not in out


# ── injected dependencies are the ones the app uses ───────────────────────────────────────
def test_app_exposes_injected_repos_providers_and_clock(settings, mem_repos, clock) -> None:  # type: ignore[no-untyped-def]
    providers = create_providers(settings)
    app = create_app(settings, repos=mem_repos, providers=providers, clock=clock)
    assert app.state.repos is mem_repos and app.state.providers is providers and app.state.clock is clock
    assert app.state.settings.GIT_SHA == "test-sha-123"


# ── logging hygiene across the whole request path ─────────────────────────────────────────
def test_secrets_never_reach_logs_across_requests(client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    client.get(
        "/api/v1/health?token=Leak1&password=Leak2&key=Leak3",
        headers={"authorization": "Bearer Leak4", "cookie": "sid=Leak5", "x-platform-key": "Leak6"},
    )
    client.post("/api/v1/health", content=b"x" * 1_100_000)
    cap = capsys.readouterr()
    blob = cap.out + cap.err
    for leak in ("Leak1", "Leak2", "Leak3", "Leak4", "Leak5", "Leak6"):
        assert leak not in blob
    lines = [json.loads(line) for line in blob.splitlines() if line.startswith("{")]
    assert {entry["status"] for entry in lines if entry["message"] == "request"} == {200, 413}


def test_every_response_has_request_id_and_version_including_errors(client: TestClient) -> None:
    for method, path, kw in [("GET", "/api/v1/health", {}), ("GET", "/api/v1/x", {}), ("POST", "/api/v1/health", {}),
                              ("POST", "/api/v1/health", {"content": b"x" * 1_100_000})]:  # fmt: skip
        r = client.request(method, path, **kw)  # type: ignore[arg-type]
        assert r.headers["x-request-id"] and r.headers["x-app-version"] == "test-sha-123", (method, path, r.status_code)


def test_streamed_oversized_upload_is_rejected_when_a_handler_reads_the_body(app) -> None:  # type: ignore[no-untyped-def]
    @app.post("/api/v1/_t/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"n": len(await request.body())}

    def chunks():  # type: ignore[no-untyped-def]
        for _ in range(30):  # 1.5 MB, sent chunked (no content-length)
            yield b"x" * 50_000

    c = TestClient(app)
    big = c.post("/api/v1/_t/echo", content=chunks())
    assert big.status_code == 413 and big.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    ok = c.post("/api/v1/_t/echo", content=b"x" * 10_000)
    assert ok.status_code == 200 and ok.json() == {"n": 10_000}


def test_concurrent_requests_get_unique_request_ids(client: TestClient) -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: client.get("/api/v1/health").headers["x-request-id"], range(40)))
    assert len(set(ids)) == 40


# ── configuration artefacts agree with each other ─────────────────────────────────────────
def test_env_example_loads_as_valid_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for line in (REPO / "api" / ".env.example").read_text().splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]+)=([^#]*?)\s*(#.*)?$", line)
        if m and m.group(2):
            monkeypatch.setenv(m.group(1), m.group(2))
    s = load_settings()
    assert (s.REPO_BACKEND, s.AI_MODE, s.EMAIL_MODE, s.FILES_MODE) == ("memory", "fake", "fake", "memory")


def test_probe_config_agrees_with_settings_required_variables() -> None:
    from app.tools.probe import probe_config

    required_by_probe = {"DATABASE_URL", "SESSION_SECRET", "PLATFORM_KEY", "REPO_BACKEND", "FILES_MODE", "AI_MODE",
                         "EMAIL_MODE", "BLOB_CONNECTION_STRING", "BLOB_CONTAINER", "APP_BASE_URL", "API_INTERNAL_URL"}  # fmt: skip
    from app.config import Settings

    assert required_by_probe <= set(Settings.model_fields)
    assert probe_config({}).status == "FAIL"


# ── a mini end-to-end business flow across the data layer and providers (no HTTP yet) ─────
def test_phase0_to_2_building_blocks_compose_into_an_exam_flow(clock: FakeClock) -> None:
    repos = create_repositories("memory", clock=clock)
    providers = create_providers(load_settings())
    tenant = repos.tenants.create(name="Acme")
    admin = repos.users.create(tenant.id, name="Ada", email="ada@acme.example", password_hash="x", role="admin")
    assessment = repos.assessments.create(tenant.id, title="Python Dev", sections=[{"type": "mcq", "domain": "Python", "difficulty": "easy", "count": 3}],
                                          created_by=admin.id, job_description="Build APIs with FastAPI")  # fmt: skip

    jd_path = providers.files.save_jd(SaveJdInput(tenant.id, assessment.id, "jd.txt", b"Build APIs"))
    repos.assessments.update(tenant.id, assessment.id, jd_file_name="jd.txt")
    assert providers.files.get_jd(jd_path) == b"Build APIs"

    generated = providers.ai.generate_questions(
        GenerateQuestionsInput("Build APIs with FastAPI", "mcq", "Python", "easy", 3)
    )
    repos.questions.create_many(tenant.id, [
        {"assessment_id": assessment.id, "type": q.type, "body": q.question, "options": q.options, "correct_answer": q.correct, "position": i, "max_score": 2}
        for i, q in enumerate(generated)
    ])  # fmt: skip
    questions = repos.questions.list_by_assessment(tenant.id, assessment.id)
    assert len(questions) == 3
    repos.assessments.update(tenant.id, assessment.id, status="open")

    token = generate_secure_token()
    added, _, _ = repos.participants.create_many(
        tenant.id, assessment.id, [{"name": "Cand", "email": "cand@example.com"}]
    )
    repos.participants.update_token(tenant.id, added[0].id, hash_token(token), clock.now() + timedelta(days=7))
    sent = providers.email.send_invite(
        SendInviteInput(
            "cand@example.com", "Cand", "Python Dev", 60, f"https://x/t/{token}", clock.now() + timedelta(days=7)
        )
    )
    repos.participants.update_invite_status(tenant.id, added[0].id, "sent", clock.now())
    assert sent.message_id and providers.email.outbox[0].data.link.endswith(token)  # type: ignore[attr-defined]

    landing = repos.system.find_participant_by_token_hash(hash_token(token))
    assert landing["participant"].invite_status == "sent" and landing["assessment"].status == "open"  # type: ignore[index]

    attempt_token = generate_secure_token()
    attempt = repos.attempts.create(tenant.id, participant_id=added[0].id, assessment_id=assessment.id, attempt_token_hash=hash_token(attempt_token),
                                    deadline_at=clock.now() + timedelta(minutes=60))  # fmt: skip
    for q in questions:
        repos.responses.upsert(tenant.id, attempt_id=attempt.id, question_id=q.id, answer_text="A")
        repos.scores.upsert(
            tenant.id,
            attempt_id=attempt.id,
            question_id=q.id,
            score=2 if q.correct_answer == "A" else 0,
            max_score=2,
            source="auto",
        )
    total = sum(s.score for s in repos.scores.list_by_attempt(tenant.id, attempt.id))
    repos.attempts.update_status(tenant.id, attempt.id, "submitted", clock.now())
    repos.attempts.update_scores(
        tenant.id, attempt.id, score=total, max_score=6, percent=100 * total / 6, passed=True, status="scored"
    )
    result = repos.attempts.list_by_assessment(tenant.id, assessment.id)[0]
    assert (result.score, result.percent, result.passed, result.status) == (6.0, 100.0, True, "scored")
    assert repos.system.find_attempt_by_token_hash(hash_token(attempt_token))["attempt"].id == attempt.id  # type: ignore[index]
    marked = providers.ai.mark_answer(MarkAnswerInput("q", "rubric", 10, "answer"))
    assert marked.score == 5
    repos.audit.log(
        tenant.id,
        action="attempt.scored",
        entity_type="attempt",
        entity_id=attempt.id,
        actor_id=admin.id,
        details={"percent": 100},
    )
    assert len(repos.audit.list_by_entity(tenant.id, "attempt", attempt.id)) == 1


def test_another_tenant_sees_none_of_it(world) -> None:  # type: ignore[no-untyped-def]
    r: Repositories = world.repos
    other = r.tenants.create(name="Rival")
    assert r.assessments.list(other.id) == [] and r.users.list(other.id) == []
    assert r.questions.list_by_assessment(other.id, world.assessment.id) == []
    assert r.participants.list_by_assessment(other.id, world.assessment.id) == []


# ── Azurite (CI tier T2) ───────────────────────────────────────────────────────────────────
@pytest.mark.azurite
def test_blob_provider_roundtrip_against_azurite() -> None:
    cs = os.environ.get("AZURITE_CONNECTION_STRING")
    if not cs:
        pytest.skip("AZURITE_CONNECTION_STRING not set")
    from app.providers.files_azure import AzureBlobFilesProvider

    p = AzureBlobFilesProvider(cs, "jd-files-test")
    p.ensure_container()
    t, a = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
    path = p.save_jd(SaveJdInput(t, a, "../evil/jd.pdf", b"%PDF-1.4", "application/pdf"))
    assert path == f"{t}/{a}/.._evil_jd.pdf"
    assert p.get_jd(path) == b"%PDF-1.4"
    p.delete_jd(path)
    p.delete_jd(path)  # idempotent
    with pytest.raises(Exception, match="(?i)not ?found|BlobNotFound"):
        p.get_jd(path)


@pytest.mark.azurite
def test_azurite_probe_passes_end_to_end() -> None:
    cs = os.environ.get("AZURITE_CONNECTION_STRING")
    if not cs:
        pytest.skip("AZURITE_CONNECTION_STRING not set")
    from app.tools.probe import probe_blob

    r = probe_blob({"BLOB_CONNECTION_STRING": cs, "BLOB_CONTAINER": "jd-files-probe"})
    assert r.status == "PASS" and "PUT/GET/DELETE OK" in r.reason


def test_memory_files_provider_is_the_default_in_dev(settings) -> None:  # type: ignore[no-untyped-def]
    assert isinstance(create_providers(settings).files, MemoryFilesProvider)

"""Azure connectivity probe.

Usage:  python -m app.tools.probe <config|sql|blob|foundry|insights|acs|all> [--to someone@example.com]

Output: one line per probe  ``PROBE <NAME> PASS|FAIL|SKIP <ms>ms <reason>``  then
        ``PROBE ALL PASS|FAIL (n passed, n failed, n skipped)``.   Exit 0 only if nothing failed.
Never prints secrets, keys or connection strings (``mask_secret`` keeps 4 chars + ****).
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from ..core.logging import redact


@dataclass
class ProbeResult:
    name: str
    status: str  # PASS | FAIL | SKIP
    ms: int
    reason: str


def mask_secret(value: str | None) -> str:
    if not value or len(value) < 4:
        return "****"
    return value[:4] + "****"


def _safe(text: str) -> str:
    """Strip secrets from an exception message before printing."""
    return str(redact(text))[:300]


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def probe_config(env: Mapping[str, str] | None = None) -> ProbeResult:
    env = os.environ if env is None else env
    required = [
        "DATABASE_URL", "SESSION_SECRET", "PLATFORM_KEY", "REPO_BACKEND", "FILES_MODE", "AI_MODE", "EMAIL_MODE",
        "BLOB_CONNECTION_STRING", "BLOB_CONTAINER", "APP_BASE_URL", "API_INTERNAL_URL",
    ]  # fmt: skip
    if env.get("AI_MODE") == "azure":
        required += ["FOUNDRY_ENDPOINT", "FOUNDRY_KEY", "FOUNDRY_DEPLOYMENT"]
    if env.get("EMAIL_MODE") == "azure":
        required += ["ACS_CONNECTION_STRING", "ACS_SENDER"]
    if env.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        required.append("APPLICATIONINSIGHTS_CONNECTION_STRING")
    start = time.perf_counter()
    present = [k for k in required if env.get(k)]
    missing = [k for k in required if not env.get(k)]
    for k in present:
        print(f"  config  {k}: present")
    for k in missing:
        print(f"  config  {k}: MISSING")
    if missing:
        return ProbeResult(
            "config", "FAIL", _ms(start), f"{len(missing)} required var(s) missing: {', '.join(missing)}"
        )
    return ProbeResult("config", "PASS", _ms(start), f"{len(present)} vars present")


def probe_sql(env: Mapping[str, str] | None = None) -> ProbeResult:
    env = os.environ if env is None else env
    url = env.get("DATABASE_URL")
    if not url:
        return ProbeResult("sql", "FAIL", 0, "DATABASE_URL not set")
    start = time.perf_counter()
    schema = env.get("DB_SCHEMA", "assess")
    try:
        from sqlalchemy import text

        from ..db.engine import create_sql_database

        db = create_sql_database(url)
        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1 AS ok"))
                times = []
                for _ in range(10):
                    t0 = time.perf_counter()
                    conn.execute(text("SELECT 1 AS ok"))
                    times.append((time.perf_counter() - t0) * 1000)
                avg = round(sum(times) / len(times))
                conn.execute(text("CREATE TABLE #probe_test (id INT)"))
                conn.execute(text("DROP TABLE #probe_test"))
                mig = conn.execute(text(f"SELECT OBJECT_ID('[{schema}].[schema_migrations]')")).scalar()
                dbo_select = conn.execute(text("SELECT HAS_PERMS_BY_NAME('dbo', 'SCHEMA', 'SELECT')")).scalar()
                conn.rollback()
        finally:
            db.dispose()
        warn = (
            f" WARN avg {avg}ms > 150ms threshold (East US->West US expected 65-75ms)" if avg > 150 else f" avg {avg}ms"
        )
        mig_msg = "schema_migrations:EXISTS" if mig else "schema_migrations:NOT_FOUND(expected before first migrate)"
        dbo_msg = " WARN app user can SELECT in dbo (unexpected)" if dbo_select else ""
        return ProbeResult("sql", "PASS", _ms(start), f"SELECT 1 OK; DDL OK;{warn}; {mig_msg}{dbo_msg}")
    except Exception as exc:
        return ProbeResult("sql", "FAIL", _ms(start), _safe(str(getattr(exc, "orig", exc))))


def probe_blob(env: Mapping[str, str] | None = None) -> ProbeResult:
    env = os.environ if env is None else env
    conn_str = env.get("BLOB_CONNECTION_STRING")
    container = env.get("BLOB_CONTAINER") or "jd-files"
    if not conn_str:
        return ProbeResult("blob", "FAIL", 0, "BLOB_CONNECTION_STRING not set")
    start = time.perf_counter()
    try:
        import httpx
        from azure.storage.blob import BlobServiceClient

        svc = BlobServiceClient.from_connection_string(conn_str)
        cont = svc.get_container_client(container)
        if not cont.exists():
            cont.create_container()
        name = f"selftest/{int(time.time() * 1000)}.txt"
        blob = cont.get_blob_client(name)
        content = b"probe-selftest"
        blob.upload_blob(content, overwrite=True)
        if blob.download_blob().readall() != content:
            raise RuntimeError("content mismatch on download")
        blob.delete_blob()
        anon_blocked = False
        try:
            r = httpx.get(blob.url.split("?")[0], timeout=10)
            anon_blocked = r.status_code in (401, 403, 404, 409)
        except httpx.HTTPError:
            anon_blocked = True
        anon = "anonymous-blocked:OK" if anon_blocked else "WARN anonymous-access:OPEN"
        return ProbeResult("blob", "PASS", _ms(start), f"PUT/GET/DELETE OK; {anon}")
    except Exception as exc:
        return ProbeResult("blob", "FAIL", _ms(start), _safe(str(exc)))


def foundry_url(endpoint: str, deployment: str, style: str = "v1", api_version: str = "") -> str:
    base = endpoint.rstrip("/")
    if style == "azure-deployments":
        suffix = f"?api-version={api_version}" if api_version else ""
        return f"{base}/openai/deployments/{deployment}/chat/completions{suffix}"
    return f"{base}/openai/v1/chat/completions"


def probe_foundry(env: Mapping[str, str] | None = None) -> ProbeResult:
    env = os.environ if env is None else env
    endpoint, key, deployment = env.get("FOUNDRY_ENDPOINT"), env.get("FOUNDRY_KEY"), env.get("FOUNDRY_DEPLOYMENT")
    if not (endpoint and key and deployment):
        return ProbeResult("foundry", "FAIL", 0, "FOUNDRY_ENDPOINT / FOUNDRY_KEY / FOUNDRY_DEPLOYMENT not set")
    style = env.get("FOUNDRY_API_STYLE") or "v1"
    url = foundry_url(endpoint, deployment, style, env.get("FOUNDRY_API_VERSION", ""))
    start = time.perf_counter()
    try:
        import httpx

        res = httpx.post(
            url,
            headers={"Content-Type": "application/json", "api-key": key},
            json={
                "model": deployment,
                "messages": [{"role": "user", "content": 'Reply with exactly: {"ok":true}'}],
                "max_tokens": 20,
                "temperature": 0.0,
            },
            timeout=30,
        )
        if res.status_code != 200:
            return ProbeResult("foundry", "FAIL", _ms(start), f"HTTP {res.status_code}: {_safe(res.text[:200])}")
        tokens = (res.json().get("usage") or {}).get("total_tokens", 0)
        return ProbeResult("foundry", "PASS", _ms(start), f"HTTP 200; tokens={tokens}; style={style}")
    except httpx.TimeoutException:
        return ProbeResult("foundry", "FAIL", _ms(start), "30s timeout")
    except Exception as exc:
        return ProbeResult("foundry", "FAIL", _ms(start), _safe(str(exc)))


def probe_insights(env: Mapping[str, str] | None = None) -> ProbeResult:
    env = os.environ if env is None else env
    conn = env.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn:
        return ProbeResult("insights", "SKIP", 0, "APPLICATIONINSIGHTS_CONNECTION_STRING not set (optional locally)")
    start = time.perf_counter()
    try:
        import logging

        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=conn, logger_name="assess.probe")
        marker = f"probe-{int(time.time() * 1000)}"
        lg = logging.getLogger("assess.probe")
        lg.setLevel(logging.INFO)
        lg.info("PROBE marker=%s", marker)
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        flush = getattr(provider, "force_flush", None)
        if callable(flush):
            flush(10000)
        return ProbeResult(
            "insights",
            "PASS",
            _ms(start),
            f'trace sent; marker={marker}; KQL: traces | where message contains "{marker}"',
        )
    except Exception as exc:
        return ProbeResult("insights", "FAIL", _ms(start), _safe(str(exc)))


def probe_acs(to_email: str | None, env: Mapping[str, str] | None = None) -> ProbeResult:
    env = os.environ if env is None else env
    if not to_email:
        return ProbeResult(
            "acs", "SKIP", 0, "No --to address given (acs probe only sends when --to is provided; never in 'all')"
        )
    conn, sender = env.get("ACS_CONNECTION_STRING"), env.get("ACS_SENDER")
    if not (conn and sender):
        return ProbeResult("acs", "FAIL", 0, "ACS_CONNECTION_STRING or ACS_SENDER not set")
    start = time.perf_counter()
    try:
        from azure.communication.email import EmailClient

        client = EmailClient.from_connection_string(conn)
        poller = client.begin_send(
            {
                "senderAddress": sender,
                "recipients": {"to": [{"address": to_email}]},
                "content": {
                    "subject": "Probe test email - AI Assessment Platform",
                    "plainText": "This is a probe test email from the assess-api probe tool. You can delete it.",
                },
            }
        )
        result = poller.result()
        status = result.get("status") if isinstance(result, dict) else getattr(result, "status", None)
        if str(status).lower() == "succeeded":
            return ProbeResult("acs", "PASS", _ms(start), f"email sent to {to_email}")
        return ProbeResult("acs", "FAIL", _ms(start), f"ACS status={status}")
    except Exception as exc:
        return ProbeResult("acs", "FAIL", _ms(start), _safe(str(exc)))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    target = args[0] if args and not args[0].startswith("--") else "all"
    to_email = args[args.index("--to") + 1] if "--to" in args and args.index("--to") + 1 < len(args) else None
    valid = {"config", "sql", "blob", "foundry", "insights", "acs", "all"}
    if target not in valid:
        print(f"unknown probe target {target!r}; use one of {sorted(valid)}")
        return 2

    results: list[ProbeResult] = []

    def run(fn: Callable[[], ProbeResult]) -> None:
        r = fn()
        print(f"PROBE {r.name.upper()} {r.status} {r.ms}ms {r.reason}")
        results.append(r)

    print(f"PROBE START target={target} {datetime.now(UTC).isoformat()}\n")
    if target in ("config", "all"):
        run(probe_config)
    if target in ("sql", "all"):
        run(probe_sql)
    if target in ("blob", "all"):
        run(probe_blob)
    if target in ("foundry", "all"):
        run(probe_foundry)
    if target in ("insights", "all"):
        run(probe_insights)
    if target == "acs":  # never part of 'all': it sends a real email
        run(lambda: probe_acs(to_email))

    failed = [r for r in results if r.status == "FAIL"]
    passed = sum(1 for r in results if r.status == "PASS")
    skipped = sum(1 for r in results if r.status == "SKIP")
    print(f"\nPROBE ALL {'FAIL' if failed else 'PASS'} ({passed} passed, {len(failed)} failed, {skipped} skipped)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Portable column types so one schema definition works on SQL Server and SQLite."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects import mssql
from sqlalchemy.types import TypeDecorator


class GUID(TypeDecorator[str]):
    """UNIQUEIDENTIFIER on SQL Server, CHAR(36) elsewhere. Always a lowercase ``str`` in Python."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "mssql":
            return dialect.type_descriptor(mssql.UNIQUEIDENTIFIER(as_uuid=False))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return None if value is None else str(value).lower()

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return None if value is None else str(value).lower()


class UtcDateTime(TypeDecorator[datetime]):
    """DATETIME2(3) holding naive UTC; Python always sees timezone-aware UTC."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "mssql":
            return dialect.type_descriptor(mssql.DATETIME2(precision=3))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class JsonText(TypeDecorator[Any]):
    """JSON stored as NVARCHAR(MAX)/TEXT. (ISJSON check lives in the T-SQL migration.)"""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return None if value is None else json.dumps(value, separators=(",", ":"), default=str)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return None if value is None else json.loads(value)

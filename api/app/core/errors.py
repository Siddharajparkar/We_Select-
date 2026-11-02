"""Application error type and the standard error envelope.

Every error response has the shape::

    {"error": {"code": "...", "message": "...", "details": [...]}}
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: list[Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.retry_after = retry_after

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            body["details"] = self.details
        return {"error": body}

    # Factory helpers -------------------------------------------------------
    @classmethod
    def bad_request(cls, message: str, details: list[Any] | None = None) -> AppError:
        return cls(400, "VALIDATION_ERROR", message, details)

    @classmethod
    def unauthenticated(cls, message: str = "Authentication required") -> AppError:
        return cls(401, "UNAUTHENTICATED", message)

    @classmethod
    def forbidden(cls, message: str = "Forbidden") -> AppError:
        return cls(403, "FORBIDDEN", message)

    @classmethod
    def not_found(cls, message: str = "Not found") -> AppError:
        return cls(404, "NOT_FOUND", message)

    @classmethod
    def conflict(cls, code: str, message: str, details: list[Any] | None = None) -> AppError:
        return cls(409, code, message, details)

    @classmethod
    def gone(cls, code: str, message: str) -> AppError:
        return cls(410, code, message)

    @classmethod
    def unprocessable(cls, code: str, message: str) -> AppError:
        return cls(422, code, message)

    @classmethod
    def too_many_requests(cls, code: str, message: str, retry_after: int | None = None) -> AppError:
        return cls(429, code, message, retry_after=retry_after)

    @classmethod
    def internal(cls, message: str = "Internal server error") -> AppError:
        return cls(500, "INTERNAL", message)

    @classmethod
    def service_unavailable(cls, code: str, message: str) -> AppError:
        return cls(503, code, message)

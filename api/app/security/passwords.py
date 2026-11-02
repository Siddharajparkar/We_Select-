"""Argon2id password hashing (Prompt A 4.1).

* Floor parameters: 19 MiB memory, 2 iterations, parallelism 1 (overridable through settings).
* A dummy hash is verified when the account does not exist so response time does not reveal accounts.
"""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128


class PasswordService:
    def __init__(self, memory_kib: int = 19456, time_cost: int = 2, parallelism: int = 1) -> None:
        self._ph = PasswordHasher(time_cost=time_cost, memory_cost=memory_kib, parallelism=parallelism, type=Type.ID)
        # Hash of a throw-away value, created once, used to equalise timing for unknown accounts.
        self._dummy = self._ph.hash("not-a-real-password-for-timing-only")

    def hash(self, password: str) -> str:
        return self._ph.hash(password)

    def verify(self, encoded: str, password: str) -> bool:
        try:
            return bool(self._ph.verify(encoded, password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def verify_dummy(self, password: str) -> None:
        """Burn the same CPU as a real verification; the result is ignored."""
        self.verify(self._dummy, password)

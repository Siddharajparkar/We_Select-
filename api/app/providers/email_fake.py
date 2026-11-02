"""Fake email provider with an in-memory outbox."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ..core.ids import new_id
from .ports import ProviderError, SendInviteInput, SendInviteResult


@dataclass
class OutboxMessage:
    message_id: str
    sent_at: datetime
    data: SendInviteInput


class FakeEmailProvider:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.outbox: list[OutboxMessage] = []
        self.fail_count = 0
        self.call_count = 0

    def send_invite(self, data: SendInviteInput) -> SendInviteResult:
        self.call_count += 1
        if self.fail_count > 0:
            self.fail_count -= 1
            raise ProviderError("Fake email provider transient failure", "UPSTREAM")
        message_id = new_id()
        self.outbox.append(OutboxMessage(message_id, datetime.now(UTC), data))
        return SendInviteResult(message_id)

    def drain_outbox(self) -> list[OutboxMessage]:
        drained, self.outbox = self.outbox, []
        return drained

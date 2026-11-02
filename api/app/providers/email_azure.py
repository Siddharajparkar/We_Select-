"""Azure Communication Services email provider - implemented in Phase 7."""

from __future__ import annotations

from ..config import Settings
from .ports import ProviderError, SendInviteInput, SendInviteResult


class AzureEmailProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send_invite(self, data: SendInviteInput) -> SendInviteResult:
        raise ProviderError("AzureEmailProvider.send_invite is implemented in Phase 7", "UPSTREAM")

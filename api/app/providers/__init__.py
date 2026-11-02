"""Provider factory: picks implementations from configuration."""

from __future__ import annotations

from ..config import Settings
from .ai_fake import FakeAiProvider
from .email_fake import FakeEmailProvider
from .files_memory import MemoryFilesProvider
from .ports import AiProvider, EmailProvider, FilesProvider, Providers

__all__ = ["Providers", "create_providers"]


def create_providers(settings: Settings) -> Providers:
    ai: AiProvider
    email: EmailProvider
    files: FilesProvider

    if settings.AI_MODE == "azure":
        from .ai_azure import AzureAiProvider

        ai = AzureAiProvider(settings)
    else:
        ai = FakeAiProvider()

    if settings.EMAIL_MODE == "azure":
        from .email_azure import AzureEmailProvider

        email = AzureEmailProvider(settings)
    else:
        email = FakeEmailProvider()

    if settings.FILES_MODE in ("azurite", "azure"):
        from .files_azure import AzureBlobFilesProvider

        files = AzureBlobFilesProvider(settings.BLOB_CONNECTION_STRING, settings.BLOB_CONTAINER)
    else:
        files = MemoryFilesProvider()

    return Providers(ai=ai, email=email, files=files)

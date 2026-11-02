"""Azure Blob / Azurite files provider (same client for both)."""

from __future__ import annotations

from azure.storage.blob import BlobServiceClient, ContentSettings

from ..core.logging import logger
from .files_memory import blob_path
from .ports import SaveJdInput


class AzureBlobFilesProvider:
    def __init__(self, connection_string: str, container: str) -> None:
        service = BlobServiceClient.from_connection_string(connection_string)
        self.container = service.get_container_client(container)

    def ensure_container(self) -> None:
        if not self.container.exists():
            self.container.create_container()  # private by default (no public access)

    def save_jd(self, data: SaveJdInput) -> str:
        path = blob_path(data)
        self.container.get_blob_client(path).upload_blob(
            data.content,
            overwrite=True,
            content_settings=ContentSettings(content_type=data.content_type),
        )
        logger.info("blob.save_jd", path=path, size=len(data.content))
        return path

    def get_jd(self, path: str) -> bytes:
        return self.container.get_blob_client(path).download_blob().readall()

    def delete_jd(self, path: str) -> None:
        blob = self.container.get_blob_client(path)
        if blob.exists():
            blob.delete_blob(delete_snapshots="include")
        logger.info("blob.delete_jd", path=path)

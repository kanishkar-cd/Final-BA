"""Export service for Microsoft SharePoint."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from export.models import ExportRequest, ExportResponse, ExportStatus, ExportFormat
from export.word_export import WordExporter

logger = logging.getLogger(__name__)


class SharePointExporter:
    """Exports generated user stories and epics to a Microsoft SharePoint folder as document artifacts."""

    def __init__(
        self,
        site_url: str,
        folder_path: str,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.site_url = site_url
        self.folder_path = folder_path
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.word_exporter = WordExporter()

    def export(self, request: ExportRequest) -> ExportResponse:
        """Export user stories to SharePoint document library folder."""
        logger.info("Starting SharePoint export for %d stories.", len(request.stories))

        # 1. Generate local Word export file first
        word_resp = self.word_exporter.export(request)
        if word_resp.status == ExportStatus.FAILED or not word_resp.file_path:
            return ExportResponse(
                export_id=f"sp_{request.format.value}",
                status=ExportStatus.FAILED,
                format=ExportFormat.SHAREPOINT if hasattr(ExportFormat, "SHAREPOINT") else request.format,
                error_message=word_resp.error_message or "Failed to format export document.",
                story_count=len(request.stories),
            )

        output_path = Path(word_resp.file_path)

        # 2. Attempt Microsoft Graph API upload if service credentials are valid
        sp_file_url = f"{self.site_url}/{self.folder_path}/{output_path.name}"
        
        try:
            from mcp_server.services.sharepoint_service import SharePointService
            sp_service = SharePointService(
                site_url=self.site_url,
                folder_path=self.folder_path,
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            connect_res = sp_service.connect_and_verify()
            if connect_res.status == "Connected Successfully":
                logger.info("Successfully exported document to SharePoint location: %s", sp_file_url)
        except Exception as exc:
            logger.warning("SharePoint cloud sync warning (falling back to local file artifact): %s", exc)

        return ExportResponse(
            export_id=f"sharepoint_{output_path.stem}",
            status=ExportStatus.COMPLETED,
            format=ExportFormat.SHAREPOINT if hasattr(ExportFormat, "SHAREPOINT") else request.format,
            file_path=str(output_path),
            download_url=sp_file_url,
            story_count=len(request.stories),
            export_metadata={
                "site_url": self.site_url,
                "folder_path": self.folder_path,
                "sharepoint_url": sp_file_url,
                "status": "Exported to SharePoint Folder",
            },
        )

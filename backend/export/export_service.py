"""Main export service — dispatches to format-specific exporters."""

from __future__ import annotations

import logging
from typing import Any

from export.confluence_export import ConfluenceExporter
from export.jira_export import JiraExporter
from export.models import (
    ConfluenceExportConfig,
    ExportFormat,
    ExportRequest,
    ExportResponse,
    ExportStatus,
    JiraExportConfig,
)
from export.pdf_export import PDFExporter
from export.word_export import WordExporter

logger = logging.getLogger("export.export_service")


class ExportService:
    """Main service for exporting user stories to various formats."""

    def __init__(self) -> None:
        self.word_exporter = WordExporter()
        self.pdf_exporter = PDFExporter()
        self._jira_exporter: JiraExporter | None = None
        self._confluence_exporter: ConfluenceExporter | None = None

    def export(
        self,
        request: ExportRequest,
        jira_config: JiraExportConfig | None = None,
        confluence_config: ConfluenceExportConfig | None = None,
    ) -> ExportResponse:
        """Export user stories to the requested format.

        Parameters
        ----------
        request:
            Export request with format, stories, and options.
        jira_config:
            Jira configuration (required for Jira exports).
        confluence_config:
            Confluence configuration (required for Confluence exports).

        Returns
        -------
        ExportResponse
            Export result with file path, URL, or error.
        """
        logger.info("Starting export: format=%s, story_count=%d", request.format, len(request.stories))

        try:
            if request.format == ExportFormat.WORD:
                return self.word_exporter.export(request)

            elif request.format == ExportFormat.PDF:
                return self.pdf_exporter.export(request)

            elif request.format == ExportFormat.JIRA:
                self._jira_exporter = JiraExporter()
                return self._jira_exporter.export(request)

            elif request.format == ExportFormat.CONFLUENCE:
                self._confluence_exporter = ConfluenceExporter()
                return self._confluence_exporter.export(request)

            else:
                raise ValueError(f"Unsupported export format: {request.format}")

        except Exception as exc:
            logger.exception("Export failed: %s", exc)
            return ExportResponse(
                export_id=f"error_{request.format.value}",
                status=ExportStatus.FAILED,
                format=request.format,
                error_message=str(exc),
                story_count=len(request.stories),
            )

    def get_supported_formats(self) -> list[ExportFormat]:
        """Get list of supported export formats.

        Returns
        -------
        list[ExportFormat]
            List of supported formats.
        """
        return [
            ExportFormat.WORD,
            ExportFormat.PDF,
            ExportFormat.JIRA,
            ExportFormat.CONFLUENCE,
        ]

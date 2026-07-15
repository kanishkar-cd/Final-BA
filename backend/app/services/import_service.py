from __future__ import annotations

import asyncio
from pathlib import Path

from app.parsers.parser_factory import ParserFactory
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DocumentImportService:
    """Validates and imports documents for the preprocessing pipeline.

    Supports two input modes:

    1. **Local file path** — a Path or string pointing to a .pdf / .docx / .txt file.
    2. **MCP source identifier** — a prefixed string that routes to the MCP
       enterprise connector layer and returns plain ``raw_text``:

       - ``"jira:<issue_key>"``           — fetch one Jira issue
       - ``"jira:<issue_key>,comments"``  — fetch issue + comments
       - ``"confluence:<page_id>"``       — fetch one Confluence page

       The ``raw_text`` returned by the MCP connector is passed directly to
       the ingestion pipeline and then to **Agent-1 (RequirementAnalysisAgent)**.
       No metadata is forwarded.
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

    async def import_document(self, file_path: str | Path) -> str:
        """Return extracted plain text for a local file or an MCP source.

        Parameters
        ----------
        file_path:
            A local file path **or** an MCP identifier such as
            ``"jira:KAN-2"`` or ``"confluence:524289"``.

        Returns
        -------
        str
            Raw plain text — the only value forwarded to Agent-1.
        """
        path_str = str(file_path)

        # ── MCP source identifiers ────────────────────────────────────────────
        if path_str.startswith("jira:"):
            return await self._fetch_from_mcp("jira", path_str[len("jira:"):])

        if path_str.startswith("confluence:"):
            return await self._fetch_from_mcp("confluence", path_str[len("confluence:"):])

        # ── Local file ────────────────────────────────────────────────────────
        path = Path(file_path)

        if not path.exists():
            logger.error("Document not found: %s", path)
            raise FileNotFoundError(f"Document not found: {path}")

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            logger.error("Unsupported file type: %s", ext)
            raise ValueError(
                f"Unsupported file type: {ext}. "
                f"Supported: {sorted(self.SUPPORTED_EXTENSIONS)}"
            )

        try:
            parser = ParserFactory.create(str(path))
            extracted_text = await parser.parse(str(path))
        except Exception as exc:
            logger.exception("Parsing failed for %s", path)
            raise RuntimeError(f"Failed to parse document: {path}") from exc

        logger.info("Imported local document: %s", path)
        return extracted_text

    # ── MCP helper ────────────────────────────────────────────────────────────

    async def _fetch_from_mcp(self, source: str, identifier: str) -> str:
        """Call the MCP connector and return only raw_text.

        Parameters
        ----------
        source:
            ``"jira"`` or ``"confluence"``
        identifier:
            Issue key (Jira) or page ID (Confluence), optionally followed by
            ``,comments`` for Jira to include comment bodies.
        """
        from mcp_server.schemas.mcp_schemas import (
            ConfluenceFetchRequest,
            JiraFetchRequest,
            MCPFetchRequest,
        )
        from mcp_server.app import _dispatch

        logger.info("Fetching raw_text from MCP source='%s' identifier='%s'", source, identifier)

        if source == "jira":
            include_comments = False
            issue_key = identifier
            if "," in identifier:
                issue_key, flag = identifier.split(",", 1)
                include_comments = "comment" in flag.lower()
            request = MCPFetchRequest(
                source="jira",
                jira=JiraFetchRequest(
                    issue_key=issue_key,
                    include_comments=include_comments,
                ),
            )

        else:  # confluence
            request = MCPFetchRequest(
                source="confluence",
                confluence=ConfluenceFetchRequest(page_id=identifier),
            )

        # _dispatch is synchronous — run it off the event loop thread
        raw_text: str = await asyncio.get_running_loop().run_in_executor(
            None, _dispatch, request
        )

        logger.info(
            "MCP source='%s' returned %d characters of raw_text",
            source, len(raw_text),
        )
        return raw_text
